## What
<!-- 이 PR이 무엇을 하는지 한두 줄 -->

## Why
<!-- 왜 필요한지 / 어떤 단계/이슈와 연결되는지 -->

## How
<!-- 핵심 구현 방식, 주요 결정 -->

## Trade-offs
<!-- 포기한 것, 알려진 한계, 후속 단계로 미룬 것 -->

## Self-Review Checklist
- [ ] `.env` / 비밀 JSON이 diff에 없음 (★ 필수 ★)
- [ ] `ruff check .` 통과
- [ ] `black --check .` 통과
- [ ] `mypy app` 통과
- [ ] `pytest` 통과
- [ ] 새 라이브러리 추가 시 `requirements.txt` + `.env.example` 갱신
- [ ] 새 설계 결정 시 ADR 작성/갱신
- [ ] Conventional Commits 형식 커밋

## Related
<!-- 관련 이슈/ADR/단계 번호 (예: closes #1, ADR 0005, 4단계) -->
