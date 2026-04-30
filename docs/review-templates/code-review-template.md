# 코드 리뷰 마스터 템플릿

> PR-Agent `jclee-bot`용 코드 리뷰 기준 및 응답 형식
> 적용 모델: `kimi-k2.6` (fallback: `kimi-k2.5`, `claude-sonnet-4-6`)
> 응답 언어: **한국어 (ko)**

---

## 1. 우선순위 (Priority Order)

| 순위 | 항목 | 검토 포인트 |
|------|------|-------------|
| 1 | **보안 (Security)** | SQL Injection, XSS, 인증/인가, secrets 노출, 입력 검증 |
| 2 | **정확성 (Correctness)** | 논리 오류, 경쟁조건, edge case 미처리, 오프바이원 |
| 3 | **성능 (Performance)** | N+1 쿼리, 메모리 누수, 불필요한 복잡도, 비효율 알고리즘 |
| 4 | **유지보수성 (Maintainability)** | 코드 중복, 과도한 복잡성, 명명 규칙, 테스트 부재 |
| 5 | **문서화 (Documentation)** | README.md, API 문서, 주석/독스트링, PR 설명 명확성 |

---

## 2. 리뷰 형식 (Review Format)

### 2.1 이슈 표기법

```markdown
### [{심각도}] {파일명}:{라인번호}
**문제**: {한국어 설명}
**개선안**:
```코드
{개선된 코드 예시}
```
```

### 2.2 심각도 레벨

| 레벨 | 의미 | 처리 방식 |
|------|------|-----------|
| `[CRITICAL]` | 즉시 수정 필요 (보안/데이터 손상 위험) | Blocking |
| `[WARNING]` | 권장 수정 (버그/성능 저하 가능성) | Non-blocking |
| `[INFO]` | 참고 사항 (스타일/개선 제안) | Optional |

---

## 3. 문서화 검토 체크리스트

> 모든 PR은 다음 문서화 항목을 검토해야 합니다.

- [ ] **README.md**: 새로운 기능, API 변경, 설정 옵션 추가 시 업데이트 필요
- [ ] **API 문서**: 엔드포인트 변경, 요청/응답 스펙 변경 시 반영
- [ ] **주석/독스트링**: 복잡한 로직, public 함수, 핵심 알고리즘에 설명 추가
- [ ] **PR 설명**: 변경사항의 "왜"(Why)가 명확히 기술되었는지 확인
- [ ] **Configuration 예시**: `.env`, `.toml`, `.yaml` 등 설정 변경 시 예시 업데이트
- [ ] **Migration Guide**: Breaking change 시 마이그레이션 가이드 작성

---

## 4. 특수 상황 가이드

### 4.1 `/agentic_review`
- 더 깊은 아키텍처 분석 수행
- 의존성 영향도(impact) 평가
- 장기적 유지보수성 관점 검토

### 4.2 보안 레이블 (`security-review`)
- SAST(Security Assessment) 관점 적용
- OWASP Top 10 관련 패턴 검색
- Secret scanning, dependency vulnerability 확인

### 4.3 Draft PR
- Blocking 이슈만 코멘트
- 경미한 스타일 이슈는 제외
- `WIP`/`draft` 상태 명시적 언급

---

## 5. 예시 응답

```markdown
## 리뷰 요약
- 변경사항: 사용자 인증 로직에 JWT 토큰 갱신 기능 추가
- 전반적 평가: NEEDS_REVISION

## 상세 피드백

### [CRITICAL] auth/login.py:45
**문제**: 토큰 갱신 시 기존 토큰이 무효화되지 않아 세션 고정 공격 가능성
**개선안**:
```python
# 기존 토큰을 블랙리스트에 추가
token_blacklist.add(old_token)
```

### [WARNING] auth/models.py:12
**문제**: `expires_at` 필드에 timezone 정보 누락
**개선안**:
```python
expires_at = models.DateTimeField(default=lambda: timezone.now() + timedelta(hours=1))
```

### [INFO] README.md
**문제**: 새로운 `JWT_REFRESH_INTERVAL` 환경변수가 문서에 누락됨
**개선안**: Configuration 섹션에 해당 변수 설명 추가
```

---

*템플릿 버전: 1.0.0*
*마지막 업데이트: 2026-04-30*
