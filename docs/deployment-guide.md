# 🍓 라즈베리파이 5 + 우분투(Ubuntu) 배포 및 서버 환경 설정 가이드

본 문서는 **라즈베리파이 5** 기기에 봇을 설치하고 systemd·cron으로 운영하는
절차만 관리합니다. 제품 의도와 데이터 정책은 `project-context.md`, 로컬 개발과
기능 개요는 루트 `README.md`를 참고합니다.

---

## 🚀 1단계: 라즈베리파이 우분투 OS 설치 (가장 처음)

1. **PC**에서 [Raspberry Pi Imager](https://www.raspberrypi.com/software/) 프로그램을 다운로드하고 실행합니다.
2. PC에 라즈베리파이용 SD카드(또는 USB/SSD)를 꽂습니다.
3. Imager 프로그램에서 다음을 선택합니다.
   * **CHOOSE DEVICE (운영체제 장치 선택):** `Raspberry Pi 5`
   * **CHOOSE OS (운영체제 선택):** `Other general-purpose OS` -> `Ubuntu` -> **`Ubuntu Server 24.04.1 LTS (64-bit)`** (Desktop 버전도 무방하나 Server 버전을 추천합니다.)
   * **CHOOSE STORAGE (저장소 선택):** 연결한 SD카드/SSD 선택
4. `NEXT (다음)` 버튼을 누르면 **설정 커스터마이징 편집(OS Customisation)** 창이 뜹니다. `EDIT SETTINGS (설정 편집)`를 눌러 아래와 같이 맞춥니다.
   * **Hostname (호스트 이름):** `bot-server` (자유롭게 지정)
   * **✅ 사용자 이름 및 비밀번호 설정 (매우 중요!!):**
     * **사용자 이름(User):** `os`  **(기존 서버 설정이 `os` 기준이므로 반드시 `os`로 만드세요!)**
     * **비밀번호(Password):** 접속에 사용할 비밀번호 설정
   * **✅ 무선 LAN(Wi-Fi) 설정:** (공유기에 무선으로 연결할 거라면 와이파이 이름과 비밀번호 입력)
   * **✅ 서비스(SERVICES):** `SSH 활성화 (Enable SSH)` 체크 (원격 접속을 위해 필수) -> `비밀번호 인증 사용` 선택
5. 저장을 누르고 `쓰기(YES)`를 눌러 설치를 완료합니다. 끝난 SD카드를 라즈베리파이5 에 꽂고 전원을 켭니다.

---

## 🔑 관리 PC의 SSH 키 설정

이 설정은 Windows 관리 PC에서 Raspberry Pi에 비밀번호를 매번 입력하지 않고
안전하게 접속하기 위한 절차입니다. 이미
`%USERPROFILE%\.ssh\id_ed25519` 파일이 있다면 새 키로 덮어쓰지 말고 기존 키를
사용합니다.

Windows PowerShell에서 키가 없을 때만 다음 명령을 실행합니다.

```powershell
ssh-keygen -t ed25519 -C "discordbot-admin"
```

일반적인 관리용 키에는 암호를 설정하고 Windows `ssh-agent`에 한 번 등록하는
방식을 권장합니다. 관리자 권한 PowerShell에서 서비스를 준비한 뒤, 일반
PowerShell에서 키를 등록합니다.

```powershell
# 관리자 권한 PowerShell
Set-Service -Name ssh-agent -StartupType Automatic
Start-Service ssh-agent

# 일반 PowerShell
ssh-add $env:USERPROFILE\.ssh\id_ed25519
```

공개 키(`.pub`)만 Pi에 등록합니다. 아래의 `botserver.local`은 실제 서버 주소가
다르면 해당 주소로 바꿉니다.

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub |
  ssh os@botserver.local "umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys"
```

등록 후 새 PowerShell 창에서 접속을 확인합니다.

```powershell
ssh os@botserver.local "echo SSH_KEY_OK"
```

`SSH_KEY_OK`가 표시되면 정상입니다. 개인 키인 `id_ed25519`, 키 암호,
`.env` 내용은 문서·GitHub·메신저에 올리지 않습니다. `id_ed25519.pub`만
서버에 전달할 수 있습니다. 서버 운영체제를 다시 설치해 호스트 키가 바뀐
경우에는 경고를 무시하지 말고, 실제 서버가 맞는지 먼저 확인한 뒤 기존
`known_hosts` 기록을 정리합니다.

---

## 💻 2단계: 최신 업데이트 및 기초 프로그램 설치

라즈베리파이 전원이 켜지고 1~2분 뒤, SSH 원격 접속 프로그램(예: PuTTY)이나 직접 연결된 모니터/키보드를 통해 터미널 화면(검은 창)에 접속합니다.

접속하면 아래 명령어를 **한 줄씩 복사해서 붙여넣고 엔터**를 누르세요.

```bash
# 1. 우분투 시스템을 최신 상태로 업데이트
sudo apt update && sudo apt upgrade -y

# 2. 봇 구동에 필요한 필수 프로그램 설치 (파이썬, 깃, 멀티미디어 재생기 FFmpeg 등)
sudo apt install git python3 python3-venv python3-pip ffmpeg sqlite3 ntfs-3g -y
```

---

## 📥 3단계: GitHub에서 봇 코드 다운로드 (Clone)

기존 서버 설정 경로(`WorkingDirectory=/home/os/bot`)를 맞추기 위해 아래 명령어를 순서대로 입력합니다.

```bash
# 1. os 사용자의 기본 폴더로 이동합니다.
cd /home/os

# 2. 깃허브에서 봇 코드를 'bot' 이라는 이름의 폴더로 다운로드 받습니다.
git clone https://github.com/lgw323/Bot.git bot

# 3. 방금 다운받은 bot 폴더로 들어갑니다.
cd bot
```

---

## 🐍 4단계: 파이썬 가상환경 만들기 및 라이브러리 설치

안전한 실행을 위해 파이썬 가상환경(`bot_env`)을 만들고 필요한 부품을 설치합니다. 터미널은 계속 `/home/os/bot` 위치여야 합니다.

```bash
# 1. 'bot_env' 라는 이름의 파이썬 가상환경을 만듭니다.
python3 -m venv bot_env

# 2. 가상환경에 접속합니다. (프롬프트 앞쪽에 (bot_env) 가 생겨야 정상입니다.)
source bot_env/bin/activate

# 3. 봇 실행에 필요한 모든 파이썬 라이브러리를 한 번에 설치합니다.
pip install -r requirements.txt

# 4. 데이터베이스 및 스크립트 실행 폴더 권한 부여 (필수)
chmod -R 777 scripts/
chmod -R 777 data/
```

---

## 🔑 5단계: 환경변수 설정 (.env 파일 옮기기)

봇이 구동되려면 디스코드 봇 토큰이 담긴 비밀번호 파일(`.env`)이 필요합니다.
라즈베리파이에서 직접 만들지 않고, **메인 PC의 명령 프롬프트(윈도우 cmd) 창에서 명령어 한 줄로 전송**하는 가장 깔끔한 방식을 사용합니다.

1. **메인 PC(현재 사용 중인 윈도우)**에서 키보드의 `Windows Key + R`을 누른 후, `cmd`를 입력해 검은색 창(명령 프롬프트)을 켭니다.
2. 아래 명령어를 그대로 복사해서 붙여넣고 엔터를 치세요. (현재 메인 PC의 봇 폴더로 이동)
   ```cmd
   cd Desktop\1_programming\4_python\DiscordBot
   ```
3. 다음 명령어를 입력해 `.env` 파일을 라즈베리파이 서버로 복사합니다. (`192.168.0.x` 부분은 라즈베리파이의 원격 접속 IP 주소로 바꿔주세요)
   ```cmd
   scp .env os@192.168.0.x:/home/os/bot/
   ```
4. 혹시 `Are you sure you want to continue connecting (yes/no)?` 라고 물어보면 `yes`를 치고 엔터를 누릅니다.
5. 라즈베리파이 접속 비밀번호를 입력하고 엔터를 치면 파일 전송이 1초 만에 깔끔히 완료됩니다!

---

## ⚙️ 6단계: 서비스 데몬 설정 (Systemd - 자동 재시작 및 백그라운드 구동)

라즈베리파이를 껐다 켜도 봇이 24시간 내내 혼자 구동되도록 설정합니다.

```bash
# 1. 서비스를 관리하는 파일을 관리자 권한으로 엽니다.
sudo nano /etc/systemd/system/discordbot.service
```
👉 아래 내용을 전부 복사해서 붙여넣습니다. (하단의 **8단계 설정 백업본** 기반)

```ini
[Unit]
Description=Discord Music Bot
Wants=network-online.target
After=network-online.target

[Service]
User=os
WorkingDirectory=/home/os/bot

# 봇 실행 명령어 (가상환경 경로 주의)
ExecStart=/home/os/bot/bot_env/bin/python main_bot.py

# 봇이 죽으면 무조건 다시 시작 (핵심 안정성 기능)
Restart=always
# 실패 시 1초만에 연속 재시작하지 않고 5초 대기 (정전/인터넷 지연 방어)
RestartSec=5

[Install]
WantedBy=multi-user.target
```
👉 **`Ctrl + O` -> `Enter` -> `Ctrl + X`** 로 저장하고 나옵니다.

이제 서비스를 시스템에 등록하고 바로 봇을 켭니다.
```bash
# 2. 시스템 데몬 파일 새로고침
sudo systemctl daemon-reload

# 3. 부팅 시 자동 시작 등록
sudo systemctl enable discordbot.service

# 4. 지금 바로 봇 켜기
sudo systemctl start discordbot.service

# 5. 상태 확인 (초록색 글씨로 active (running) 이 뜨면 성공!)
sudo systemctl status discordbot.service
```
(상태 확인창에서 빠져나오려면 키보드 `q`를 누르세요.)

---

## ⏰ 7단계: 자동 업데이트 및 백업 스케줄러 등록 (Crontab)

GitHub에 새 코드가 올라오면 스스로 업데이트하고 영구적인 백업을 하기 위한 스케줄러 설정입니다.

```bash
# 1. 일반 크론탭 열기 (명령어 입력 시 에디터를 고르라고 나오면 보통 1번 nano 선택)
crontab -e
```
👉 파일 맨 아래에 다음 내용을 복사해서 붙여넣습니다.

```text
# 1. [실시간 감지] GitHub 코드 변경 또는 이전 실패를 확인하고 재시도 (5분 주기)
*/5 * * * * /home/os/bot/scripts/auto_update.sh

# 2. [일일 정기 점검] yt-dlp만 최신화하고 성공 시 봇 재시작 (매일 새벽 04:00)
3 4 * * * /home/os/bot/scripts/auto_update.sh --daily

# 3. [데이터 백업] 6시간마다 사용자 데이터 GitHub 'db-backup' 브랜치로 단일 푸시 및 내부 최대 7일 롤백 저장 (0, 6, 12, 18시) 
3 */6 * * * /home/os/bot/scripts/auto_backup.sh
```
👉 **`Ctrl + O` -> `Enter` -> `Ctrl + X`** 로 저장하고 나옵니다.

> DB 백업에는 `.env`의 유효한 `DB_ENCRYPTION_KEY`가 반드시 필요합니다. 새
> `data/database_backup.sql`은 확장자와 경로는 유지하지만, 내용은 사용자 ID,
> 음악 정보와 SQL 구조까지 포함해 파일 전체가 암호화됩니다. 텍스트 편집기로
> SQL을 읽을 수 없는 것이 정상입니다. 복구할 서버에도 백업을 만들 때 사용한 것과
> 같은 키가 필요하므로 `.env`와 별도로 키를 안전하게 보관해야 합니다.
>
> 키가 없거나 잘못됐거나 SQL 생성·검증·암호화 확인이 실패하면 새 백업으로
> 교체하지 않고 마지막 정상 백업을 유지합니다. 예전 일부 필드 암호화 백업은
> 복구할 수 있지만, 앞으로 생성하는 백업은 파일 전체 암호화 형식입니다.
> SQL 생성, Pi의 날짜별 보관 또는 원격 `db-backup` 업로드 중 하나라도 실패하면
> 스크립트는 성공으로 처리하지 않고 `backup.log`에 실패 원인을 남깁니다. 따라서
> cron의 실행 결과와 로그를 함께 확인할 수 있습니다.
>
> 코드 변경을 발견하면 원격 `requirements.txt`를 먼저 읽고 `-U` 없이 필요한
> 패키지만 준비합니다. 이 과정이 성공한 뒤에만 코드를 `origin/main`으로
> 맞춥니다. 새 코드로 서비스가 정상 재시작한 뒤에는 이번에 폐기한 음성 수신,
> 음성 인식, 이전 YouTube 검색 및 옛 Gemini 패키지를 제거합니다. 제거 작업만
> 실패한 경우 실행 중인 봇은 유지하고 경고를 기록합니다. `--daily`는 YouTube
> 변경 대응이 필요한 `yt-dlp`만 최신화합니다.
>
> Git 조회, 패키지 설치 또는 서비스 재시작이 실패하면 성공 로그를 남기지 않으며
> `data/update_pending`을 만들어 다음 5분 cron 실행에서 다시 시도합니다. 새 코드로
> 재시작하지 못한 경우에는 직전 커밋으로 한 번 되돌리고 서비스를 복구합니다.
> 무한 반복은 하지 않으므로 `update.log`에 수동 확인 메시지가 있으면 아래 로그
> 확인 절차를 따르세요.
>
> 스크립트는 정상 배치 시 `git reset --hard origin/main`을 사용하므로 Pi에서 직접
> 수정한 파일은 여전히 보존되지 않습니다. Pi는 실행 전용 서버로 사용해야 합니다.

이제 일주일에 한 번씩 라즈베리파이 기기 자체를 강제로 껐다 켜서 메모리를 청소하는 관리자(sudo) 크론탭을 설정합니다.
```bash
# 2. 관리자용 크론탭 열기
sudo crontab -e
```
👉 파일 맨 아래에 다음 내용을 추가합니다. (매주 일요일 오전 5시 재부팅)

```text
0 5 * * 0 sudo /sbin/reboot
```
👉 마지막으로 저장하고 나옵니다. **`Ctrl + O` -> `Enter` -> `Ctrl + X`**

---

## 🛠️ 8단계: 운영 상태 확인

서비스 상태와 최근 systemd 로그를 확인합니다.

```bash
sudo systemctl status discordbot.service
sudo journalctl -u discordbot.service -n 100 --no-pager
```

봇 로그, 자동 업데이트 로그와 백업 로그를 각각 확인할 수 있습니다.

```bash
tail -f ~/bot/data/logs/system.log
tail -f ~/bot/data/logs/update.log
tail -f ~/bot/data/logs/backup.log
```

백업 성공 여부는 `backup.log`, 최근 로컬 복구본은 `data/archives/`, 원격 최신
복구본은 `db-backup` 브랜치에서 확인합니다. 실제 DB 교체나 SQL 복구는 데이터
손실 위험이 있으므로 대상 백업의 시점과 크기를 확인한 뒤 진행합니다.

`backup.log`에 `ERROR`가 있으면 그 실행에서는 원격 백업까지 완료되지 않은
것입니다. 오류를 해결한 뒤 다음 cron 실행을 기다리거나 스크립트를 다시 실행하고,
새 `Backup successful` 기록과 `db-backup` 브랜치의 갱신 시각을 함께 확인합니다.

🎉 **설치 및 환경 세팅이 모두 완료되었습니다!** 이제 디스코드에서 봇이 온라인인지 확인하고 사용하시면 됩니다.
