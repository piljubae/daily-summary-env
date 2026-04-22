# Slack API 직접 연동 설계

**날짜**: 2026-04-22
**목표**: Slack Web API로 내 멘션 스레드 + 지정 채널 메시지를 직접 가져와 AI 요약 후 .md 파일로 저장

## 배경

- 현재: 외부 자동화(오전 9시)가 Slack 멘션을 정리하여 `~/Documents/Claude Cowork/Slack/`에 .md 파일 생성
- 목표: 외부 자동화 의존 없이, daily-summary 파이프라인 내에서 Slack 데이터를 직접 수집·요약

## 요구사항

- 내 멘션이 포함된 스레드의 전체 흐름 + 특정 지정 채널 메시지
- 기존 .md 파일의 마지막 수정 시간 이후 데이터만 증분 조회
- 스레드당 하나의 .md 파일, 새 메시지는 기존 파일에 반영(AI 재요약)
- Gemini로 구조화된 요약 저장 (현재 외부 자동화 결과물과 유사)
- .md 파일 저장 + FetchedData 직접 전달 (둘 다)

## 아키텍처 (2모듈 분리)

```
[Slack API] → slack_api.py (raw 수집) → slack_summarizer.py (AI 요약 + .md 저장)
                                                  ↓
                                          .md 파일 업데이트
                                                  ↓
                                     기존 fetch_slack_summary() → FetchedData
```

### 모듈 1: `fetchers/slack_api.py`

Slack Web API 호출, raw 스레드 데이터 수집.

**흐름:**
1. 기존 .md 파일들의 가장 최근 수정 시간 확인 → `since_ts`
2. `search.messages` — 내 멘션 검색 (`since_ts` 이후)
3. 지정 채널에 대해 `conversations.history` — `since_ts` 이후 메시지
4. 각 메시지의 스레드 전체를 `conversations.replies`로 가져옴
5. 스레드 단위 중복 제거 후 반환

**반환값:**
```python
list[dict]: [{
    "channel_id": str,
    "channel_name": str,
    "thread_ts": str,
    "messages": [{"user": str, "text": str, "ts": str}, ...],
}]
```

### 모듈 2: `fetchers/slack_summarizer.py`

raw 스레드 → Gemini 요약 → .md 파일 저장.

**흐름:**
1. 스레드별로 Gemini에 요약 요청
2. 기존 .md 파일이 있으면 새 메시지 반영하여 업데이트 (전체 재요약)
3. 새 스레드면 새 .md 파일 생성
4. README.md 인덱스 갱신

**파일 매칭:** `thread_ts`를 .md 파일 frontmatter에 포함하여 기존 파일과 매칭.

### 실행 순서 (daily_summary.py)

```
1. slack_api.fetch_slack_threads()              → raw threads
2. slack_summarizer.summarize_and_save(threads)  → .md 파일 업데이트
3. fetch_slack_summary()                         → .md 파일 읽어서 FetchedData (기존 구현)
```

### Config 추가

```python
"slack_bot_token": os.environ.get("SLACK_BOT_TOKEN", ""),
"slack_watch_channels": [c.strip() for c in os.environ.get("SLACK_WATCH_CHANNELS", "").split(",") if c.strip()],
```

## 변경 파일

| 파일 | 변경 |
|------|------|
| `fetchers/slack_api.py` | 신규 — Slack API 호출 |
| `fetchers/slack_summarizer.py` | 신규 — AI 요약 + .md 저장 |
| `config.py` | `slack_bot_token`, `slack_watch_channels` 추가 |
| `daily_summary.py` | slack_api → slack_summarizer 단계 추가 |

기존 `fetchers/slack_summary.py`는 그대로 유지 (.md 읽기 전담).
