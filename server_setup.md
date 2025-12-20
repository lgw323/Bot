# 🛠️ Raspberry Pi 5 Server Configuration Reference

이 문서는 라즈베리파이 서버의 자동화 설정(Crontab)과 서비스 데몬(Systemd) 설정값을 기록한 백업 파일입니다.dd

## 1. 스케줄러 설정 (Crontab)

- **편집 명령어:** `crontab -e`

```
# ==========================================
# [Crontab Configuration]
# ==========================================

# 1. [자동 업데이트] 5분마다 코드 변경 확인 및 반영
*/5 * * * * /home/os/bot/auto_update.sh

# 2. [데이터 백업] 6시간마다 사용자 데이터 GitHub로 업로드 (0, 6, 12, 18시)
0 */6 * * * /home/os/bot/auto_backup.sh

# 3. [시스템 관리] 매주 월요일 새벽 4시에 라즈베리파이 재부팅 (메모리 정리)
0 4 * * 1 sudo reboot

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