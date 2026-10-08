# ADR 0012 — Cloud Run 배포 전략 (direct IAP + Workload Identity)

- 상태(Status): Accepted
- 날짜: 2026-07-09
- 관련 구현: `Dockerfile`(port 8080), `app/utils/auth_utils.py`(IAP 헤더 처리)
- 관련 ADR: 0002(OAuth 개인 인증), 0009(Rate Limit — 인스턴스 수 영향), 0011(Docker 패키징)

## 맥락 (Context)

ADR 0011 에서 만든 컨테이너 이미지를 운영 환경에 처음 배포한다. 요구사항:
(1) 허가된 사용자만 접근(현재 본인 1명, 회사 GCP 이전 후 임직원 7~10명),
(2) 서비스 계정 키 파일 원천 제거, (3) 비용 최소(개인 결제, 예산 ₩50,000/월),
(4) 사용자 10명 규모에 맞는 스케일링.

초기 계획은 "IAP + (Ingress 결정: LB 검토)"였으나, 계획 수립 이후
Cloud Run에 IAP를 직접 붙이는 방식이 정식 제공되기 시작해(콘솔 토글 / gcloud `--iap`)
LB 없이 IAP를 쓸 수 있게 됐다 → 원안 재검토가 필요했다.

## 결정 (Decision)

1. **인증/인가: Cloud Run direct IAP** (LB 미사용)
   - `--no-allow-unauthenticated` + 서비스 보안 탭에서 IAP ON.
   - 조직 없는(개인) 프로젝트는 최초 활성화 시 OAuth 클라이언트 자동 구성이
     콘솔에서만 가능 → 최초 1회 콘솔, 이후 IAM 은 gcloud.
   - 접근 부여: `roles/iap.httpsResourceAccessor` 를 `user:<ADMIN_EMAIL>` 에게만.
     (회사 GCP 이전 후 `domain:example.com` 한 줄 추가로 전 임직원 개방)
   - IAP 서비스 에이전트(`service-<PROJECT_NUMBER>@gcp-sa-iap...`)에 `roles/run.invoker`.
2. **신원: Workload Identity** — `--service-account=chatbot-app-sa@<PROJECT_ID>.iam.gserviceaccount.com`.
   키 파일이 이미지/컨테이너/시크릿 어디에도 존재하지 않는다. 앱의 모든 ADC 호출
   (Firestore/Vertex/GCS/Secret 주입)이 런타임 SA 신원으로 나간다.
3. **스케일: min=0 / max=2** (초기 계획 max=5 에서 하향)
   - min=0: 콜드스타트 허용(비용 우선). startup-cpu-boost 기본 ON 이 완화해 줌.
   - max=2: rate limit(ADR 0009)이 인스턴스별 인메모리 → 인스턴스 수 = 한도 배수.
     max=5 면 최악 1분 25회. 10명 × 동시성 80 이면 실질 1개로 충분, 2는 여유분.
     비정상 트래픽 시 비용 상한 효과도 겸함.
4. **리소스: 1 vCPU / 1Gi / port 8080** (Dockerfile 정합).
5. **URL: run.app 결정형 URL 사용, 커스텀 도메인 스킵**
   - `https://drive-chatbot-<PROJECT_NUMBER>.asia-northeast3.run.app` 하나로 통일
     (해시형 URL 혼용 금지 — localhost/127.0.0.1 혼용의 mismatching_state 교훈 재적용).
   - 개인 GCP PoC 단계라 도메인 실익 없음. 회사 GCP 이전 시 URL 이 재발급되므로
     `chatbot.example.com` 매핑은 그 시점에.
6. **배포 절차의 순환 의존 해소**: OAuth redirect URI 는 배포 전엔 알 수 없음 →
   1차 배포(redirect 기본값) → URL 확보 → 콘솔에 URI 등록 + `--update-env-vars` 로
   2차 리비전. (`--set-env-vars` 는 전체 교체라 금지, `--update-env-vars` 는 병합)

## 트레이드오프 (Consequences)

- (−) min=0 콜드스타트: 5분+ 미사용 후 첫 응답 지연. 사용 빈도 증가 시 min=1 재검토
      (단, min=1 은 24시간 과금 — 비용 경고).
- (−) direct IAP 는 Cloud Armor(WAF)/고급 라우팅 같은 LB 기능을 못 씀. 필요해지면
      그때 LB+IAP 로 이전(둘 동시 사용 불가).
- (−) 인증 이중 구조 유지: IAP(입장) + 앱 OAuth /login(Drive 토큰). IAP 만 통과한
      사용자는 Drive 검색이 skip 되고 Vertex-only 로 degrade(설계된 동작). Drive
      하이브리드를 쓰려면 /login 1회 필요. OAuth refresh 미구현이라 "로그인 직후"만
      보장(README 알려진 한계 — refresh 토큰 미갱신).
- (+) LB 고정비 제거: LB+IAP 구성은 포워딩 룰만 월 ~$18(예산의 절반). direct IAP 는
      IAP 자체 무료 + LB 0 → 유휴 시 고정비 ≈ 0.
- (+) 키 유출 표면 제거: "키 관리" 문제를 "IAM 관리" 문제로 치환.
- (+) 코드 수정 0: get_user_email() 이 IAP 헤더를 1순위 처리하도록 미리 잡아 둬 앱 무수정.

## 대안 (Alternatives considered)

- **LB + IAP(초기 계획)**: 커스텀 도메인/Cloud Armor 필요 시 정답이나, 지금은 기능을 안
  쓰면서 월 ~$18 고정비 → 기각. 필요 시점에 이전 가능(마이그레이션 경로 보존).
- **IAP 없이 앱 OAuth 만**: 인증 이전에 앱이 인터넷에 직접 노출(미인증 요청도 앱까지
  도달). IAP 는 앱 앞단에서 차단 + 인프라 레벨 감사로그 → 기각.
- **min=1**: 콜드스타트 0 이지만 24시간 과금. 사용자 1명(현재)~10명에 오버 → 기각.

## 후속 (Follow-ups)

- 회사 GCP 이전: IAP 재활성화(새 프로젝트) + `domain:example.com` 부여,
  redirect URI 재등록, 결정형 URL 재확인.
- 에러 핸들링/알림(로드맵). OAuth refresh 토큰 흐름 검토.
- 다중 인스턴스가 실제로 관측되면(로그) rate limit Redis 전환 재평가(ADR 0009 후속).
- Terraform 모듈화(로드맵): 이 구성 전체(서비스/IAP/IAM/시크릿 배선)를 코드화.
