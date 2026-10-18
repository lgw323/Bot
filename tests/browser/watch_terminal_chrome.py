"""Opt-in local Chrome proof: shipped JS, real iframe/audio, synthetic loopback WS.

Run with the existing development Python; no YouTube, Discord, credentials or DB.
The fake provider owns a genuine browser media element. Removing its iframe must
stop that media clock while the other room's clock continues.
"""
from __future__ import annotations

from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener, ProxyHandler
import wave

from websockets.datastructures import Headers
from websockets.http11 import Response
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect
from websockets.sync.server import serve


ROOT = Path(__file__).resolve().parents[2]
CHROME = Path("C:/Program Files/Google/Chrome/Application/chrome.exe")
PROVIDER = r"""
window.YT={PlayerState:{UNSTARTED:-1,PLAYING:1,PAUSED:2,ENDED:0,CUED:5},
Player:function(id,options){
 const iframe=document.createElement('iframe');iframe.id=id;iframe.src='/media';
 document.getElementById(id).replaceWith(iframe);
 let audio,videoId=null,state=-1;
 const player={getVideoData:()=>({video_id:videoId}),getCurrentTime:()=>audio.currentTime,
 getPlayerState:()=>state,seekTo:t=>{audio.currentTime=t;},
 playVideo:()=>audio.play(),pauseVideo:()=>audio.pause(),
 loadVideoById:value=>{videoId=value.videoId;audio.currentTime=value.startSeconds;audio.play();},
 cueVideoById:value=>{videoId=value.videoId;audio.currentTime=value.startSeconds;audio.pause();state=5;},
 destroy:()=>{window.__destroyed=(window.__destroyed||0)+1;iframe.remove();}};
 iframe.onload=()=>{
  audio=iframe.contentDocument.querySelector('audio');window.__media=audio;
  const notify=()=>options.events.onReady({target:player});
  audio.addEventListener('playing',()=>{state=1;options.events.onStateChange({target:player,data:1});});
  audio.addEventListener('pause',()=>{state=2;options.events.onStateChange({target:player,data:2});});
  if(audio.readyState>=1)notify();else audio.addEventListener('loadedmetadata',notify,{once:true});
 };
 return player;
}};
onYouTubeIframeAPIReady();
"""


