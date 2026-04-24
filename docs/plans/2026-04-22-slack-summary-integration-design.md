# Slack 요약 fetcher 통합 설계

**날짜**: 2026-04-22
**목표**: `~/Documents/Claude Cowork/Slack/` 디렉토리의 Slack 스레드 요약 파일을 daily-summary에 통합

## 배경

- 외부 자동화가 매일 오전 9시에 Slack 멘션 스레드를 주제별 .md 파일로 정리
- daily-summary는 오전 10시에 실행 → 타이밍 문제 없음
- 현재 11개 토픽 파일 + README.md 인덱스, 총 ~410줄

## 설계

### 접근 방식

- markdown 리포트: 간략 섹션 (README의 "이번 주 포커스" 활용)
- Gemini 요약 prompt: 전체 파일 내용을 컨텍스트로 전달

### 1. fetcher: `fetchers/slack_summary.py`

- `config.py`의 `slack_summary_dir` 경로에서 `.md` 파일 전체를 읽음
- 반환값: `dict`
  - `topics`: `list[dict]` — `{filename, title, content}`
  - `readme_content`: `str` — README.md 원문
  - `full_text`: `str` — 모든 파일 합친 전체 텍스트 (Gemini용)

### 2. FetchedData 확장

```python
slack_summary: dict = field(default_factory=dict)
```

### 3. Markdown 리포트 섹션

`📬 Slack 주요 토픽` — README의 "이번 주 포커스" 불릿 포인트를 그대로 표시.

### 4. Gemini prompt 확장

`summarize_with_gemini()`에 Slack 전체 텍스트를 추가 컨텍스트로 삽입.
Gemini가 오늘의 플랜 생성 시 Slack 논의 맥락 활용.

### 변경 파일

| 파일 | 변경 |
|------|------|
| `fetchers/slack_summary.py` | 신규 |
| `fetchers/all.py` | 필드 + fetch 호출 |
| `fetchers/__init__.py` | export |
| `config.py` | `slack_summary_dir` 설정 |
| `formatters/markdown.py` | 간략 섹션 + Gemini prompt 확장 |
