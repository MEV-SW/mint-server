# API스펙_변화분류

- 기능요청: [B5 변화 분류](https://github.com/MEV-SW/mint-server/issues/32)
- 소속: [서버 기능묶음 #27](https://github.com/MEV-SW/mint-server/issues/27) / 프로젝트 [mint-release#9](https://github.com/MEV-SW/mint-release/issues/9)
- 새 REST 엔드포인트는 없다 — [B4](https://github.com/MEV-SW/mint-server/issues/31) 배정 로직 안에서만 동작.

## 범위

B4가 이미 코사인 임계값으로 근접중복(≥0.90)/실질변화(0.84~0.90)를 가른다. B5는 그중 **실질변화(`kind=development`)로 배정된 경우에만** LLM을 한 번 더 불러 다음 두 가지를 채운다:

1. **요지**(`headline`) — "이 기사가 사건에 무엇을 더했는지" 한 줄. `Issue.summary`도 이 값으로 갱신(모델 주석 "AI 요약, B5가 갱신"과 일치).
2. **유형**(`fact_type`) — `fact`(본문에 명시된 사실) / `ai_interpretation`(종합 해석) / `needs_check`(근거 부족·검증 필요).

근접중복(`kind=duplicates`)은 이 카드가 손대지 않는다 — B4의 임계값 판단만으로 "중복으로 접힘"이 이미 완료 판정 기준을 만족한다.

## 프롬프트 계약

`app/prompts/issue_change_classify_v1.md` — 입력: 기존 이슈 제목·요약 + 새 기사 제목·본문. 출력 JSON: `{"headline": str, "note": str, "fact_type": "fact"|"ai_interpretation"|"needs_check"}`. `LLMClient.classify_issue_change(issue_title, issue_summary, new_title, new_body)` — Bedrock/Gemini/Mock 세 구현 다 있음(기존 `classify_post_content` 등과 동일한 `LLMClient` 추상 인터페이스 패턴).

## 실패 시 동작

LLM 호출이 실패하면(자격증명·쿼터·타임아웃) **배정 자체는 그대로 진행**하고 `headline=post.title`, `fact_type=None`, `note=""`로 떨어진다 — B4가 이미 했던 배정(합류 여부·member_count 등)을 되돌리지 않는다. "원문에 없는 수치는 추가 확인 필요로 표시된다"는 완료 판정은 LLM이 정상 응답할 때의 분류 규칙이고, LLM 자체가 죽었을 때는 분류를 안 하는 쪽(None)을 택했다 — 잘못된 fact_type을 지어내는 것보다 안전하다.