class CDP:
    def __init__(self, url: str) -> None:
        self.ws = connect(url, proxy=None, open_timeout=5)
        self.sequence = 0

    def call(self, method: str, **params: object) -> dict:
        self.sequence += 1
        self.ws.send(json.dumps({"id": self.sequence, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv(timeout=10))
            if reply.get("id") == self.sequence:
                assert "error" not in reply, reply
                return reply.get("result", {})

    def evaluate(self, expression: str):
        reply = self.call("Runtime.evaluate", expression=expression, returnByValue=True)
        assert "exceptionDetails" not in reply, reply
        return reply["result"].get("value")

    def close(self) -> None:
        self.ws.close()


def wait_for(probe, timeout: float = 10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("local browser verification deadline")


def main() -> None:
    assert CHROME.is_file(), "Existing Chrome is required; do not install automatically"
    template = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src/discordbot/watch/adapters/templates/player.html"
    html = template.read_text(encoding="utf-8")
    html = html.replace('https://www.youtube.com/iframe_api', '/provider.js')
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        wav.writeframes(b"\0\0" * 8000 * 120)
    peers, joins = {}, {"target": 0, "control": 0}

    def request(connection, incoming):
        path = incoming.path.split("?", 1)[0]
        if path.startswith("/ws/"):
            return None
        if path == "/watch":
            body, mime = html.encode(), "text/html; charset=utf-8"
        elif path == "/provider.js":
            body, mime = PROVIDER.encode(), "text/javascript"
        elif path == "/media":
            body, mime = b'<audio src="/silence.wav" preload="auto"></audio>', "text/html"
        elif path == "/silence.wav":
            body, mime = buf.getvalue(), "audio/wav"
            if incoming.headers.get("Range"):
                start, end = incoming.headers["Range"].removeprefix("bytes=").split("-")
                first, last = int(start), int(end) if end else len(body) - 1
                chunk = body[first:last + 1]
                return Response(206, "Partial Content", Headers({"Content-Type": mime,
                    "Content-Length": str(len(chunk)), "Accept-Ranges": "bytes",
                    "Content-Range": f"bytes {first}-{last}/{len(body)}"}), chunk)
        else:
            body, mime = b'{"playlist":[]}', "application/json"
        return Response(200, "OK", Headers({"Content-Type": mime, "Content-Length": str(len(body)),
            "Accept-Ranges": "bytes"}), body)

    def socket(connection):
        room = connection.request.path.rsplit("/", 1)[-1]
        peers[room] = connection
        try:
            for raw in connection:
                if json.loads(raw).get("type") == "join":
                    joins[room] += 1
                    connection.send(json.dumps({"type": "sync_response", "revision": 1,
                        "videoId": "aaaaaaaaaaa", "state": "playing", "time": 42}))
        except ConnectionClosed as error:
            if error.sent is None or error.sent.code != 4001:
                raise

    with tempfile.TemporaryDirectory(prefix="discordbot-a6r1-chrome-") as profile, ExitStack() as stack:
        server = stack.enter_context(serve(socket, "127.0.0.1", 0, process_request=request, close_timeout=1))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.socket.getsockname()[1]
        process = subprocess.Popen([
            str(CHROME), "--headless=new", "--remote-debugging-port=0", "--remote-debugging-address=127.0.0.1",
            "--user-data-dir=" + profile, "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-sync",
            "--proxy-server=http://127.0.0.1:9", "--proxy-bypass-list=127.0.0.1;localhost",
            "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost",
            "--autoplay-policy=no-user-gesture-required", "--mute-audio", "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        browser = None
        try:
            active = Path(profile) / "DevToolsActivePort"
            wait_for(active.exists)
            lines = active.read_text().splitlines()
            browser = CDP(f"ws://127.0.0.1:{lines[0]}{lines[1]}")
            tabs = []
            opener = build_opener(ProxyHandler({}))
            for room in ("target", "control"):
                target = browser.call("Target.createTarget", url="about:blank")["targetId"]
                with opener.open(f"http://127.0.0.1:{lines[0]}/json/list", timeout=5) as response:
                    info = next(row for row in json.load(response) if row["id"] == target)
                tab = CDP(info["webSocketDebuggerUrl"])
                stack.callback(tab.close)
                tab.call("Page.navigate", url=f"http://127.0.0.1:{port}/watch?session={room}")
                try:
                    wait_for(lambda: tab.evaluate("!!window.__media && !__media.paused && __media.currentTime>42"))
                except AssertionError:
                    print(tab.evaluate("JSON.stringify({api:typeof YT,ready:playerReady,terminal,pending:pendingPlayback,ws:ws?.readyState,media:window.__media && {paused:__media.paused,time:__media.currentTime,ready:__media.readyState,error:__media.error?.code}})"))
                    raise
                tabs.append(tab)
            target, control = tabs
            before = [tab.evaluate("__media.currentTime") for tab in tabs]
            peers["target"].close(4001)
            wait_for(lambda: target.evaluate("terminal"))
            assert target.evaluate("!document.querySelector('iframe#yt-player')"), "terminal iframe remains attached"
            target.evaluate("window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('pageshow'));onYouTubeIframeAPIReady();")
            stopped = target.evaluate("__media.currentTime")
            time.sleep(1)
            after = [tab.evaluate("__media.currentTime") for tab in tabs]
            assert abs(after[0] - stopped) < 0.05, (stopped, after)
            assert after[1] > before[1] + 0.5, (before, after)
            assert target.evaluate("window.__destroyed") == 1
            assert control.evaluate("!terminal && !!document.querySelector('iframe#yt-player')")
            assert joins == {"target": 1, "control": 1}, joins
            print(json.dumps({"result": "PASS", "browser": browser.call("Browser.getVersion")["product"],
                "before": before, "stopped": stopped, "after": after, "joins": joins,
                "network": "synthetic loopback HTTP/WS/media only"}))
        finally:
            if browser:
                try:
                    browser.call("Browser.close")
                except ConnectionClosed:
                    # Chrome may close its debugging channel before acknowledging exit.
                    if process.poll() is None:
                        process.terminate()
                finally:
                    browser.close()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                # Only this owned temporary Chrome process tree; never shared browsers.
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=True, capture_output=True)
                process.wait(timeout=5)
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


if __name__ == "__main__":
    main()
