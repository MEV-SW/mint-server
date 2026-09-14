# API스펙_사건자동배정

- 기능요청: [B4 증분 사건 배정](https://github.com/MEV-SW/mint-server/issues/31)
- 소속: [서버 기능묶음 #27](https://github.com/MEV-SW/mint-server/issues/27) / 프로젝트 [mint-release#9](https://github.com/MEV-SW/mint-release/issues/9)
- 새 REST 엔드포인트는 없다 — 크롤 파이프라인 내부 훅.

## 전제 (결정기록 — B1 설계에서 벗어난 지점)

- **B1 API스펙은 "centroid_vector를 ES `issues` 인덱스에 별도 유지"라고 적었지만, 이 카드는 그 대신 `posts` 인덱스에 대한 kNN + `issue_members` 조인으로 구현한다.** 별도 인덱스·centroid 재계산 없이 같은 기능(신규 기사와 가장 가까운 기존 이슈 찾기)을 달성해 이번 카드 범위를 좁힌다. `Issue.centroid_vector`는 만들지 않는다 — 필요해지면(예: 대량 배치 재클러스터링) 별도 카드.
- 임계값은 **B2 실험값**(near-dup 0.90 / event 0.84)을 그대로 쓴다. [B3](https://github.com/MEV-SW/mint-server/issues/30)의 운영표본 라벨링·확정 전까지 임시값 — `app/core/config.py`의 `issue_near_dup_cosine`/`issue_event_cosine`로 빼서 코드 변경 없이 조정 가능하게 했다.
- 하나의 크롤 훅으로 충분하다 — `CrawlerService._save_discovery_post`(discovery 경로)와 `_save_post`(RSS 경로) 둘 다 내부적으로 `_attach_discovery_ai_output`을 호출하고, 그 안에서 `save_post_content` 뒤에 배정을 붙인다. "두 수집 경로"는 공개 API(`crawl_source`/`crawl_source_to_discovery`) 레벨의 구분이고, Post 저장 직후 로직은 이미 하나로 합쳐져 있었다.

## 배정 로직

```
1. post.published_at 없으면 스킵(배정 불가)
2. ES에서 이 post의 embedding 조회(B0가 색인 시 이미 넣어둠)
   없으면 스킵 — ES/Bedrock 미가용 시 조용히 넘어가고 크롤은 계속됨
3. ES kNN: 같은 organization, published_at ±ISSUE_WINDOW_DAYS(기본 7일),
   숨김·삭제 제외, 상위 20개 후보(post_id, cosine)
4. 후보를 점수 내림차순으로 훑어 issue_members에 이미 속한 것을 찾음
   - cosine >= ISSUE_NEAR_DUP_COSINE → 그 이슈에 합류, role=duplicate,
     issue_revision kind=duplicates
   - cosine >= ISSUE_EVENT_COSINE → 그 이슈에 합류, role=development,
     issue_revision kind=development
   - 둘 다 아니면 다음 후보로. 전부 미달이면 새 이슈
5. 합류 시 member_count/source_count 재계산, last_activity_at 갱신
6. 시리즈 가드 재평가(아래)
```

## 시리즈 가드 (결정기록 — 범위 축소)

B4 이슈 원문은 "near-identical + 정기 주기 + 템플릿 제목"을 시리즈 조건으로 든다. 이 카드는 **"정기 주기"(간격 규칙성) 판별은 하지 않는다** — 지금 표본 밀도로는 신뢰성 있게 못 만든다. 대신:

> 이슈의 `member_count >= 3`이고 `source_count == 1`(지금까지 단 하나의 출처만 반복 보도)이면 `status=series`.

여러 출처가 같은 사건을 다루면(source_count 2 이상) 시리즈로 안 바뀐다 — 진짜 사건과 한 출처의 반복 공지를 이 대리 지표로 가른다. 근거가 더 쌓이면(B3 라벨링, 운영 관찰) 간격 규칙성을 더할 수 있다.

## 설정값

| 키 | 기본값(임시) | 설명 |
|---|---|---|
| `ISSUE_NEAR_DUP_COSINE` | `0.90` | B2 실험값. B3 확정 후 갱신 |
| `ISSUE_EVENT_COSINE` | `0.84` | 동일 |
| `ISSUE_WINDOW_DAYS` | `7` | kNN 후보 시간창 |

`ISSUE_RADAR_ENABLED=false`면 배정 자체가 안 돈다(기존 flag 재사용, 읽기 API와 같은 스위치).
