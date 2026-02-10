import os
import sys

# API 키 확인
api_key = os.environ.get("GEMINI_API_KEY", "")
print(f"API 키 설정 여부: {'✅ 설정됨' if api_key else '❌ 없음'}")
if api_key:
    print(f"API 키 길이: {len(api_key)} 문자")
    print(f"API 키 시작: {api_key[:10]}...")

# Gemini 패키지 확인
try:
    import google.generativeai as genai
    print("✅ google-generativeai 패키지 설치됨")
    
    if api_key:
        print("\n🔄 Gemini API 테스트 중...")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content("Hello, say hi in Korean!")
        print(f"✅ API 호출 성공!")
        print(f"응답: {response.text}")
    else:
        print("⚠️ API 키가 설정되지 않아 테스트를 건너뜁니다")
        
except ImportError as e:
    print(f"❌ google-generativeai 패키지 없음: {e}")
except Exception as e:
    print(f"❌ API 호출 실패: {e}")
