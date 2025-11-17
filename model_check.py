import os
import sys
import google.generativeai as genai
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

api_key = os.getenv("GOOGLE_API_KEY")

if not api_key or api_key == "YOUR_GOOGLE_API_KEY_HERE":
    print("오류: .env 파일에 GOOGLE_API_KEY가 올바르게 설정되지 않았습니다.")
    sys.exit(1)

try:
    genai.configure(api_key=api_key)

    # 1. 'generateContent'를 지원하는 모든 모델을 미리 필터링합니다.
    all_models = [
        model for model in genai.list_models()
        if 'generateContent' in model.supported_generation_methods
    ]

    # 2. 모델을 카테고리별로 분류합니다.
    #    (예: 'gemini-1.5-pro'는 'pro'로, 'gemini-2.5-flash'는 'flash'로)
    
    # 카테고리 분류 우선순위 (이름에 여러 키워드가 겹칠 경우)
    # (예: 'flash-image' 모델은 'image'로 분류)
    CATEGORIES_PRIORITY = [
        'robotics', 
        'computer-use', 
        'image', 
        'flash', 
        'pro', 
        'ultra'
    ]
    
    categorized = defaultdict(list)
    
    for model in all_models:
        model_name_lower = model.name.lower()
        found_category = False
        
        for cat in CATEGORIES_PRIORITY:
            if f'-{cat}' in model_name_lower:
                categorized[cat].append(model)
                found_category = True
                break
        
        if not found_category:
            categorized['other'].append(model)
    
    # 3. 분류된 결과를 보기 좋게 출력합니다.
    print("조회 시작: 'generateContent' (텍스트 생성)을 지원하는 모델 목록\n")
    
    total_count = 0
    
    # 정의된 카테고리 순서대로 출력
    all_categories = CATEGORIES_PRIORITY + ['other']
    
    for cat in all_categories:
        if cat in categorized and categorized[cat]:
            print(f"--- [ {cat.upper()} 모델 ] ---")
            
            for model in categorized[cat]:
                print(f"  모델: {model.name}")
                print(f"    이름: {model.display_name}\n")
                total_count += 1
            
            print("") # 카테고리 간 간격

    print(f"\n총 {total_count}개의 사용 가능한 텍스트 생성 모델을 찾았습니다.")

except Exception as e:
    print(f"모델 목록을 가져오는 중 오류가 발생했습니다: {e}")