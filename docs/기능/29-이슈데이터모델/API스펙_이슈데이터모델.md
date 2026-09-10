# API스펙_이슈데이터모델

- 기능요청: [B1 이슈 데이터 모델 + 조회 API 계약](https://github.com/MEV-SW/mint-server/issues/29)
- 소속: [서버 기능묶음 #27](https://github.com/MEV-SW/mint-server/issues/27) / 프로젝트 [mint-release#9](https://github.com/MEV-SW/mint-release/issues/9)
- 이 문서는 저장 모델과 웹 소비 계약만 정한다. 배정 로직은 [B4](https://github.com/MEV-SW/mint-server/issues/31), 변화 분류는 [B5](https://github.com/MEV-SW/mint-server/issues/32), 병합·분리 실행은 [B6](https://github.com/MEV-SW/mint-server/issues/33)에서 구현한다. 여기서는 엔드포인트가 존재하고 스텁이 계약대로 응답하는 수준까지다.

## 전제

- 근거 실험: [B2 FINDINGS.md](https://github.com/MEV-SW/mint-server/blob/main/scripts/experiments/issue_clustering/FINDINGS.md). near-dup 코사인 0.90, event 코사인 0.84, 시간창 ±7일, 2층 구조(중복/정정 vs 사건).
- 임베딩·kNN 인프라는 [B0](https://github.com/MEV-SW/mint-server/issues/28)에서 만든다. 이 문서는 B0가 `posts`에 임베딩을 붙이고 Elasticsearch에 `dense_vector`로 색인한다고 가정한다.
- 기존 인증·조직 스코프 규칙을 따른다: [`get_current_user`](https://github.com/MEV-SW/mint-server/blob/main/app/core/security.py), [`require_admin`](https://github.com/MEV-SW/mint-server/blob/main/app/core/permissions.py), 모든 조회는 `user.organization_id`로 범위 제한.
- 페이지네이션은 기존 [`PaginatedResponse`](https://github.com/MEV-SW/mint-server/blob/main/app/schemas/common.py) / [`GET /api/v1/posts`](https://github.com/MEV-SW/mint-server/blob/main/app/api/v1/posts.py)와 동일하게 `page` / `size`를 쓴다.

## feature flag

- `ISSUE_RADAR_ENABLED` (기본 `false`). [`PERSONALIZATION_ENABLED`](https://github.com/MEV-SW/mint-server/blob/main/app/core/config.py)와 같은 방식.
- `false`면 아래 엔드포인트 전부 404 (라우터 미등록). 기존 1면·뉴스·리포트·개인화 흐름은 이 값과 무관하게 동작한다.

## 저장 모델

새 테이블 4개. 전부 [`app/models/`](https://github.com/MEV-SW/mint-server/tree/main/app/models) 컨벤션(`UUID` PK, `organization_id` FK, `created_at`/`updated_at` server_default)을 따른다. `create_all`로 생성되며 Alembic 마이그레이션도 함께 추가한다(기존 [`alembic/versions/`](https://github.com/MEV-SW/mint-server/tree/main/alembic/versions)).

### issue — 사건

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID PK | |
| `organization_id` | UUID FK `organizations.id`, index | 조직 스코프 |
| `edition_id` | UUID FK `editions.id` NULL, index | 대표 분야. 배정 시 구성 기사 다수결로 채움([B4](https://github.com/MEV-SW/mint-server/issues/31)) |
| `title` | String(512) | 대표 제목. 최신 실질 변화 기사 제목으로 갱신 |
| `summary` | Text | AI 요약([B5](https://github.com/MEV-SW/mint-server/issues/32)가 갱신). 없으면 빈 문자열 |
| `status` | enum `IssueStatus` | `active` / `series`(정기 시리즈, 추적 노출 제외) / `merged`(다른 이슈로 병합됨) |
| `merged_into_id` | UUID FK `issues.id` NULL | `status=merged`일 때 대상 이슈. 리다이렉트용 |
| `member_count` | Integer | 구성 기사 수 (역정규화, 목록 정렬·표시용) |
| `source_count` | Integer | 구성 기사의 서로 다른 출처 수 (역정규화) |
| `first_seen_at` | DateTime(tz) | 가장 이른 구성 기사 `published_at` |
| `last_activity_at` | DateTime(tz), index | 마지막으로 기사가 붙거나 실질 변화가 생긴 시각. 목록 기본 정렬 키 |
| `last_change_kind` | enum `ChangeKind` NULL | 마지막 `issue_revision`의 종류 (아래) |
| `centroid_vector` | (ES에만) | 임베딩 평균. DB에는 저장하지 않고 ES `issues` 인덱스 문서로 유지([B0](https://github.com/MEV-SW/mint-server/issues/28)/[B4](https://github.com/MEV-SW/mint-server/issues/31)) |
| `created_at` / `updated_at` | DateTime(tz) | |

- index: `(organization_id, status, last_activity_at)`.

### issue_member — 이슈 ↔ 기사 (N:1)

기존 [`PostKeyword`](https://github.com/MEV-SW/mint-server/blob/main/app/models/personalization.py) 조인 패턴과 동일.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID PK | |
| `issue_id` | UUID FK `issues.id`, index | |
| `post_id` | UUID FK `posts.id`, index | |
| `role` | enum `MemberRole` | `origin`(첫 기사) / `development`(실질 변화) / `duplicate`(중복 보도) |
| `similarity` | Float | 배정 시 이슈 centroid와의 코사인 |
| `added_at` | DateTime(tz) | |

- `UniqueConstraint(issue_id, post_id)`. 한 기사는 한 이슈에만 속한다.

### issue_revision — 변화 이력

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID PK | |
| `issue_id` | UUID FK `issues.id`, index | |
| `kind` | enum `ChangeKind` | `first_report` / `development`(실질 변화) / `duplicates`(중복 보도 N건 묶음) / `correction`(정정) / `admin_adjust`(병합·분리) |
| `fact_type` | enum `FactType` NULL | `fact` / `ai_interpretation` / `needs_check`. `kind`가 `development`·`correction`일 때만 채움 |
| `headline` | String(512) | 변화 한 줄 |
| `note` | Text | 부연. `ai_interpretation`·`needs_check`는 여기에 근거 부재를 적음 |
| `post_id` | UUID FK `posts.id` NULL | 이 변화를 일으킨 기사. `duplicates`·`admin_adjust`는 NULL |
| `duplicate_post_ids` | JSON NULL | `kind=duplicates`일 때 묶인 기사 id 배열 |
| `actor_user_id` | UUID FK `users.id` NULL | `admin_adjust`일 때 수행자 |
| `prompt_version` | String(32) | `kind`가 AI 생성일 때. 기존 [`AIOutput.prompt_version`](https://github.com/MEV-SW/mint-server/blob/main/app/models/ai_output.py) 관례 |
| `occurred_at` | DateTime(tz), index | 타임라인 정렬 키. 기사 변화는 `published_at`, 관리자 조정은 실행 시각 |
| `created_at` | DateTime(tz) | |

- index: `(issue_id, occurred_at)`.

### user_issue_seen — 사용자별 추적·확인 커서

기존 [`PersonalReportView`](https://github.com/MEV-SW/mint-server/blob/main/app/models/personalization.py)(`popup_seen_at`/`opened_at`)와 같은 목적.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | UUID FK `users.id`, index | |
| `issue_id` | UUID FK `issues.id`, index | |
| `tracking` | Boolean, default true | 추적 on/off. 행이 있고 `false`면 명시적 해제 |
| `last_seen_at` | DateTime(tz) NULL | 마지막으로 이슈 상세를 연 시각. 이 값 이후의 `issue_revision`이 "새 변화" |
| `created_at` / `updated_at` | DateTime(tz) | |

- `UniqueConstraint(user_id, issue_id)`.

## 조직 공개 범위 (모든 조회 공통)

- 조회 대상은 `issue.organization_id == user.organization_id`인 이슈뿐이다.
- `edition_id`가 있는 이슈는 사용자가 볼 수 있는 분야([`require_edition_editor_any`](https://github.com/MEV-SW/mint-server/blob/main/app/core/permissions.py) 계산에 쓰는 `visible` edition 집합, 기존 [`_list_category_reads`](https://github.com/MEV-SW/mint-server/blob/main/app/api/v1/personalization.py))에 속할 때만 보인다.
- `issue_member` / `issue_revision`에서 참조하는 `post`가 숨김·삭제 상태([`PostStatus`](https://github.com/MEV-SW/mint-server/blob/main/app/models/enums.py))거나 조직 밖이면 응답의 근거 목록·`member_count`·`source_count`·피드 집계에서 **일관되게** 빠진다. 한 곳에서만 필터링하지 않는다.
- `status=merged` 이슈를 직접 조회하면 상세는 `merged_into_id`로 308 리다이렉트, 목록·피드에는 나오지 않는다.
- `status=series` 이슈는 목록에서 기본 제외(`include_series=true`로만 노출), 변화 피드에는 절대 나오지 않는다.

## 엔드포인트 목록

| Method | Path | 용도 | 인증 |
|---|---|---|---|
| GET | /api/v1/issues | 이슈 목록 (사건 단위) | Bearer JWT |
| GET | /api/v1/issues/{issue_id} | 이슈 상세 — 요약·근거·구성 기사 | Bearer JWT |
| GET | /api/v1/issues/{issue_id}/revisions | 변화 이력 (타임라인) | Bearer JWT |
| GET | /api/v1/issues/changes | 추적 이슈 중 "마지막 확인 이후" 변화 피드 | Bearer JWT |
| PUT | /api/v1/issues/{issue_id}/tracking | 추적 on/off | Bearer JWT |
| POST | /api/v1/issues/{issue_id}/seen | 확인 커서 갱신 (상세 이탈 시) | Bearer JWT |

- 병합·분리(`POST /issues/{id}/merge`, `POST /issues/{id}/split`)는 [B6](https://github.com/MEV-SW/mint-server/issues/33) API스펙에서 정의한다. 여기서는 자리만 알린다.
- 1면·리포트 연동: [B7](https://github.com/MEV-SW/mint-server/issues/34)에서 `GET /api/v1/issues/changes`를 재사용하며 새 엔드포인트를 만들지 않는다.

## 상세

공통: `ISSUE_RADAR_ENABLED=false`면 전부 404. 인증 없음·만료 401. 응답 시간·정렬은 조직·분야 필터를 적용한 뒤 계산한다.

### GET /api/v1/issues

- Request: query parameter.
  - `page` 정수 기본 1 (ge 1), `size` 정수 기본 20 (ge 1, le 100).
  - `filter` 문자열 선택 — `all`(기본) / `tracked`(내 추적 이슈) / `changed`(내 추적 이슈 중 `last_activity_at > user_issue_seen.last_seen_at`).
  - `edition_id` UUID 선택 — 특정 분야만.
  - `change_state` 문자열 선택 — `development` / `correction` / `duplicates_only` / `quiet` 중 하나. `issue.last_change_kind`와 `last_activity_at` 기준 파생.
  - `include_series` boolean 기본 false.
- 정렬: `last_activity_at` 내림차순 고정.
- Response 200: 기존 `PaginatedResponse` 형태.
```json
{
  "items": [
    {
      "id": "9f1c...",
      "title": "미국, 중국산 전기차 시장 차단 논의",
      "summary": "완성차 단체의 영구 차단 요구와 회담 앞둔 개방설이 맞선다.",
      "edition_id": "3a2b...",
      "member_count": 6,
      "source_count": 3,
      "first_seen_at": "2026-09-02T01:10:00Z",
      "last_activity_at": "2026-09-09T23:20:00Z",
      "last_change_kind": "development",
      "change_state": "development",
      "tracking": true,
      "has_unseen_change": true
    }
  ],
  "total": 28,
  "page": 1,
  "size": 20,
  "pages": 2
}
```
- `tracking` / `has_unseen_change`는 요청 사용자의 `user_issue_seen`으로 계산한다. 행이 없으면 `tracking=false`, `has_unseen_change=false`.
- 오류: 잘못된 `filter`·`change_state` 값 422.

### GET /api/v1/issues/{issue_id}

- Request: path parameter `issue_id` 필수 UUID.
- Response 200:
```json
{
  "id": "9f1c...",
  "title": "미국, 중국산 전기차 시장 차단 논의",
  "summary": "완성차 단체의 영구 차단 요구와 회담 앞둔 개방설이 맞선다.",
  "summary_confidence": "medium",
  "edition_id": "3a2b...",
  "status": "active",
  "member_count": 6,
  "source_count": 3,
  "first_seen_at": "2026-09-02T01:10:00Z",
  "last_activity_at": "2026-09-09T23:20:00Z",
  "tracking": true,
  "last_seen_at": "2026-09-08T11:14:00Z",
  "has_unseen_change": true,
  "members": [
    {
      "post_id": "aa11...",
      "title": "\"제발 중국산 막아 달라\" 美 완성차, 의회에 영구 차단 요구",
      "source_name": "오토헤럴드",
      "board_type": "trusted",
      "role": "origin",
      "published_at": "2026-09-02T01:10:00Z",
      "original_url": "https://...",
      "unverified": false
    }
  ]
}
```
- `members`는 `role` 무관 전체를 `published_at` 오름차순으로. `board_type=community`면 `unverified=true`.
- `summary_confidence`는 [B5](https://github.com/MEV-SW/mint-server/issues/32) 산출. 없으면 `null`.
- 오류: `issue_id` 없음·타 조직·안 보이는 분야 404. `status=merged`면 308 `Location: /api/v1/issues/{merged_into_id}`.

### GET /api/v1/issues/{issue_id}/revisions

- Request: path parameter `issue_id` 필수 UUID. query parameter `page` 기본 1, `size` 기본 50 (le 200).
- 정렬: `occurred_at` 오름차순 고정 (타임라인 순서).
- Response 200: `PaginatedResponse`. 각 항목:
```json
{
  "id": "r001",
  "kind": "development",
  "fact_type": "fact",
  "headline": "트럼프, 시진핑 회담 앞두고 중국 전기차 시장 개방설 제기",
  "note": "앞선 영구 차단 요구와 방향이 반대인 신호. 회담 일정은 공개되지 않음.",
  "post_id": "bb22...",
  "post_title": "\"트럼프, 中 전기차에 미국 문 여나\"",
  "source_name": "오토헤럴드",
  "duplicate_post_ids": null,
  "actor": null,
  "occurred_at": "2026-09-09T08:20:00Z",
  "is_unseen": true
}
```
- `kind=duplicates`면 `headline`은 `"중복 보도 3건"` 식, `duplicate_post_ids` 채움, `post_id`/`fact_type` null.
- `kind=admin_adjust`면 `actor`에 `{ "user_id": "...", "name": "..." }`, `headline`은 `"관리자 조정 — 기사 1건 분리"` 식.
- `is_unseen`은 `occurred_at > user_issue_seen.last_seen_at`. 커서 없으면 전부 `false`.
- 오류: 상세와 동일 (404 / 308).

### GET /api/v1/issues/changes

추적 이슈 중 마지막 확인 이후 변화가 있는 것만. 1면 변화 밴드([W5](https://github.com/MEV-SW/mint-web/issues/32))와 [B7](https://github.com/MEV-SW/mint-server/issues/34) 리포트 연동이 이 하나를 쓴다.

- Request: query parameter.
  - `since` ISO8601 datetime 선택 — 주면 이 시각 이후 변화만. 없으면 각 이슈의 `user_issue_seen.last_seen_at` 기준.
  - `limit` 정수 기본 20 (le 50).
- 대상: `user_issue_seen.tracking=true` 이고 `issue.last_activity_at > 기준시각` 인 이슈. `status=active`만. `series`·`merged` 제외.
- 정렬: `last_activity_at` 내림차순.
- Response 200:
```json
{
  "since": "2026-09-08T11:14:00Z",
  "items": [
    {
      "id": "9f1c...",
      "title": "미국, 중국산 전기차 시장 차단 논의",
      "edition_id": "3a2b...",
      "last_activity_at": "2026-09-09T23:20:00Z",
      "new_revision_count": 3,
      "top_change_kinds": ["development", "ai_interpretation", "needs_check"],
      "new_member_count": 2
    }
  ]
}
```
- `top_change_kinds`는 새 `issue_revision`의 `fact_type`(없으면 `kind`) 중복 제거, 최대 3개.
- 변화가 없으면 `items: []` — 이 경우 밴드를 그리지 않는다(빈 목록과 오류를 구분).
- 오류: 잘못된 `since` 형식 422.

### PUT /api/v1/issues/{issue_id}/tracking

- Request: path parameter `issue_id` 필수 UUID. request body `{ "tracking": true|false }` 필수 boolean.
- `user_issue_seen` 행이 없으면 만들고, 있으면 `tracking`만 갱신. `last_seen_at`은 건드리지 않는다.
- Response 200: `{ "issue_id": "9f1c...", "tracking": true }`.
- 오류: 이슈 없음·타 조직·안 보이는 분야 404. `status=merged`면 404 (병합된 이슈는 추적 불가, 대상 이슈를 추적).

### POST /api/v1/issues/{issue_id}/seen

- Request: path parameter `issue_id` 필수 UUID. request body 없음.
- `user_issue_seen` 행이 없으면 `tracking=true`로 만들며 `last_seen_at = now()`. 있으면 `last_seen_at`만 `now()`로. 상세를 여는 것만으로 추적이 켜지지는 않되(행 없이 상세만 보는 경우), **명시적 seen 호출**은 추적 의사로 본다 — 이 판단은 [W4](https://github.com/MEV-SW/mint-web/issues/31) 화면정의서와 맞춘다.
- Response 204.
- 오류: 이슈 없음·타 조직·안 보이는 분야 404.

## 웹 계약 정렬 (W1)

[W1 화면정의서](https://github.com/MEV-SW/mint-web/issues/28)가 이 응답 필드를 그대로 소비한다. 특히:
- 목록 행 = `GET /issues`의 `items[]` (배지는 `change_state`, 별표는 `tracking`, "변화 있음" 표식은 `has_unseen_change`).
- 상세 = `GET /issues/{id}` + `GET /issues/{id}/revisions`. "여기까지 확인함" 선은 `last_seen_at`, 그 아래 NEW는 `revisions[].is_unseen`.
- 1면 밴드 = `GET /issues/changes` (`items` 비면 밴드 없음).
- W1에서 필드가 부족하면 이 문서를 고쳐 맞춘다. 한쪽만 바꾸지 않는다.
