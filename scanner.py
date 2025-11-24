import discord
import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from collections import Counter
from dotenv import load_dotenv

# --- [설정 구간] 정보를 입력해주세요 ---
TARGET_USER_ID = 281745554097176577    # [친구 ID] 추적할 친구의 유저 ID (숫자)
TARGET_KEYWORD = "건우"                # [단어] 찾을 단어 (포함되어 있으면 카운트)
TARGET_CHANNEL_ID = 860135576690229279 # [채널 ID] 검색할 채팅방 ID (숫자)

# 검색 시작 날짜 (None으로 두면 처음부터, 날짜를 적으면 그 이후부터)
# 예시: START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)
START_DATE = datetime(2024, 1, 1, tzinfo=timezone.utc)

OUTPUT_FILE = "data/detailed_stats.json"  # 결과 저장 경로
# -------------------------------------

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

class DetailedScanner(discord.Client):
    async def on_ready(self):
        print(f"✅ 스캐너 로그인: {self.user}")
        
        try:
            channel = self.get_channel(TARGET_CHANNEL_ID)
            if not channel:
                print(f"❌ 오류: ID가 {TARGET_CHANNEL_ID}인 채널을 찾을 수 없습니다.")
                await self.close()
                return

            print(f"🎯 목표 채널: '{channel.name}' 스캔 시작...")
            print(f"🔎 조건: 유저({TARGET_USER_ID})가 '{TARGET_KEYWORD}'를 포함한 메시지 검색 중...")

            # 데이터 저장소
            logs = []
            hourly_counts = Counter()
            monthly_counts = Counter()
            total_count = 0

            # 진행률 표시를 위한 변수
            scanned_msg_count = 0
            
            # 검색 시작 (limit=None: 전체 조회)
            async for msg in channel.history(limit=None, after=START_DATE, oldest_first=True):
                scanned_msg_count += 1
                if scanned_msg_count % 1000 == 0:
                    print(f"\r⏳ {scanned_msg_count}개 메시지 검사 중... (현재 발견: {total_count}개)", end="")

                # 조건: 작성자 일치 AND 키워드 포함
                if msg.author.id == TARGET_USER_ID and msg.content:
                    if TARGET_KEYWORD in msg.content:
                        # 등장 횟수 (한 메시지에 여러 번 쓴 경우)
                        occurences = msg.content.count(TARGET_KEYWORD)
                        total_count += occurences

                        # 한국 시간(KST) 보정 (UTC+9)
                        kst_time = msg.created_at + timedelta(hours=9)
                        time_str = kst_time.strftime("%Y-%m-%d %H:%M:%S")
                        
                        # 1. 통계용 데이터 수집
                        hourly_counts[kst_time.hour] += occurences # 0시~23시
                        monthly_key = kst_time.strftime("%Y-%m") # 2024-05
                        monthly_counts[monthly_key] += occurences

                        # 2. 로그 상세 저장
                        logs.append({
                            "time": time_str,
                            "content": msg.content,
                            "count_in_msg": occurences
                        })

            # 결과 정리
            result_data = {
                "summary": {
                    "target_user": TARGET_USER_ID,
                    "keyword": TARGET_KEYWORD,
                    "total_found": total_count,
                    "total_scanned_messages": scanned_msg_count,
                    "scan_date": str(datetime.now())
                },
                "stats": {
                    "most_active_hour": hourly_counts.most_common(3), # 가장 많이 부른 시간대 TOP 3
                    "hourly_breakdown": dict(sorted(hourly_counts.items())), # 시간대별 전체 분포
                    "monthly_trend": dict(sorted(monthly_counts.items()))    # 월별 추이
                },
                "message_logs": logs # 실제 채팅 로그 전체
            }

            # 파일 저장
            os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(result_data, f, ensure_ascii=False, indent=4)

            print(f"\n\n✅ [완료] 총 {total_count}번의 호출을 발견했습니다.")
            print(f"📂 상세 결과가 '{OUTPUT_FILE}'에 저장되었습니다.")

        except Exception as e:
            print(f"\n❌ 실행 중 오류 발생: {e}")
        
        await self.close()

if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True 
    
    client = DetailedScanner(intents=intents)
    client.run(TOKEN)