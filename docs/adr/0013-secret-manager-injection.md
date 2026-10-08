# ADR 0013 — Secret Manager 주입 전략 (--set-secrets 환경변수 주입)

- 상태(Status): Accepted
- 날짜: 2026-07-09
- 관련 구현: `app/config.py`(pydantic Settings — 환경변수 로드). ADR 0011 결정 2 의 후속 결정
- 관련 ADR: 0011(Docker — 비밀 2중 차단), 0012(Cloud Run 배포)

## 맥락 (Context)

로컬은 .env 로 비밀을 주입한다(개발 편의). 운영(Cloud Run)에서 비밀
(GOOGLE_CLIENT_SECRET, SESSION_SECRET_KEY)을 앱에 전달하는 경로를 정해야 한다.
ADR 0011 에서 `get_secret()`(env=="prod" 이면 Secret Manager 조회) 헬퍼 스켈레톤을
만들어 뒀고, 여기서 실제 배선 방식을 확정한다.

전제: 시크릿 리소스는 Secret Manager 에 등록(`google-client-secret`,
`session-secret-key`, user-managed replication asia-northeast3), 접근 권한은
**시크릿 단위** `roles/secretmanager.secretAccessor` 를 chatbot-app-sa 에만 부여
(프로젝트 레벨 부여 금지 — 미래 시크릿까지 자동 개방되므로 최소 권한 위반).

## 결정 (Decision)

**Cloud Run `--set-secrets` 로 환경변수 주입**을 채택한다. `get_secret()` 은
배선하지 않고 보존한다(환경변수로 주입하기 애매한 시크릿이 생기는 시점에 사용).

```
--set-secrets="GOOGLE_CLIENT_SECRET=google-client-secret:latest,SESSION_SECRET_KEY=session-secret-key:latest"
```

인스턴스 시작 시 Cloud Run 이 런타임 SA 권한으로 시크릿을 읽어 환경변수로 주입
→ pydantic Settings 가 .env 와 동일하게 읽음. 앱 코드 수정 0.

### 비교표 (가중치: 운영 첫 배포 + 솔로 + 10명 규모 기준)

| 기준 (가중치) | ① --set-secrets | ② get_secret() 직접 조회 | ③ 시크릿 볼륨 마운트 |
|---|---|---|---|
| 코드 침습성 (×3) | 5 (0줄) | 2 (auth.py/main.py import 시점 수정) | 2 (파일 읽기 신설) |
| 로컬/운영 경로 일치 (×3) | 5 | 3 (env 분기) | 2 |
| 실패 발견 시점 (×2) | 5 (기동 실패로 즉시) | 2 (런타임에 발견) | 4 |
| 보안 (×2) | 5 | 5 | 5 |
| 로테이션 (×1) | 2 (새 리비전 필요) | 5 (무중단) | 3 |
| 운영 단순성 (×2) | 5 | 3 | 3 |
| **가중 합계 (65)** | **61** | 39 | 40 |

②의 유일한 실질 우위(무중단 로테이션)는 재배포 1분·사용자 10명 서비스에서 가치가
없고, auth.py 가 import 시점에 client_secret 을 사용하는 구조라 배선 침습이 크다.
④ --set-env-vars 평문 주입(콘솔/describe 노출)과 ⑤ 이미지에 굽기는 보안상 논외.

## 트레이드오프 (Consequences)

- (−) 시크릿 변경 시 반영에 새 리비전(재배포) 필요 — latest 참조라도 기동 시 1회 주입.
- (−) 로컬 .env ↔ Secret Manager 두 곳 동기화 부담(값 변경 시 둘 다).
- (+) 코드 수정 0 + 로컬/운영 동일 코드 경로(pydantic env 로드) — dev/prod 차이 버그 방지.
- (+) 빠른 실패: 권한/시크릿 누락 시 인스턴스가 아예 못 뜸 → 배포 시점에 발견.
- (+) get_secret() prod 경로는 실증 완료(ENV=prod 강제 + ADC 로 1회 실호출 성공) —
  코드는 검증된 상태로 대기.

## 대안 (Alternatives considered)

- 위 비교표의 ②③④⑤. ②는 기각이 아니라 **보류**: 알림 웹훅 등
  "환경변수 주입이 부적합한 시크릿" 등장 시 1순위 도구.

## 후속 (Follow-ups)

- 시크릿 노출 의심 시 절차: 새 버전 추가 → 재배포(latest 자동) → 원본(OAuth secret)
  재발급 → git 히스토리 점검.
- 회사 GCP 이전: 시크릿 2종 재생성(새 프로젝트) + 시크릿 단위 IAM 재부여.
- Terraform 모듈화(로드맵): google_secret_manager_secret + IAM binding 모듈화.
