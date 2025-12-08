# -*- coding: utf-8 -*-
import discord
import json
import asyncio
from datetime import datetime
import sys

# 상위 폴더의 config를 가져오기 위한 경로 설정
sys.path.append("..") 
import config

class HistoryDumper(discord.Client):
    def __init__(self, target_channel_id):
        intents = discord.Intents.default()
        intents.message_content = True # 메시지 내용 읽기 권한 필수
        super().__init__(intents=intents)
        self.target_channel_id = target_channel_id
        self.output_file = config.RAW_DATA_DIR / "raw_history.json"

    async def on_ready(self):
        print(f"✅ [Dumper] 로그인 성공: {self.user}")
        channel = self.get_channel(self.target_channel_id)

        if not channel:
            print(f"❌ [Dumper] 채널 ID({self.target_channel_id})를 찾을 수 없습니다. 봇이 해당 서버에 있나요?")
            await self.close()
            return

        print(f"📥 [Dumper] '{channel.name}' 채널의 전체 기록 다운로드를 시작합니다...")
        print("   (메시지 양에 따라 시간이 오래 걸릴 수 있습니다.)")

        all_messages = []
        msg_count = 0
        start_time = datetime.now()

        try:
            # limit=None으로 설정하여 채널의 처음부터 끝까지 가져옵니다.
            async for msg in channel.history(limit=None, oldest_first=True):
                # 봇 메시지는 제외 (순수 유저 대화만 수집)
                if msg.author.bot:
                    continue

                # 저장할 데이터 최소화
                msg_data = {
                    "id": msg.id,
                    "timestamp": msg.created_at.isoformat(),
                    "author_id": msg.author.id,
                    "author_name": msg.author.display_name, # 닉네임
                    "content": msg.content
                }
                
                # 텍스트가 있는 경우만 저장 (사진만 있는 경우 제외 가능)
                if msg.content.strip():
                    all_messages.append(msg_data)
                    msg_count += 1

                if msg_count % 1000 == 0:
                    print(f"\r⏳ {msg_count}개 수집 중... (현재 처리 날짜: {msg.created_at.date()})", end="")

            duration = datetime.now() - start_time
            print(f"\n\n✅ 수집 완료!")
            print(f"   - 총 메시지 수: {len(all_messages)}개")
            print(f"   - 소요 시간: {duration}")

            # 파일 저장
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump(all_messages, f, ensure_ascii=False, indent=4)
            
            print(f"📂 파일 저장 완료: {self.output_file}")

        except Exception as e:
            print(f"\n❌ 수집 중 오류 발생: {e}")
        
        finally:
            await self.close()

async def run_dump_process():
    if not config.DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN이 없습니다.")
        return

    client = HistoryDumper(config.TARGET_CHANNEL_ID)
    await client.start(config.DISCORD_TOKEN)