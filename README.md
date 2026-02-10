# Daily Summary - ActivityWatch 일일 활동 요약

ActivityWatch 데이터를 기반으로 하루 활동을 자동으로 요약하고, Gemini AI로 5가지 핵심 포인트를 추출하여 Slack으로 전송하는 스크립트입니다.

## 주요 기능

- ✅ **앱 사용 시간 추적**: ActivityWatch에서 앱 활동 데이터 수집
- ✅ **웹 브라우징 추적**: 방문한 웹사이트와 페이지 타이틀 수집 (클릭 가능한 링크 포함)
- ✅ **Claude 활동 요약**: 세션 제목, 작업 목표, 수정한 파일 목록
- ✅ **Antigravity 파일 추적**: Git 이력 기반 파일 수정 목록
- ✅ **AI 요약**: Gemini API로 5가지 핵심 활동 자동 요약
- ✅ **Slack 전송**: AI 요약을 Slack DM으로 자동 전송

## 설치 방법

### 1. 필수 패키지 설치

```bash
pip install requests google-generativeai
```

### 2. Gemini API 키 설정

**방법 1: 자동 설정 스크립트 사용 (권장)**

```bash
./setup_env.sh
```

**방법 2: 수동 설정**

1. https://aistudio.google.com/app/apikey 에서 API 키 발급
2. `.env` 파일 생성:

```bash
cp .env.example .env
# .env 파일을 열어서 API 키 입력
```

3. 환경변수 로드:

```bash
source .env
```

### 3. Slack Webhook 설정 (선택사항)

`daily_summary.py` 파일에서 Slack Webhook URL 설정:

```python
"slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
```

## 사용 방법

### 기본 사용 (어제 날짜)

```bash
python3 daily_summary.py
```

### 오늘 날짜로 실행

```bash
python3 daily_summary.py --today
```

### 특정 날짜 지정 (YYYYMMDD 형식)

```bash
python3 daily_summary.py 20260210
```

### 환경변수와 함께 실행

```bash
source .env
python3 daily_summary.py --today
```

## 출력 결과

### 1. 마크다운 파일
- 위치: `~/daily-summaries/YYYY-MM-DD-daily-summary.md`
- 상세한 활동 내역 포함

### 2. Slack DM (AI 요약)
- Gemini AI가 생성한 5가지 핵심 활동
- 관련 링크 포함
- 원본 리포트 파일 경로 표시

## 보안 주의사항

⚠️ **중요**: `.env` 파일은 Git에 커밋되지 않도록 `.gitignore`에 추가되어 있습니다.

- API 키는 절대 Git에 커밋하지 마세요
- `.env.example`은 예시 파일이므로 실제 키를 입력하지 마세요
- 환경변수 방식을 사용하는 것이 가장 안전합니다

## 자동화 설정

매일 자동으로 실행하려면 cron job을 설정하세요:

```bash
# crontab 편집
crontab -e

# 매일 오전 10시 5분에 실행
5 10 * * * cd /Users/pilju.bae/daily-summary-env && source .env && python3 daily_summary.py
```

## 문제 해결

### "Gemini API 요약 실패" 오류
- API 키가 올바르게 설정되었는지 확인
- `echo $GEMINI_API_KEY`로 환경변수 확인
- API 키 할당량 확인

### "웹 활동 0개" 문제
- ActivityWatch가 실행 중인지 확인
- 웹 브라우저 확장 프로그램이 설치되어 있는지 확인

### Git 저장소 없음
- Antigravity 파일 추적은 Git 저장소가 필요합니다
- `git init`으로 저장소 초기화 또는 작업 디렉토리 경로 수정
# daily-summary-env
