# API스펙_AI소스제안

- 기능요청: [P2 AI 소스 제안 API](https://github.com/MEV-SW/mint-server/issues/14)

## 엔드포인트 목록
| Method | Path | 용도 | 인증 |
|---|---|---|---|
| POST | /api/v1/categories/{category_id}/source-suggestions | 카테고리에 맞는 소스 후보를 LLM으로 생성 | 기존 Bearer JWT, admin |

## 상세
설계 결정: 제안 결과를 별도 테이블에 저장하지 않는다. 이 엔드포인트는 후보 목록을 그때그때 생성해 응답으로만 돌려주고(상태 없음), [P3](https://github.com/MEV-SW/mint-server/issues/15)의 승인 엔드포인트가 클라이언트가 들고 있는 후보 데이터를 그대로 요청 본문에 받아 `Source`로 만든다. 이렇게 하면 이번 카드가 새 영속 모델을 발명하지 않고, L3(방법 자체를 실험해야 함) 카드의 범위를 좁게 유지할 수 있다 — 저장이 필요해지면 그건 실사용 후 별도 카드로 재분할한다.

### POST /api/v1/categories/{category_id}/source-suggestions
- Request: path parameter `category_id` 필수 UUID(활성 카테고리). request body `count` 선택 정수 기본 5·1~10.
- 카테고리가 존재하지 않거나 비활성(`is_active=false`)이거나 타 조직이면 404.
- LLM에는 카테고리 이름과 [기존 `industry`](https://github.com/MEV-SW/mint-server/blob/main/app/models/source.py) 맥락(현재는 `"EV"` 고정값)을 전달한다. 프롬프트·모델 선택은 기술스펙에서 정한다.
- 서버는 응답을 그대로 반환하기 전에 최소 검증을 한다: `url`이 http/https 형식이 아니면 후보에서 제외, 같은 조직의 기존 활성 `Source.url`과 정확히 일치하면 제외(중복 방지). 필터링 후 남은 후보가 0개여도 200과 빈 배열을 반환한다(오류 아님).
- Response 200:
```json
{"category_id":"11111111-1111-4111-8111-111111111111","candidates":[{"name":"예시 충전 인프라 뉴스","url":"https://example-news.com/rss","source_type":"rss","reason":"카테고리와 관련된 공개 RSS 피드"}],"generated_at":"2026-09-09T00:00:00Z"}
```
- 필드: `candidates[].name` 필수 string, `url` 필수 string(http/https), `source_type`은 기존 [`SourceType`](https://github.com/MEV-SW/mint-server/blob/main/app/models/enums.py) 값 중 하나(주로 `rss`|`webpage`|`news_page`), `reason` 필수 string(왜 이 소스를 제안했는지, admin이 승인 판단에 쓴다).
- 오류: 인증 없음·만료 401, admin 아님 403, 카테고리 없음/비활성/타 조직 404, `count` 범위 밖 422, LLM 호출 실패·타임아웃은 503 `{"detail":"소스 제안을 생성하지 못했습니다. 잠시 후 다시 시도해 주세요."}`(서버는 죽지 않고 재시도 가능한 오류로 응답).
- flag: 없음 — admin 전용 신규 엔드포인트라 기존 소비자에게 영향 없음.
