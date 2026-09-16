# API스펙_추적변화피드

- 기능요청: [B7 추적·변화 피드 API + 공개범위 일관 적용](https://github.com/MEV-SW/mint-server/issues/34)
- 소속: [서버 기능묶음 #27](https://github.com/MEV-SW/mint-server/issues/27) / 프로젝트 [mint-release#9](https://github.com/MEV-SW/mint-release/issues/9)

## B1 스펙 재검토

[B1 API스펙](https://github.com/MEV-SW/mint-server/blob/main/docs/기능/29-이슈데이터모델/API스펙_이슈데이터모델.md#L113)은 "1면·리포트 연동은 `GET /api/v1/issues/changes` 재사용, 새 엔드포인트 없음"이라고 미리 적어뒀다.
1면은 이 가정이 맞는다 — 로그인 사용자 개인 화면이고, `GET /issues/changes`는 정확히 그 사용자의 `user_issue_seen`(개인 추적 커서) 기준으로 동작한다. 프론트가 이미 이 엔드포인트로 1면 변화 밴드를 구현했다([W5](https://github.com/MEV-SW/mint-web/issues/32), 완료).

리포트는 이 가정이 안 맞는다. 데일리 리포트는 조직 전체에 한 번 생성돼 발송되는 자료라 "이 리포트를 보는 특정 사용자의 추적 커서"라는 개념 자체가 없다. `GET /issues/changes`를 그대로 리포트 생성 배치에 붙이면 어느 사용자 기준으로 호출할지가 애매해진다.
그래서 **HTTP 엔드포인트는 늘리지 않는다는 결정은 유지**하되(요청서의 "안 만들 것: 새 엔드포인트"), 리포트 쪽만 조직 단위로 동작하는 내부 서비스 메서드를 하나 추가해 리포트 생성 배치가 직접 호출하게 한다.

## 엔드포인트 목록

새 HTTP 엔드포인트 없음. 기존 3개를 그대로 쓴다(B1 스펙, 변경 없음).

| Method | Path | 용도 | 인증 |
|---|---|---|---|
| GET | /api/v1/issues/changes | 1면 변화 밴드 (개인 추적 커서 기준) | Bearer JWT |
| PUT | /api/v1/issues/{issue_id}/tracking | 추적 on/off | Bearer JWT |
| POST | /api/v1/issues/{issue_id}/seen | 확인 커서 갱신 | Bearer JWT |

## 내부 연동 (신규) — `IssueService.list_org_changes`

- 호출자: [`report_service.py`](https://github.com/MEV-SW/mint-server/blob/main/app/services/report_service.py) 리포트 생성 배치. HTTP 엔드포인트가 아니라 서버 내부 메서드라 인증 파라미터 없음, 대신 `organization_id`를 직접 받는다.
- Request(함수 인자): `organization_id: UUID`, `since: datetime`(리포트 대상일 00:00 KST).
- 대상: `Issue.organization_id == organization_id`, `status == active`, `last_activity_at > since`. 개인 추적(`user_issue_seen.tracking`) 여부는 안 본다 — 조직 전체 활동 기준.
- 공개범위: [`MembershipService.visible_edition_ids`](https://github.com/MEV-SW/mint-server/blob/main/app/services/issue_service.py#L74-L76)와 동일한 `_edition_visible` 필터를 조직 단위로 적용(비공개 에디션 소속 이슈 제외) — 사용자 파라미터가 없으므로 "조직에 하나라도 비공개 아닌 에디션 멤버십이 있으면 보임"이 아니라 **에디션 자체의 `visibility` 플래그**로 판단한다(사용자별 멤버십 화이트리스트가 아니라 에디션이 조직 공개인지만 본다). 이 부분이 `_edition_visible`의 현재 시그니처(사용자별 `visible` 집합)와 달라 구현 단계에서 헬퍼를 분리한다.
- Response(반환 타입): `list[IssueChangeSummary]` — `{ issue_id, title, edition_id, last_change_kind, top_revision_kinds[:3], member_count }`. 기존 `IssueChangesResponse.items`([B1 스펙](https://github.com/MEV-SW/mint-server/blob/main/docs/기능/29-이슈데이터모델/API스펙_이슈데이터모델.md) 참고)와 필드 구성은 맞추되 `tracking`/`has_unseen_change`(개인 필드)는 뺀다.
- 오류: 없음(내부 호출). `organization_id`에 해당하는 활동 이슈가 없으면 빈 리스트.

## report_service 통합

- [`_normalize_report_result`](https://github.com/MEV-SW/mint-server/blob/main/app/services/report_service.py#L577-L609)가 LLM `recommendations`를 정규화할 때, `list_org_changes` 결과에서 `related_post_ids`가 걸치는 이슈를 찾아 `related_issue_ids`를 채운다. 매치가 없으면 필드 생략 — LLM 추천 자체를 이슈 데이터로 대체하지 않는다.
- `DailyReportItemRead`/`key_changes` 항목 스키마에 `related_issue_ids: list[UUID] | None = None` 추가. 기존 `related_post_ids`는 유지(하위호환, MINOR 변경).
- flag: 기존 `issue_radar_enabled`가 꺼져 있으면 `list_org_changes` 호출을 건너뛰고 `related_issue_ids`는 항상 없음(오늘 배포본과 동일 동작 보장).

## 완료 판정 기준과의 대응

- "추적 이슈 중 커서 이후 변화만 피드로, 상세 열면 커서 갱신" — 이미 구현됨(B1, 변경 없음).
- "비공개 조직·게시물은 모든 응답에서 일관되게 빠진다" — 기존 3개 엔드포인트는 이미 만족. `list_org_changes` 신규 경로도 위 공개범위 절 기준으로 구현·검증한다.
- "1면·리포트가 이슈 피드를 소비할 엔드포인트가 준비된다" — 1면은 이미 충족(B1). 리포트는 이 문서의 `list_org_changes` + report_service 통합으로 충족한다.
