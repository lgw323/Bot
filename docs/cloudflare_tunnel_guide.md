# ☁️ Cloudflare Tunnel을 활용한 라즈베리파이 외부 접속 및 개인 도메인 연결 가이드

이 문서는 복잡한 공유기 설정(포트포워딩, DDNS 등)을 전혀 모르는 초보자도 **단 10분 만에 안전하게 외부 접속 통로를 뚫고, 내가 구매한 도메인을 연결하는 방법**을 한 줄 한 줄 쉽게 풀어 설명한 가이드입니다.

---

## 💡 Cloudflare Tunnel(터널)이 무엇인가요?
우리 집 공유기 설정을 건드리지 않고, 라즈베리파이 서버와 Cloudflare 사이에 **"안전한 암호화 비밀 터널"**을 파는 기술입니다.
* **보안성 최고**: 외부로 나가는 포트를 열지 않아 해킹 위협이 없습니다.
* **DDNS 불필요**: 인터넷 IP 주소가 매일 바뀌어도 자동으로 주소를 유지해 줍니다.
* **개인 도메인 사용 가능**: 내가 구매한 멋진 도메인(예: `watch.mybot.com`)으로 바로 접속할 수 있습니다.

---

## 🛠️ 준비물
1. **라즈베리파이 5** (봇이 켜져 있는 서버)
2. **Cloudflare 무료 계정** (가입 후 카드 등록이 필요할 수 있으나, 본 서비스는 **100% 무료**입니다.)
3. **내가 구매한 개인 도메인** (가비아, 후이즈 등 어디서 구매했든 상관없음)

---

## 🚀 1단계: 내 도메인을 Cloudflare에 연결하기 (처음 한 번만)

