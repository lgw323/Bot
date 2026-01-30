# 🛠️ Raspberry Pi 5 Server Configuration Reference

이 문서는 라즈베리파이 서버의 자동화 설정(Crontab)과 서비스 데몬(Systemd) 설정값을 기록한 백업 파일입니다.

## 1. 스케줄러 설정 (Crontab)

- **편집 명령어:** `crontab -e`

```
# ==========================================
# [Crontab Configuration]
# ==========================================

# 1. [실시간 감지] GitHub에 새로운 코드가 올라오면 즉시 업데이트하고 재시작 (5분 주기)
*/5 * * * * /home/os/bot/auto_update.sh

# 2. [일일 정기 점검] 매일 강제로 라이브러리를 최신화, 봇 재시작 (매일 새벽 04:00)
3 4 * * * /home/os/bot/auto_update.sh --daily

# 3. [데이터 백업] 6시간마다 사용자 데이터 GitHub로 업로드 (0, 6, 12, 18시) [업데이트와 시간이 겹치지 않게 하기 위해 3분]
3 */6 * * * /home/os/bot/auto_backup.sh

```

## 2. 서비스 데몬 설정 (Systemd)

- **파일 경로:** `/etc/systemd/system/discordbot.service`
- **편집 명령어:** `sudo nano /etc/systemd/system/discordbot.service`

```
# ==========================================
# [Systemd Service Configuration]
# ==========================================

[Unit]
Description=Discord Music Bot
After=network.target

[Service]
User=os
WorkingDirectory=/home/os/bot

# 봇 실행 전 핵심 라이브러리(yt-dlp) 강제 업데이트
ExecStartPre=/home/os/bot/bot_env/bin/pip install -U yt-dlp

# 봇 실행 명령어 (가상환경 경로 주의)
ExecStart=/home/os/bot/bot_env/bin/python main_bot.py

# 봇이 죽으면 무조건 다시 시작 (핵심 안정성 기능)
Restart=always

[Install]
WantedBy=multi-user.target

```

## 3. 로그 모니터링 명령어

서버 내부에서 실시간 로그를 확인하고 싶을 때 사용합니다.

```
# 실시간 시스템 로그 확인 (Ctrl+C로 종료)
tail -f ~/bot/data/logs/system.log

```