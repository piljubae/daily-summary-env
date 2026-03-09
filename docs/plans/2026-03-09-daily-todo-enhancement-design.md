# 데일리 할일 추천 개선 설계

## 배경

현재 `fetchers/todo.py`는 Jira에서 `summary`와 `status`만 가져와 3개 버킷(진행중/리뷰/할일)으로 분류한다. Gemini 프롬프트도 느슨해서 티켓을 나열하는 수준의 결과가 나옴.

### 핵심 문제

1. Gemini가 판단할 데이터가 부족 (마감일, 우선순위, 코멘트 없음)
2. 상태 기반 분류 → "오늘 뭘 해야 하는가" 관점이 아님
3. 어제 작업과 오늘 할일이 연결되지 않음
4. 프롬프트가 뚜루뚜루해서 인사이트 없는 플랜 생성

## 설계

### 1. 파일 구조 — 책임 분리

```
fetchers/
├── todo.py              # Jira API 호출 + 원시 데이터 파싱
├── todo_scorer.py       # 그룹 분류, 긴급도 계산, 정렬
├── todo_matcher.py      # 어제 데이터에서 티켓키 추출 + 매칭
```

### 2. todo.py — Jira 데이터 수집

JQL 요청 필드를 확장하고 changelog를 포함한다.

```python
"fields": ["summary", "status", "priority", "duedate", "updated", "comment"],
"expand": ["changelog"]
```

반환 구조:

```python
def fetch_today_todos() -> list[dict]:
    """
    Returns: [
        {
            "key": "KMA-1234",
            "summary": "로그인 리팩토링",
            "status": "진행 중",
            "priority": "High",
            "duedate": "2026-03-12" | None,
            "updated": "2026-03-08T10:30:00",
            "latest_comment": "리뷰 반영 부탁" | None,  # 50자 자르기
            "status_changed_at": "2026-03-06T09:00:00" | None,
        },
        ...
    ]
    """
```

- changelog에서 status 필드 변경 이력의 마지막 변경 날짜를 `status_changed_at`으로 추출
- 비즈니스 로직 없음, 데이터 정제만 담당

### 3. todo_matcher.py — 어제 작업 연결

```python
def extract_ticket_keys(fetched_data) -> set[str]:
    """어제 수집된 데이터에서 Jira 티켓키를 추출한다.

    소스: antigravity_data(git), claude_context, claude_cli_history
    정규식: r'[A-Z]+-\d+'
    """

def tag_yesterday_tickets(tickets, yesterday_keys) -> list[dict]:
    """어제 작업한 티켓에 'yesterday': True 플래그를 부여한다."""
```

### 4. todo_scorer.py — 액션 기반 그룹 분류

상태가 아닌 "언제 해야 하는가" 기준으로 3단계 그룹:

| 그룹 | 키 | 조건 (OR) |
|---|---|---|
| 🔴 오늘 집중 | `urgent` | duedate <= 내일 / priority Highest·High + 진행중 / 24시간 내 코멘트 |
| 🟡 이번주 내 | `this_week` | duedate 2~5일 이내 / 진행중·리뷰 상태 (긴급 아닌 것) |
| ⚪ 백로그 | `backlog` | 위 조건에 해당 안 되는 나머지 |

각 티켓에 태그 목록 부여:

| 조건 | 태그 |
|---|---|
| duedate가 오늘~내일 | `D-N` (🔴마감임박) |
| duedate가 2~5일 이내 | `D-N` |
| priority Highest/High | `📍High` |
| 24시간 내 코멘트 | `💬코멘트` |
| updated 7일 이상 전 | `💤N일방치` |
| yesterday 플래그 | `🔄어제이어서` |
| status_changed_at 기반 | `진행중 N일째` / `할일 N일째` 등 |

그룹 내 정렬: 마감 임박 → 우선순위 높은 → updated 최신

```python
def score_and_group(tickets: list[dict]) -> dict:
    """
    Returns: {
        "urgent": [...],     # 🔴 오늘 집중
        "this_week": [...],  # 🟡 이번주 내
        "backlog": [...],    # ⚪ 백로그
    }
    각 티켓에 "tags": ["D-1", "📍High", ...] 필드 추가됨
    """
```

### 5. formatters/markdown.py — 렌더링 + 프롬프트

