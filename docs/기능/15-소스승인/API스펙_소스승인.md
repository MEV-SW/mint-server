# API스펙_소스승인

- 기능요청: [P3 제안 소스 승인/반려 플로우](https://github.com/MEV-SW/mint-server/issues/15)

## 엔드포인트 목록
| Method | Path | 용도 | 인증 |
|---|---|---|---|
| POST | /api/v1/categories/{category_id}/source-suggestions/approve | AI 제안 소스 후보 하나를 승인해 실제 Source로 등록 | 기존 Bearer JWT, admin |

## 상세

**범위 조정 안내(카드 완료 판정 기준과의 차이)**: [P2](https://github.com/MEV-SW/mint-server/issues/14)가 제안 결과를 저장하지 않는 stateless 설계로 확정·구현됐다(제안은 매 호출마다 새로 생성되고 서버 어디에도 남지 않는다). 그래서 이 카드의 원래 완료 판정 기준에 있던 "반려 시 제안이 반려 상태로 남는다(재제안 근거 확인용)"는 구현할 대상이 없다 — 반려는 저장된 무언가를 바꾸는 동작이 아니라 admin이 그냥 승인하지 않고 넘어가는 것이므로 **별도 반려 엔드포인트를 두지 않는다**. 같은 후보가 나중에 다시 제안될 수 있다는 한계는 남는다(재제안 방지가 필요해지면 별도 카드로 재분할). 이 조정은 사용자 확인 대기다.

### POST /api/v1/categories/{category_id}/source-suggestions/approve
- Request: path parameter `category_id` 필수 UUID(활성 카테고리). request body는 [P2 응답의 candidate 하나](https://github.com/MEV-SW/mint-server/blob/main/docs/기능/14-ai소스제안/API스펙_AI소스제안.md)를 그대로 담는다 — `name` 필수 string, `url` 필수 string(http/https), `source_type` 필수(기존 [`SourceType`](https://github.com/MEV-SW/mint-server/blob/main/app/models/enums.py) 값), `reason` 선택(감사용 기록, 저장하지 않고 응답 로그 수준으로만 쓴다).
- 내부적으로 기존 [`SourceService.create_source`](https://github.com/MEV-SW/mint-server/blob/main/app/services/source_service.py)와 같은 기본값(trust_level=high, reliability_score=80 등)을 쓰되, `category_id`(이 경로의 값)·`category`(카테고리 이름 문자열, 하위 호환)·`discovery_type=ai_discovered`·`approved_by=현재 admin`·`approved_at=지금 시각`을 강제로 채운다. trust_level 등 세부값의 자동 산정은 하지 않는다(안 만들 것 목록).
- 같은 조직에 동일 `url`의 활성 소스가 이미 있으면 409로 거부한다(P2가 생성 시점에 걸러주지만 이 시점엔 다시 생겼을 수 있다).
- Response 200: 기존 `SourceRead`와 동일한 형태(신규 필드 `discovery_type: "ai_discovered"`, `approved_by`, `approved_at` 포함).
- 오류: 인증 없음·만료 401, admin 아님 403, 카테고리 없음/비활성/타 조직 404, `source_type` 값 오류·URL 형식 오류 422, URL 중복 409.
- flag: 없음.