1. [Cloudflare 홈페이지](https://www.cloudflare.com/)에 가입하고 로그인합니다.
2. 메인 화면에서 **[사이트 추가]** 버튼을 누르고, 구매한 도메인 주소(예: `yourdomain.com`)를 입력합니다.
3. 요금제 선택 창이 나오면 아래로 쭉 내려서 **[Free ($0)] (무료)** 요금제를 선택합니다.
4. Cloudflare가 기존 도메인의 주소 레코드(DNS)를 자동으로 긁어옵니다. 그냥 **[계속]**을 누릅니다.
5. 화면에 **"네임서버 변경"** 안내와 함께 2개의 Cloudflare 네임서버 주소가 뜹니다.
   * 예: `ashley.ns.cloudflare.com`, `will.ns.cloudflare.com`
6. **도메인을 구매한 사이트(가비아 등)**에 로그인하여 내 도메인의 **네임서버(DNS) 설정**으로 들어갑니다.
7. 기존의 네임서버 주소들을 지우고, 방금 5번에서 받은 **Cloudflare 네임서버 2개**로 덮어씁니다.
8. 변경사항을 저장합니다. (네임서버가 전 세계로 퍼지는 데는 최소 5분에서 최대 하루 정도 걸리나, 보통 10분 내로 처리됩니다.)

---

## 💻 2단계: 라즈베리파이에 터널 프로그램 설치하기

라즈베리파이 터널에 SSH로 접속하여 아래 명령어들을 **한 줄씩 복사해서 붙여넣고 엔터**를 칩니다.

```bash
# 1. 터널 프로그램(cloudflared) 다운로드 폴더 만들기 및 이동
mkdir -p ~/.cloudflared && cd ~/.cloudflared

# 2. 라즈베리파이5(ARM64 아키텍처) 전용 최신 설치 파일 다운로드
wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64

# 3. 다운로드한 파일 이름을 cloudflared로 변경하고 권한 주기
mv cloudflared-linux-arm64 cloudflared
chmod +x cloudflared

# 4. 어떤 폴더에서든 실행할 수 있도록 시스템 전역 폴더로 복사
sudo cp cloudflared /usr/local/bin/
```

---

## 🔑 3단계: 내 터널 로그인 및 생성하기

이 단계는 라즈베리파이와 내 Cloudflare 계정을 동기화하는 단계입니다.

```bash
# 1. 로그인 명령어 실행 (라즈베리파이에서 실행)
cloudflared tunnel login
```
👉 실행하면 터널 창에 **엄청나게 긴 주소(URL)**가 한 줄 뜹니다.
1. 그 주소를 복사해서 **메인 PC의 웹 브라우저 주소창**에 붙여넣고 들어갑니다.
2. 로그인 창이 뜨면 Cloudflare 로그인을 하고, 방금 등록한 내 도메인을 선택한 후 **[Authorize (승인)]** 버튼을 누릅니다.
3. 승인이 완료되면 라즈베리파이 창에 성공 메시지가 뜹니다.

이제 나만의 비밀 터널 방을 만듭니다.
```bash
# 2. 'discord-bot-tunnel'이라는 이름의 터널 생성 (이름은 자유 변경 가능)
cloudflared tunnel create discord-bot-tunnel
```
👉 터널이 정상적으로 생성되면 화면에 **UUID(난수 문자열)**와 자격 증명 파일 경로가 출력됩니다.
* 예: `Created tunnel discord-bot-tunnel with id 1234abcd-1234-abcd-1234-abcd1234abcd`
* 이 **UUID 값**과 **경로**를 메모장에 따로 복사해 둡니다.

---

## ⚙️ 4단계: 터널 설정 파일 작성하기

터널에게 **"누가 외부에서 들어오면, 라즈베리파이 내부 8000포트(FastAPI)로 보내라!"** 하고 길을 알려주는 지도 파일(`config.yml`)을 만듭니다.

```bash
# 1. 설정 파일을 편집기로 엽니다.
nano ~/.cloudflared/config.yml
```
👉 메모장 같은 빈 화면이 뜨면, 아래 내용을 그대로 복사해서 붙여넣습니다. (단, **UUID** 부분은 본인의 것으로 수정해야 합니다.)

```yaml
tunnel: your-tunnel-uuid-here # 3단계에서 생성된 UUID 값을 여기에 넣으세요!
credentials-file: /home/os/.cloudflared/your-tunnel-uuid-here.json # UUID.json 파일 전체 경로

ingress:
  # 내가 지정할 외부 도메인 주소 입력 (구매한 도메인 앞에 watch. 을 붙여 서브도메인으로 만드는 것을 추천)
  - hostname: watch.yourdomain.com 
    service: http://localhost:8000
  - service: http_status:404
```
👉 **`Ctrl + O` -> `Enter` -> `Ctrl + X`** 키를 순서대로 눌러 저장하고 편집기를 나옵니다.

---

## 🌐 5단계: 구매한 도메인과 터널 매핑(DNS 연결)하기

내가 만든 도메인 주소(`watch.yourdomain.com`)로 접속했을 때 터널로 신호가 도달하도록 이정표를 세워줍니다.

```bash
# cloudflared tunnel route dns <터널 이름> <원하는 접속 주소>
cloudflared tunnel route dns discord-bot-tunnel watch.yourdomain.com
```
👉 이 명령어 한 줄이면 Cloudflare 사이트에 들어가서 어려운 레코드(CNAME)를 수동으로 입력할 필요 없이 자동으로 이정표 세팅이 끝납니다!

---

## 🏃 6단계: 터널 실행 및 24시간 백그라운드 서비스 등록

라즈베리파이를 재부팅해도 터널이 24시간 알아서 작동하도록 리눅스 서비스에 등록해 줍니다.

```bash
# 1. 터널을 시스템 서비스로 등록 (설정 파일 위치를 인자로 전달)
sudo cloudflared --config /home/os/.cloudflared/config.yml service install

# 2. 터널 서비스 시작
sudo systemctl start cloudflared

# 3. 터널이 정상 작동하는지 상태 확인 (active (running) 이 뜨면 대성공!)
sudo systemctl status cloudflared
```

---

## 🥳 이제 어떻게 쓰면 되나요?

1. **디스코드 봇 환경 설정 변경**:
   * 로컬 프로젝트 폴더의 `.env` 파일을 엽니다.
   * `WATCH_TOGETHER_URL` 값을 방금 세팅한 도메인 주소로 입력합니다.
     * 예: `WATCH_TOGETHER_URL=https://watch.yourdomain.com`
   * 변경된 `.env` 파일을 서버(라즈베리파이)로 다시 전송해 줍니다.
2. 디스코드에서 `/시청`을 치면, 봇이 `https://watch.yourdomain.com/watch?session=<UUID>` 주소를 뿜어냅니다.
3. 이제 **방장님이든 친구들이든 전 세계 어디에서나** 저 링크를 누르고 들어오면, 내 라즈베리파이 서버를 거쳐 광고 없는 유튜브 동시 시청 화면으로 안전하게 집결됩니다! 🎉
