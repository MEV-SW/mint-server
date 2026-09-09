# API스펙_이슈조회

- 기능요청: [B1 이슈 조회 계약과 저장 모델](https://github.com/MEV-SW/mint-server/issues/4)

## 엔드포인트 목록
| Method | Path | 용도 | 인증 |
|---|---|---|---|
| GET | /api/v1/stories | 공개 근거가 있는 이슈(`story`, 개발 작업 이슈와 구별) 목록 | 기존 Bearer JWT, 활성 사용자 |
| GET | /api/v1/stories/{story_id} | 요약·근거 상세 | 동일 |

## 상세
공통: 기존 [개인화 API](https://github.com/MEV-SW/mint-server/blob/main/app/api/v1/personalization.py)·[예외 형식](https://github.com/MEV-SW/mint-server/blob/main/app/core/exceptions.py)을 따른다. JWT에서 사용자·조직을 결정하고 request에서 조직을 지정하지 않는다. 기존 게시물 공개·MembershipService 권한을 목록·검색·요약·출처 개수에 모두 적용하며, 범위 밖 근거를 제거한 결과 읽을 수 있는 기사가 없으면 해당 이슈를 노출하지 않는다. 요약은 공개 가능한 근거만으로 만들고, 접근 제한 자료가 섞인 저장 요약은 재사용하지 않고 `summary=null`·`summary_status="unavailable"`로 반환한다. UUID 식별자는 문자열, 모든 시각은 UTC ISO 8601이다(웹은 Asia/Seoul로 표시). 공통 오류: 인증 없음·만료 401, 비활성 계정 등 기존 접근 거절 403, 파라미터 검증 오류 422(기존 FastAPI 형식), 일시적 조회 실패 503 `{"detail":"잠시 후 다시 시도해 주세요."}`. 기존 뉴스·토픽·리포트 response는 변경하지 않는다. 변화 이력·추적 mutation·관리자 교정은 다른 카드의 별도 계약이다.

### GET /api/v1/stories
- Request: query parameter `q` 선택 문자열(공백 trim, 최대 200자, 빈 문자열은 검색 없음), `category_id` 선택 UUID(기존 category ID), `page` 정수 기본 1·최소 1, `page_size` 정수 기본 20·1~100.
- 정렬은 `updated_at DESC, id DESC`. `updated_at`은 공개 가능한 이슈 콘텐츠 변경 시각이며 개인의 읽음 처리 시각이 아니다. 목록을 보는 동안 새 이슈가 들어오면 페이지 경계가 바뀔 수 있고 새로고침으로 최신화한다.
- `source_count`는 해당 사용자에게 보이는 서로 다른 source ID 수이며 진실성 점수가 아니다. `article_count`는 보이는 게시물 수다.
- Response 200:
```json
{"items":[{"id":"11111111-1111-4111-8111-111111111111","title":"충전 기술 관련 사건 예시","summary":"공개 기사에서 확인한 요약 예시","summary_status":"ready","article_count":3,"source_count":2,"updated_at":"2026-09-08T00:00:00Z"}],"total":1,"page":1,"page_size":20}
```
- 필드: `id/title` 필수 string, `summary` string|null, `summary_status`는 `ready|pending|unavailable`, 개수는 0 이상의 정수, 시각은 필수 string. `ready` 요약만 화면에 표시한다.
- 빈 결과 및 범위를 넘는 페이지: 200 `{"items":[],"total":0,"page":1,"page_size":20}` 형태. total·page는 실제 검색 전체 건수·요청 페이지 값을 유지한다.
- 오류: 공통 오류. 존재하지 않거나 사용자 범위 밖 category ID는 200 빈 결과를 반환해 존재 여부를 노출하지 않는다.
- flag: `ISSUE_RADAR_ENABLED` 제안, 기본 OFF. OFF이면 403 `{"detail":"이슈 레이더 기능이 비활성화되어 있습니다."}`. 기존 API는 변경하지 않는다.

### GET /api/v1/stories/{story_id}
- Request: path parameter `story_id` 필수 UUID. query parameter `article_page` 정수 기본 1·최소 1, `article_page_size` 기본 20·1~100.
- Response 200:
```json
{"id":"11111111-1111-4111-8111-111111111111","title":"충전 기술 관련 사건 예시","summary":"공개 근거에 기반한 요약 예시","summary_status":"ready","updated_at":"2026-09-08T00:00:00Z","source_count":1,"article_count":1,"articles":{"items":[{"post_id":"22222222-2222-4222-8222-222222222222","title":"근거 기사 예시","source_name":"출처 예시","original_url":"https://example.com/article","collected_at":"2026-09-08T00:00:00Z"}],"total":1,"page":1,"page_size":20},"summary_post_ids":["22222222-2222-4222-8222-222222222222"]}
```
- `summary_post_ids`는 요약 근거 게시물 UUID 배열이다. 현재 근거 페이지 밖 ID도 내부 기사 상세에서 권한을 재검사한다. 요약 불가 시 빈 배열이다.
- 기사 `post_id/title` 필수 string, `source_name/original_url` string|null, `collected_at` 필수 UTC 시각. 원문 URL은 http/https만 허용하며 null일 때 외부 링크를 제공하지 않는다.
- articles 정렬은 `collected_at DESC, post_id DESC`. 빈 페이지는 items=[], total은 실제 보이는 기사 수다.
- 오류: 잘못된 UUID/페이지 422. 없는 이슈·타 조직·공개 근거가 없는 이슈 모두 404 `{"detail":"이슈를 찾을 수 없습니다."}`. 그 외 공통 오류.
- flag: 공통 flag 정책과 동일.
