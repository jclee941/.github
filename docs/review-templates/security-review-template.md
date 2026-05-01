# 보안 리뷰 템플릿

> PR-Agent `jclee-bot`용 보안 중심 코드 리뷰
> 트리거: `security-review` 라벨 또는 `/agentic_review --security`
> 응답 언어: **한국어 (ko)**

---

## 1. 검증 범위 (Scope)

### 1.1 입력 검증 (Input Validation)
- [ ] 모든 사용자 입력이 검증(validation)되고 정제(sanitization)되는가?
- [ ] 파일 업로드 시 MIME 타입과 확장자가 모두 검증되는가?
- [ ] Path traversal (`../`, `..\`) 방어가 되는가?

### 1.2 인증/인가 (Authentication/Authorization)
- [ ] 세션/토큰 만료 시간이 적절히 설정되었는가?
- [ ] 권한 상승(Privilege Escalation) 가능성이 있는가?
- [ ] 민감한 작업에 2FA/MFA가 요구되는가?

### 1.3 데이터 보호 (Data Protection)
- [ ] 비밀번호가 bcrypt/Argon2 등으로 해싱되는가?
- [ ] PII(개인식별정보)가 로그에 남지 않는가?
- [ ] 민감한 데이터가 클라이언트에 노출되지 않는가?

---

## 2. OWASP Top 10 체크리스트

| 위험 | 검토 항목 | 대응 |
|------|-----------|------|
| **A01: Broken Access Control** | 직접 객체 참조(IDOR), 경로 제어 누락 | 인가 검증 로직 확인 |
| **A02: Cryptographic Failures** | 평문 전송, 취약한 암호화 알고리즘 | TLS 1.3, AES-256-GCM 사용 |
| **A03: Injection** | SQLi, NoSQLi, Command Injection, LDAP Injection | 파라미터화 쿼리, 입력 검증 |
| **A04: Insecure Design** | 비즈니스 로직 결함, 경쟁조건 | Threat Modeling 검토 |
| **A05: Security Misconfiguration** | 디폴트 패스워드, 불필요한 기능 활성화 | 보안 헤더, 최소 권한 원칙 |
| **A06: Vulnerable Components** | 취약한 라이브러리/프레임워크 | Dependabot/SCA 도구 사용 |
| **A07: ID and Auth Failures** | 세션 고정, 크리덴셜 스터핑 | 세션 관리, rate limiting |
| **A08: Software and Data Integrity** | CI/CD 파이프라인 변조 | 코드 서명, SLSA 프레임워크 |
| **A09: Security Logging Failures** | 감사 로그 누락, 로그 변조 | 중앙 집중식 로깅, 무결성 검증 |
| **A10: SSRF** | 낮은 권한으로 낮은 낸트워크 요청 | URL 화이트리스트, DNS 재바인딩 방어 |

---

## 3. 시크릿/키 관리

### 3.1 하드코딩된 시크릿 검색
- [ ] API Key, Password, Token이 코드에 하드코딩되지 않았는가?
- [ ] `.env`, GitHub Secrets, Vault 등 외부 저장소 사용
- [ ] 커밋 이력에 시크릿이 노출되지 않았는가? (git-secrets, truffleHog)

### 3.2 키 회전 (Key Rotation)
- [ ] 장기간 사용되는 키에 자동 회전 정책이 있는가?
- [ ] 노출 시 즉시 폐기/재발급 절차가 문서화되었는가?

---

## 4. 리뷰 응답 형식

```markdown
## 보안 검토 결과
- 위험도: {CRITICAL / HIGH / MEDIUM / LOW}
- 총 이슈: {N}개 (CRITICAL: {c}, HIGH: {h}, MEDIUM: {m}, LOW: {l})

### [CRITICAL] 파일명:라인 - {OWASP 분류}
**취약점**: {한국어 설명}
**영향도**: {데이터 유출/권한 상승/서비스 중단 등}
**개선안**:
```코드
{보안 코드 예시}
```
**참조**: {CVE 링크 또는 OWASP 가이드}
```

---

## 5. 자동화 도구 연동

> PR-Agent가 다음 보안 도구와 연동하여 검토합니다.

- **GitHub Advanced Security**: Secret scanning, Code scanning alerts
- **Dependabot**: 취약한 dependency 자동 탐지
- **CodeQL**: 정적 분석(SAST) 결과 코멘트

---

*템플릿 버전: 1.0.0*
*마지막 업데이트: 2026-04-30*
