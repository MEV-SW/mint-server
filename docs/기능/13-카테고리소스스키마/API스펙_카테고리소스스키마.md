# API스펙_카테고리소스스키마

- 기능요청: [P1 카테고리-소스 연결 스키마 + CRUD 보강](https://github.com/MEV-SW/mint-server/issues/13)

## 엔드포인트 목록
| Method | Path | 용도 | 인증 |
|---|---|---|---|
| PATCH | /api/v1/categories/{category_id} | 카테고리 이름·정렬순서·활성 상태 수정 | 기존 Bearer JWT, admin |
| DELETE | /api/v1/categories/{category_id} | 카테고리 비활성화(소프트 삭제) | 동일 |

## 상세
공통: 기존 [카테고리 API](https://github.com/MEV-SW/mint-server/blob/main/app/api/v1/personalization.py)(`create_category`)와 동일하게 `require_admin`, 조직 범위 검증을 따른다. 카테고리 자체는 하드 삭제하지 않는다 — `is_active=false`만 사용해 과거 소스·통계 참조가 끊기지 않게 한다.

### PATCH /api/v1/categories/{category_id}
- Request: path parameter `category_id` 필수 UUID. request body `name` 선택 문자열(공백 trim, 1~128자), `sort_order` 선택 정수, `is_active` 선택 boolean.
- `name` 변경 시 기존 [`normalize_keyword`](https://github.com/MEV-SW/mint-server/blob/main/app/services/personalization_service.py) 정규화 규칙으로 `normalized_name`도 갱신하고, 조직 내 중복(`UniqueConstraint(organization_id, normalized_name)`)이면 409.
- Response 200: 기존 `CategoryRead`와 동일한 형태.
```json
{"id":"11111111-1111-4111-8111-111111111111","name":"충전 인프라","sort_order":3,"is_active":true,"is_featured":false,"selected":false,"is_discovered":false}
```
- 오류: 인증 없음·만료 401, admin 아님 403, 존재하지 않거나 타 조직 카테고리 404, 이름 중복 422/409(기존 검증 오류 형식과 통일).

### DELETE /api/v1/categories/{category_id}
- Request: path parameter `category_id` 필수 UUID. request body 없음.
- 내부 동작은 `is_active=false` 갱신이며 행을 지우지 않는다. 응답은 204(신규 소프트 삭제 성공)이다.
- 이 카테고리를 `category_id`로 참조하는 활성(`is_active=true`) `Source`가 하나라도 있으면 409 `{"detail":"이 카테고리를 참조하는 활성 소스가 있어 비활성화할 수 없습니다."}`로 거부한다. 소스를 먼저 다른 카테고리로 옮기거나 비활성화해야 한다.
- 오류: 인증 없음·만료 401, admin 아님 403, 존재하지 않거나 타 조직 404, 참조 소스 존재 409.

## 관련 스키마 변경 (기존 엔드포인트에 영향)
`Source`에 `category_id: UUID | None`(FK `news_categories.id`, nullable)을 추가한다. 기존 `category: str`(자유 텍스트, 기본값 `"general"`)는 그대로 유지해 하위 호환을 지키며, 신규 소스부터 `category_id`를 함께 채우는 걸 권장값으로 둔다. 기존 운영 소스의 `category` 문자열을 `category_id`로 일괄 재매핑하는 마이그레이션은 이 카드 범위 밖이다(별도 결정기록 대상).
- `SourceCreate`/`SourceUpdate`/`SourceRead`(기존 [app/schemas/source.py](https://github.com/MEV-SW/mint-server/blob/main/app/schemas/source.py))에 `category_id: UUID | None = None` 필드를 추가한다. 기존 `category` 필드·엔드포인트 경로·인증은 변경하지 않는다.
- `category_id`가 주어지면 존재하는 활성 카테고리인지 검증하고, 없거나 타 조직이면 기존 소스 생성/수정 오류 형식으로 404를 반환한다.
