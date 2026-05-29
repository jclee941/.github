# 보안 정책 (Security Policy)

## 지원 버전 (Supported Versions)

모든 `jclee941/*` 레포지토리는 기본 브랜치(`main` 또는 `master`)의 최신 커밋만 지원합니다.
과거 태그/릴리스에 대한 백포트는 제공하지 않습니다.

## 취약점 신고 (Reporting a Vulnerability)

보안 취약점은 **공개 Issue로 등록하지 마세요.** 다음 비공개 채널 중 하나를 이용해 주세요.

1. **GitHub Security Advisory** (권장)
   해당 레포의 **Security → Advisories → Report a vulnerability** 메뉴에서 비공개로 신고합니다.
2. **이메일**
   GitHub 프로필에 공개된 연락처로 신고합니다.

### 신고 시 포함할 내용

- 영향받는 레포지토리와 파일/경로
- 재현 단계 또는 PoC
- 예상 영향 범위 (정보 노출, RCE, 권한 상승 등)

### 응답 정책

- **48시간 이내** 접수 확인 1차 응답
- 유효한 취약점은 우선순위에 따라 패치 후 비공개 advisory로 공개
- 신고자 credit 명시 (원하지 않으면 익명 처리)

## 자동 스캔 (Automated Scanning)

이 조직의 모든 레포는 다음 자동 보안 게이트를 통과해야 PR이 머지됩니다.

- **Gitleaks** — 모든 PR/push에서 secret 패턴 스캔 (필수 status check)
- **CodeQL** — Python SAST 분석
- **Dependabot** — 의존성 취약점 자동 업데이트
- **auto-hardcode-scan** — 주간 하드코딩 비밀 스캔

자세한 자동화 구조는 [AGENTS.md](AGENTS.md)를 참고하세요.