#### 할일 섹션 출력 형식

```markdown
**📌 오늘의 할일** (8건)

🔴 오늘 집중 (3건)
- [KMA-1234] 로그인 리팩토링 — D-1, 진행중 3일째, 🔄어제이어서
- [KMA-1220] 상품 API — D-3, 💬코멘트, 리뷰 오늘시작
- [KMA-1240] 결제 모듈 테스트 — 📍High, 진행중 1일째

🟡 이번주 내 (2건)
- [KMA-1248] 검색 필터 — 진행중 2일째, 🔄어제이어서
- [KMA-1245] 장바구니 개선 — D-5

⚪ 백로그 (3건)
- [KMA-1250] 푸시 알림 — 할일 12일째 💤
- [KMA-1260] 에러 핸들링 — 할일 2일째
- [KMA-1270] 로깅 개선 — 할일 5일째
```

#### 호출 흐름

```python
# formatters/markdown.py 내부
raw_tickets = todo.fetch_today_todos()
yesterday_keys = todo_matcher.extract_ticket_keys(fetched_data)
tagged_tickets = todo_matcher.tag_yesterday_tickets(raw_tickets, yesterday_keys)
grouped = todo_scorer.score_and_group(tagged_tickets)
# grouped 기반으로 마크다운 렌더링
```

#### Gemini 프롬프트 개선

파트 2 프롬프트를 구조화된 판단 기준으로 교체:

```
## 파트 2: 오늘의 플랜

"📌 오늘의 할일"과 "📅 오늘 미팅" 데이터를 기반으로,
오늘 실제로 실행할 플랜을 3~5개 제안하라.

### 우선순위 판단 기준 (반드시 적용):
1. 🔴 오늘 집중 그룹 → 최우선. 마감/코멘트 응답 등 이유 명시
2. 🔄어제이어서 태그 → 연속성 유지 관점에서 우선 추천
3. 미팅 전후 시간 활용 → 미팅 시간대를 피한 집중 작업 블록 제안
4. 🟡 이번주 내 그룹 → 여유 시간에 착수 권장
5. ⚪ 백로그 → 시간 남을 때만 언급
6. "N일째" 수치가 큰 티켓은 장기화 → 마무리 가능하면 우선 완료 권장
```

플랜 출력 형식:

```
### 출력 형식 (반드시 준수):
- 번호 + **볼드 타이틀** (티켓번호 + 액션 동사)
- 다음 줄에 └ 근거 1줄 (왜 지금 해야 하는지)
- 미팅은 시간과 소요시간만 간결하게 (근거 줄 불필요)
- 단순 티켓 나열 금지, 반드시 "무엇을 할지" 액션 동사 포함
- 미팅이 있으면, 미팅 시간을 기준으로 작업 순서를 배치
```

출력 예시:

```markdown
**📌 오늘의 플랜**

1. **KMA-1234 로그인 리팩토링 마무리**
   └ D-1 마감 + 어제 80% 진행됨

2. **KMA-1220 리뷰 코멘트 응답**
   └ 팀원 24h 전 코멘트 대기중

3. **14:00 스프린트 미팅** (1h)

4. **KMA-1240 결제 모듈 테스트 착수**
   └ High 우선순위, 미팅 후 오후 블록 활용

5. **KMA-1245 장바구니 개선 검토**
   └ D-5, 여유 시간에 스코프 파악
```

## 변경 범위

| 파일 | 변경 | 예상 규모 |
|---|---|---|
| `fetchers/todo.py` | fields 확장, changelog 파싱, 리턴 구조 변경 | ~60줄 수정 |
| `fetchers/todo_scorer.py` | **신규** — 그룹 분류, 태그 계산, 정렬 | ~70줄 |
| `fetchers/todo_matcher.py` | **신규** — 티켓키 추출, 어제 매칭 | ~40줄 |
| `formatters/markdown.py` | 할일 렌더링 재작성 + 프롬프트 개선 | ~60줄 수정 |
| `fetchers/__init__.py` | 새 모듈 export 추가 | ~3줄 |

## 향후 이터레이션 (이번 범위 아님)

- Slack 미답변 스레드 수집
- GitHub PR 리뷰 연동
- 할일 완료 추적 (어제 추천 vs 실제 수행 비교)
