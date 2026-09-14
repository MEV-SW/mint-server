# 이슈 클러스터링 실험 (B2 타임박스)

프로젝트 정의 [mint-release #1](https://github.com/MEV-SW/mint-release/issues/1) 의 서버 B2
"사건 묶음 방법을 실험으로 찾는다" 에 대한 재현 가능한 실험.

**질문:** 임베딩 + 코사인 유사도로 "같은 사건" 기사를 자동으로 묶을 수 있는가?
방법이 되는가, 임계값은 얼마인가, 잔여 불확실성은 무엇인가.

결론은 [FINDINGS.md](FINDINGS.md).

## 파이프라인

```
fetch_corpus.py   seed.py의 실제 RSS 피드를 지금 크롤 → data/corpus.jsonl
embed_corpus.py   Bedrock cohere.embed-multilingual-v3 (us-east-1) → data/embeddings.npy
cluster.py        near-dup(≥0.90) + event 클러스터(≥0.84, 7일창) + 임계값 스윕
                  → data/clusters.csv, data/clusters_for_review.md
```

near-dup / event 두 층으로 나눈 이유: 전자는 `issue_revision`(중복·정정 감지),
후자는 `issue`(사건 묶음) 데이터 모델에 각각 대응한다.

## 실행

```bash
cd MINT_Backend
.venv/bin/python scripts/experiments/issue_clustering/fetch_corpus.py --days 21 --per-feed 80
.venv/bin/python scripts/experiments/issue_clustering/embed_corpus.py --region us-east-1
.venv/bin/python scripts/experiments/issue_clustering/cluster.py --event-sim 0.84 --window 7
```

- `numpy` 필요 (`.venv/bin/pip install numpy`). 그 외는 백엔드 기존 의존성(httpx, feedparser, boto3).
- 임베딩은 `.env`의 `BEDROCK_API_KEY`를 사용. Cohere 임베딩 모델이 `ap-northeast-2`에
  없어서 `--region us-east-1` 필수. Titan 대안: `--model amazon.titan-embed-text-v2:0`.
- `data/`는 실험 산출물이라 커밋 대상 아님 (`.gitignore` 참고).

## 한계 (이 실험이 증명하지 못하는 것)

- 로컬 DB가 없어 코퍼스는 RSS 단일 스냅샷이며 **관련성 게이트 전** 상태다. 운영 분포와 다르다.
- 정답 라벨이 없어 precision은 소표본 육안 평가, recall은 사실상 미측정.
- 제목 + RSS 요약만 사용. 운영은 `raw_content` + AI 요약 + 키워드가 있어 신호가 더 풍부하다.

바로 이 두 한계를 좁히는 게 [B3](https://github.com/MEV-SW/mint-server/issues/30)다.

## B3 — 운영표본 재보정 + 골든 평가셋

B2와 같은 임베딩 파이프라인을 **실제 DB posts**(post-분류, post-AI요약)로 재현하고,
사람이 라벨링한 쌍으로 precision/recall을 실측해 임계값을 확정한다.

```
fetch_operational_sample.py  DB에서 posts 300~500건 → data/op_corpus.jsonl
embed_corpus.py --corpus op_corpus.jsonl --tag op --region us-east-1
                              → data/op_embeddings.npy
build_candidate_pairs.py     유사도 구간별 후보쌍(~150개, 저유사도 포함) → data/op_candidates.jsonl
label_cli.py                 사람이 하나씩 라벨링(n/e/u/s) → data/op_labels.jsonl (재개 가능)
calibrate_thresholds.py      임계값 스윕 표 출력 → --commit으로 확정
                              → golden_set.jsonl, thresholds.json (커밋 대상)
```

`golden_set.jsonl`·`thresholds.json`은 `data/` **밖**(커밋 대상)이고, [`tests/test_golden_clustering.py`](../../../tests/test_golden_clustering.py)가
이 둘을 읽어 CI 회귀로 돈다 — 둘 다 없으면 스킵, 있으면 기록된 precision/recall 기준을 지키는지 검증.

### B3 실행

```bash
cd MINT_Backend
.venv/bin/python scripts/experiments/issue_clustering/fetch_operational_sample.py --days 30 --limit 400
.venv/bin/python scripts/experiments/issue_clustering/embed_corpus.py --corpus op_corpus.jsonl --tag op --region us-east-1
.venv/bin/python scripts/experiments/issue_clustering/build_candidate_pairs.py --tag op --per-bucket 25
.venv/bin/python scripts/experiments/issue_clustering/label_cli.py --tag op
# 표를 보고 임계값을 정한 뒤:
.venv/bin/python scripts/experiments/issue_clustering/calibrate_thresholds.py --tag op \
    --near-dup 0.XX --event 0.XX --commit --decided-by <이름>
```

`fetch_operational_sample.py`는 `.env`의 `DATABASE_URL`(운영 DB일 수 있음)을 읽기 전용으로 조회한다 — 쓰기 없음.
라벨링(`label_cli.py`) 자체는 사람이 해야 한다 — "담당자가 수치 합격선을 정한다(임의 수치 아님)"가 B3의 완료 판정 기준이다.
