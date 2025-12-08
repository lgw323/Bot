# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# --- 1. 경로 설정 ---
# 현재 파일(profiler/config.py)의 부모(profiler)의 부모(Bot-Root)를 기준 경로로 설정
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "profiling"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
REPORT_DIR = DATA_DIR / "reports"

# 데이터 디렉토리가 없으면 자동 생성
for d in [RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# --- 2. 환경 변수 로드 (.env) ---
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"❌ 경고: '{env_path}' 파일을 찾을 수 없습니다. API 키 로드에 실패할 수 있습니다.")

# --- 3. 핵심 설정 변수 ---
# Discord Bot Token
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Target Channel (기존 SUMMARY_CHANNEL_ID 공유)
try:
    TARGET_CHANNEL_ID = int(os.getenv("SUMMARY_CHANNEL_ID", "0"))
except ValueError:
    TARGET_CHANNEL_ID = 0

# Gemini API
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# 모델: Gemini 2.5 Flash (대량 분석에 최적화)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# 분석 임계값
MIN_MSG_COUNT = 50   # 최소 50마디 이상 한 사람만 분석
BATCH_SIZE = 1       # 한 번에 1명씩 처리 (안정성 위주)

# --- 4. 검증 함수 ---
def check_requirements():
    """필수 환경 변수가 설정되었는지 확인합니다."""
    missing = []
    if not DISCORD_TOKEN:
        missing.append("DISCORD_TOKEN")
    if not GOOGLE_API_KEY:
        missing.append("GOOGLE_API_KEY")
    if TARGET_CHANNEL_ID == 0:
        missing.append("SUMMARY_CHANNEL_ID")
    
    if missing:
        return False, f"누락된 설정: {', '.join(missing)}"
    
    return True, f"설정 로드 완료. (대상 채널: {TARGET_CHANNEL_ID}, 모델: {GEMINI_MODEL})"