# API스펙_이슈병합분리

- 기능요청: [B6 관리자 병합·분리 + 수정 이력](https://github.com/MEV-SW/mint-server/issues/33)
- 소속: [서버 기능묶음 #27](https://github.com/MEV-SW/mint-server/issues/27) / 프로젝트 [mint-release#9](https://github.com/MEV-SW/mint-release/issues/9)
- [B1 API스펙](https://github.com/MEV-SW/mint-server/blob/main/docs/기능/29-이슈데이터모델/API스펙_이슈데이터모델.md)이 자리만 잡아둔 `POST /issues/{id}/merge`·`POST /issues/{id}/split`을 여기서 확정한다.

## 전제

- `require_admin` — admin만 호출 가능(다른 role은 403). 소스 검토([`require_source_reviewer`](https://github.com/MEV-SW/mint-server/blob/main/app/core/permissions.py))와는 무관한 별도 권한.
- 모든 조정은 [`issue_revision`](https://github.com/MEV-SW/mint-server/blob/main/app/models/issue.py)에 `kind=admin_adjust`로 남는다.

## 엔드포인트 목록

| Method | Path | 용도 | 인증 |
|---|---|---|---|
| POST | /api/v1/issues/{issue_id}/merge | 다른 이슈를 이 이슈로 병합(이 이슈가 남음) | admin |
| POST | /api/v1/issues/{issue_id}/split | 구성 기사 하나를 새 이슈로 분리 | admin |

## POST /api/v1/issues/{issue_id}/merge

- Request: path `issue_id`(남는 이슈, "A"). body `{ "merge_with": "<이슈B UUID>" }`.
- 동작: B의 `issue_member` 전부를 A로 옮긴다. A의 `member_count`/`source_count`를 실제 멤버로 재계산한다. A의 `last_activity_at = max(A, B)`. B는 `status=merged`, `merged_into_id=A.id`로 바꾸고 멤버는 더 안 남는다. A에 `issue_revision(kind=admin_adjust, headline='"{B.title}" 이슈를 병합', actor_user_id=user.id)` 추가.
- Response 200: [B1 `IssueRead`](https://github.com/MEV-SW/mint-server/blob/main/docs/기능/29-이슈데이터모델/API스펙_이슈데이터모델.md) 형태로 병합 후 A.
- 오류: A 또는 B 없음·타 조직·이미 `merged` 404. `merge_with == issue_id`(자기 자신) 400. admin 아님 403.
- 이후 B를 `GET /issues/{B.id}`로 열면 기존 B1 계약대로 308 → A.

## POST /api/v1/issues/{issue_id}/split

- Request: path `issue_id`("A"). body `{ "post_id": "<분리할 기사 post UUID>" }`.
- 동작: `post_id`가 A의 구성 기사가 아니면 404. A의 구성 기사가 2건 미만이면 400(`{"detail":"구성 기사가 2건 미만이라 분리할 수 없습니다."}` — 프론트가 이미 버튼을 막지만 백엔드도 검증). 새 `Issue`("C") 생성(`title`=해당 post 제목, `status=active`, `edition_id`=A와 동일, `first_seen_at`=post.published_at, `member_count=1`). 그 `issue_member`를 A→C로 옮긴다. A의 `member_count`/`source_count` 재계산. A에 `issue_revision(kind=admin_adjust, headline='"{post.title}" 기사를 새 이슈로 분리')`. C에 `issue_revision(kind=first_report, headline=post.title, post_id=post.id)`(모든 이슈는 최소 first_report 1개 — B1 규칙 유지).
- Response 200: 새로 만들어진 C를 `IssueRead`로.
- 오류: A 없음·타 조직·`merged` 404. `post_id`가 A 소속 아님 404. 구성 기사 2건 미만 400. admin 아님 403.

## 되돌리기

이 카드는 되돌리기 API를 만들지 않는다(§6 — 없는 걸 그리지 않는다). 프론트([W6](https://github.com/MEV-SW/mint-web/issues/33))의 이력 뷰에도 "되돌리기" 버튼을 넣지 않는다.
