# Daily Summary - ActivityWatch 일일 활동 요약

ActivityWatch 데이터를 기반으로 하루 활동을 자동으로 요약하고, Gemini AI로 5가지 핵심 포인트를 추출하여 Slack으로 전송하는 스크립트입니다.

## 주요 기능

- ✅ **앱 사용 시간 추적**: ActivityWatch에서 앱 활동 데이터 수집
- ✅ **웹 브라우징 추적**: 방문한 웹사이트와 페이지 타이틀 수집 (클릭 가능한 링크 포함)
- ✅ **Claude 활동 요약**: 세션 제목, 작업 목표, 수정한 파일 목록
- ✅ **Antigravity 파일 추적**: Git 이력 기반 파일 수정 목록
- ✅ **Firebender (Android Studio)**: 안드로이드 스튜디오 AI 플러그인 사용 로그 및 질문 내역 추출
- ✅ **AI 요약**: Gemini API로 5가지 핵심 활동 자동 요약
- ✅ **Slack 전송**: AI 요약을 Slack DM으로 자동 전송

## 설치 방법

### 1. 가상환경 생성 및 패키지 설치

```bash
# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate

# 필수 패키지 설치
pip install requests google-genai

# 가상환경 비활성화 (설치 완료 후)
deactivate
```

### 2. 환경 설정 (API 키 및 슬랙 웹훅)

#### 2-1. Slack Webhook URL 발급

Daily Summary를 Slack DM으로 받으려면 개인별 Webhook URL이 필요합니다.

**옵션 1: 관리자에게 요청 (추천)**

Daily Summary Bot을 통해 Webhook URL을 받고 싶으시면 다음 담당자에게 연락하세요:
- @piljubae
- @hyunkyoung-jung

**옵션 2: 직접 생성**

1. [Slack App Incoming Webhooks 페이지](https://api.slack.com/apps/A0AEVMBAN0G/incoming-webhooks) 접속
2. "Add New Webhook to Workspace" 클릭
3. 메시지를 받을 채널 선택 (본인 DM 또는 원하는 채널)
4. 생성된 Webhook URL 복사 (예: `https://hooks.slack.com/services/...`)

#### 2-2. 환경 변수 설정

**자동 설정 스크립트 사용 (권장)**

이 스크립트를 실행하면 Gemini API 키와 Slack Webhook URL을 입력받아 `.env` 파일에 안전하게 저장합니다.

```bash
./setup_env.sh
```

**수동 설정**

프로젝트 디렉토리에 `.env` 파일을 생성하고 다음 내용을 입력하세요:

```bash
GEMINI_API_KEY=your_gemini_api_key_here
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

## 사용 방법

**가상환경 활성화 없이 바로 실행 가능합니다!** 

`daily-summary` 래퍼 스크립트가 자동으로 가상환경을 활성화하고 실행합니다.

### 기본 사용 (어제 날짜)

```bash
./daily-summary
```

### 오늘 날짜로 실행

```bash
./daily-summary --today
```

### 특정 날짜 지정 (YYYYMMDD 형식)

```bash
./daily-summary 20260210
```

### 기존 방식 (가상환경 수동 활성화)

원한다면 여전히 기존 방식으로도 실행 가능합니다:

```bash
source venv/bin/activate
python3 daily_summary.py
deactivate
```

## 출력 결과

### 1. 마크다운 파일
- 위치: `~/daily-summaries/YYYY-MM-DD-daily-summary.md`
- 상세한 활동 내역 포함 및 파일 하단에 **AI 요약 (Gemini)** 섹션이 추가됩니다.

### 2. Slack DM (AI 요약)
- 이제 전체 리포트 대신 **간결한 AI 요약(5가지 포인트)**만 슬랙으로 전송됩니다.
- 슬랙 메시지 하단에 상세 리포트 파일 경로가 표시되어 바로 확인할 수 있습니다.

## 보안 주의사항

🔐 **Secrets Protection**: 기밀 정보(API Key, Webhook URL)는 코드에 하드코딩하지 않고 `.env` 파일에서 관리합니다.
- `.env` 파일은 `.gitignore`에 등록되어 있어 GitHub에 업로드되지 않습니다.
- 코드 내에서도 하드코딩된 시크릿이 모두 제거되어 안전하게 공유 혹은 공개 저장소에 올릴 수 있습니다.

## 자동화 설정 (macOS launchd)

매일 오전 10시에 자동으로 실행되도록 `launchd`를 사용하여 설정할 수 있습니다.

### 1. 설정 파일 등록
이미 생성된 `com.piljubae.daily.summary.plist` 파일을 사용합니다.

```bash
# 설정 파일을 macOS 서비스 디렉토리로 복사
cp com.piljubae.daily.summary.plist ~/Library/LaunchAgents/

# 서비스 로드 (자동 실행 활성화)
launchctl load ~/Library/LaunchAgents/com.piljubae.daily.summary.plist
```

### 2. 관리 명령어
- **즉시 실행 테스트**: `launchctl start com.piljubae.daily.summary`
- **자동 실행 중단**: `launchctl unload ~/Library/LaunchAgents/com.piljubae.daily.summary.plist`
- **로그 확인**: `./automation.log` 파일에서 실행 이력을 확인할 수 있습니다.
