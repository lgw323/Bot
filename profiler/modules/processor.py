# -*- coding: utf-8 -*-
import json
import os
from collections import defaultdict
import re
import sys

sys.path.append("..")
import config

INPUT_FILE = config.RAW_DATA_DIR / "raw_history.json"
OUTPUT_FILE = config.PROCESSED_DATA_DIR / "clean_data.json"

def clean_text(text):
    """분석에 방해되는 노이즈 제거"""
    # URL 제거
    text = re.sub(r'http\S+', '', text)
    # 디스코드 멘션 제거 (<@1234...>)
    text = re.sub(r'<@!?[0-9]+>', '', text)
    # 너무 짧은 의성어 제거 (ㅋㅋ, ㅎㅎ 등) - 선택 사항
    if len(text) < 2 and re.match(r'[ㅋㅎㅇ]+', text):
        return ""
    return text.strip()

def run_processing():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ 원본 데이터가 없습니다: {INPUT_FILE}")
        print("   -> [1. 데이터 수집]을 먼저 실행해주세요.")
        return None

    print("🧹 데이터 전처리 작업을 시작합니다...")
    
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    user_groups = defaultdict(list)
    
    print(f"   - 원본 메시지 수: {len(raw_data)}개")

    # 사용자별 그룹화
    for msg in raw_data:
        author_name = msg['author_name']
        content = clean_text(msg['content'])
        
        if content: # 내용이 비어있지 않다면
            user_groups[author_name].append(content)

    # 통계 및 저장 데이터 구성
    processed_data = {}
    stats = []

    for user, messages in user_groups.items():
        msg_count = len(messages)
        
        # 최소 메시지 수 미만은 분석 제외
        if msg_count < config.MIN_MSG_COUNT:
            continue

        # 분석용 텍스트 뭉치 생성 (최신순? 과거순? -> 보통 흐름 파악엔 과거순)
        # 이미 Dumper에서 oldest_first로 가져왔으므로 그대로 합칩니다.
        full_text = "\n".join(messages)
        
        processed_data[user] = {
            "msg_count": msg_count,
            "full_text": full_text
        }
        
        stats.append((user, msg_count))

    # 저장
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)

    # 결과 출력
    stats.sort(key=lambda x: x[1], reverse=True)
    print(f"\n✅ 전처리 완료! (총 {len(processed_data)}명 대상)")
    print("-" * 40)
    print(f"{'사용자 (User)':<20} | {'메시지 수':<10}")
    print("-" * 40)
    for user, count in stats:
        print(f"{user:<20} | {count:<10,}")
    print("-" * 40)
    print(f"📂 저장 경로: {OUTPUT_FILE}")
    
    return processed_data