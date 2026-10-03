"""A6V1 real-DOM/iframe boundary cases. Changes only synthetic scenario/provider.
Uses reviewed A6R1 transport/profile machinery; product source stays unchanged.
"""
import importlib.util
import inspect
from pathlib import Path
import sys
ROOT=Path.cwd()
spec=importlib.util.spec_from_file_location('a6v1_browser_base',ROOT/'tests/browser/watch_terminal_chrome.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
mode=sys.argv[1]
assert mode in {'before-api','before-ready','session-event','destroy-throws','reconnect'}
m.MODE=mode
m.PROVIDER=m.PROVIDER.replace('window.YT=', "window.__constructs=0;window.__commands=[];window.__providerLoaded=true;window.YT=")
m.PROVIDER=m.PROVIDER.replace("Player:function(id,options){", "Player:function(id,options){window.__constructs++;window.__events=options.events;")
m.PROVIDER=m.PROVIDER.replace("const notify=()=>options.events.onReady({target:player});", "window.__player=player;const notify=()=>{window.__notify=()=>options.events.onReady({target:player});if(!location.search.includes('mode=before-ready'))__notify();};")
for name in ('seekTo','playVideo','pauseVideo','loadVideoById','cueVideoById'):
    marker={'seekTo':'seekTo:t=>{','playVideo':'playVideo:()=>','pauseVideo':'pauseVideo:()=>','loadVideoById':'loadVideoById:value=>{','cueVideoById':'cueVideoById:value=>{'}[name]
    if name in ('playVideo','pauseVideo'):
        original=marker+('audio.play()' if name=='playVideo' else 'audio.pause()')
        replacement=marker+"{__commands.push('"+name+"');return "+('audio.play()' if name=='playVideo' else 'audio.pause()')+';}'
    else:
        original=marker;replacement=marker+"__commands.push('"+name+"');"
    assert original in m.PROVIDER
    m.PROVIDER=m.PROVIDER.replace(original,replacement)
m.PROVIDER=m.PROVIDER.replace('onYouTubeIframeAPIReady();', "if(!location.search.includes('mode=before-api'))onYouTubeIframeAPIReady();")
source=inspect.getsource(m.main)
def swap(old,new):
    global source
    assert source.count(old)==1,(old,source.count(old))
    source=source.replace(old,new)
swap('template = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "src/discordbot/watch/adapters/templates/player.html"', 'template = ROOT / "src/discordbot/watch/adapters/templates/player.html"')
swap('prefix="discordbot-a6r1-chrome-"','prefix="discordbot-a6v1-chrome-"')
swap('error.sent.code != 4001', 'error.sent.code not in ({4001,4008} if MODE=="reconnect" else {4001})')
swap('tab.call("Page.navigate", url=f"http://127.0.0.1:{port}/watch?session={room}")', '''tab.call("Page.enable")
                tab.call("Page.addScriptToEvaluateOnNewDocument", source="""
window.__intervals=new Set();window.__pageListeners=new Set();
const si=window.setInterval.bind(window),ci=window.clearInterval.bind(window);
window.setInterval=(...args)=>{const id=si(...args);__intervals.add(id);return id;};
window.clearInterval=id=>{__intervals.delete(id);return ci(id);};
for(const target of [window,document]){
 const add=target.addEventListener.bind(target),remove=target.removeEventListener.bind(target);
 target.addEventListener=(name,fn,...rest)=>{if(['online','pageshow','pagehide','visibilitychange'].includes(name))__pageListeners.add(fn);return add(name,fn,...rest);};
 target.removeEventListener=(name,fn,...rest)=>{__pageListeners.delete(fn);return remove(name,fn,...rest);};
}
""")
                suffix = '&mode='+MODE if room=='target' else ''
                tab.call("Page.navigate", url=f"http://127.0.0.1:{port}/watch?session={room}{suffix}")''')
swap('wait_for(lambda: tab.evaluate("!!window.__media && !__media.paused && __media.currentTime>42"))', '''condition="!!window.__media && !__media.paused && __media.currentTime>42"
                    if room=='target' and MODE=='before-api':condition="window.__providerLoaded && !window.__constructs && ws?.readyState===1 && !!pendingPlayback"
                    if room=='target' and MODE=='before-ready':condition="!!window.__notify && !playerReady && ws?.readyState===1 && !!pendingPlayback"
                    wait_for(lambda: tab.evaluate(condition))''')
source=source.replace('"__media.currentTime"','"window.__media?.currentTime||0"')
swap('peers["target"].close(4001)', '''# Genuine DOM escaping and bounded message retention.
            control.evaluate("""window.__xss=0;const bad='<img src=x onerror="window.__xss=1">';
appendChatMessage(bad,bad);updateUsersList([bad]);
playlist=[{video_url:'https://youtu.be/aaaaaaaaaaa',video_title:bad,added_by:bad}];renderPlaylist();
""")
            assert control.evaluate("!__xss && !document.querySelector('#chat-messages img') && !document.querySelector('#users-badge-list img') && !document.querySelector('.item-title img')")
            control.evaluate("for(let i=0;i<250;i++)appendSystemMessage('synthetic '+i)")
            assert control.evaluate("document.querySelector('#chat-messages').children.length") == 200
            if MODE=='reconnect':
                target.evaluate("window.__retired=ws")
                peers['target'].close(4008)
                wait_for(lambda: joins['target']==2 and target.evaluate("ws!==__retired && ws.readyState===1 && !__media.paused"))
                target.evaluate("__retired.onclose({code:4001});__retired.onmessage({data:JSON.stringify({type:'sync_response',revision:999,videoId:'bbbbbbbbbbb',state:'paused',time:0})})")
                assert target.evaluate("!terminal && !window.__destroyed && !!document.querySelector('iframe#yt-player') && !__media.paused")
            owned=target.evaluate('__constructs')
            if MODE=='destroy-throws':
                target.evaluate("player.destroy=()=>{window.__destroyed=(window.__destroyed||0)+1;throw Error('synthetic provider failure')}")
            if MODE=='session-event':
                target.evaluate("ws.close=()=>{window.__closeRequested=true}")
                peers['target'].send(json.dumps({'type':'session_closed','revision':999}))
            else:
                peers['target'].close(4001)''')
swap('target.evaluate("window.dispatchEvent(new Event(\'online\'));window.dispatchEvent(new Event(\'pageshow\'));onYouTubeIframeAPIReady();")', '''command_count=target.evaluate('__commands.length')
            for _ in range(3):
                target.evaluate("""window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('pageshow'));onYouTubeIframeAPIReady();
window.__notify?.();if(window.__events){for(const name of ['onReady','onStateChange','onAutoplayBlocked','onError'])__events[name]?.({target:__player,data:1})}
loadVideoById('bbbbbbbbbbb');receivePlayback({videoId:'bbbbbbbbbbb',state:'playing',time:0});document.getElementById('resume-playback-btn').click();
ws.onmessage({data:JSON.stringify({type:'sync_response',revision:10000,videoId:'bbbbbbbbbbb',state:'playing',time:0})});ws.onclose({code:4001});
""")
            assert target.evaluate('__commands.length')==command_count
            assert target.evaluate('__constructs')==owned
            assert target.evaluate('__intervals.size===0 && __pageListeners.size===0 && player===null && pendingPlayback===null && !playerReady')''')
swap('assert target.evaluate("window.__destroyed") == 1', 'assert target.evaluate("window.__destroyed||0") == (0 if MODE=="before-api" else 1)')
swap('assert joins == {"target": 1, "control": 1}, joins', 'assert joins == {"target": 2 if MODE=="reconnect" else 1, "control": 1}, joins')
swap('"result": "PASS", "browser":', '"result": "PASS", "case":MODE, "browser":')
exec(compile(source,'a6v1-browser-boundaries','exec'),m.__dict__)
m.main()
