# RAG 품질 평가 — 골든셋 (초안)

`golden-set.json` 은 공개판 가상 샘플 문서 10개(`samples-by-folder/`)를 기준으로 쓴 **20문항 초안**이다. 아직 측정 스크립트와 수치는 없다. 문항은 문서당 1~3개, 표·목록 해석이 필요한 medium 8개, 두 문서 교차나 추론이 필요한 hard 3개, 문서에 답이 없어서 "근거 없음"이라고 해야 하는 negative 2개로 구성했다.

## 측정 계획

| 지표 | 정의 | 대상 단계 |
|---|---|---|
| Recall@5 | `expected_sources` 중 재정렬 top-5 에 들어온 비율 | 검색 → 재정렬 |
| 답변 정확도 | `expected_answer` 요지 포함 여부(사람이 O/X 채점) | 생성 |
| grounded 일치율 | 검증 단계의 grounded 플래그가 `expected_grounded` 와 같은 비율 | 검증 |
| negative 거부율 | negative 문항에서 근거 없음을 밝힌 비율 | 생성 + 검증 |

## 다음 단계

1. `scripts/eval_golden.py` — 문항을 순서대로 `/api/chat` 에 보내고 sources·answer·grounded 를 CSV 로 저장
2. Recall@5 와 grounded 일치율은 자동, 답변 정확도는 CSV 에서 사람이 채점
3. 결과를 README 로드맵에 수치로 반영. 운영 코퍼스용 골든셋은 사내 저장소에 별도 유지(실문서 질문은 공개하지 않음)
