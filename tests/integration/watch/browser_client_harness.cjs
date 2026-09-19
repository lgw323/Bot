// Execute the shipped inline client with controlled DOM, sockets, iframe and clock.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const html = fs.readFileSync(process.argv[2], 'utf8');
const source = html.match(/<script nonce="__WATCH_NONCE__">([\s\S]*?)<\/script>/)[1];
const elements = new Map(), listeners = new Map(), timers = new Map(), sockets = [];
let sequence = 0;
function element() {
    return {children: [], style: {}, value: '', className: '', innerText: '', textContent: '',
        set innerHTML(value) {this.children=[];},
        classList: {add() {}, remove() {}}, addEventListener() {},
        appendChild(item) { this.children.push(item); }, append(...items) {this.children.push(...items);},
        replaceChildren(...items) {this.children = items;}, remove() {}};
}
class Socket {
    static CONNECTING = 0; static OPEN = 1; static CLOSING = 2; static CLOSED = 3;
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
    send(data) {this.sent.push(JSON.parse(data));}
    open() {this.readyState = 1; this.onopen();}
    close(code = 1000) {this.readyState = 3; this.onclose({code});}
    receive(value) {this.onmessage({data: JSON.stringify(value)});}
}
const on = (name, callback) => listeners.set(name, callback);
const document = {visibilityState: 'visible', addEventListener: on,
    getElementById(id) {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);},
    createElement: element, querySelectorAll: () => []};
const window = {location: {search:'?session=synthetic-capability',protocol:'https:',host:'watch.example.test',origin:'https://watch.example.test'},
    stop() {}, addEventListener: on};
let state = 5, time = 0, loaded = null;
const player = {getPlayerState:()=>state, getCurrentTime:()=>time,
    getVideoData:()=>({video_id:loaded}),
    loadVideoById(media) {loaded=media.videoId;time=media.startSeconds;state=1;},
    cueVideoById(media) {loaded=media.videoId;time=media.startSeconds;state=5;}, seekTo(value) {time=value;}, playVideo() {state=1;}, pauseVideo() {state=2;}};
const context = vm.createContext({window,document,URLSearchParams,WebSocket:Socket,console,
    YT:{PlayerState:{UNSTARTED:-1,PLAYING:1,PAUSED:2,ENDED:0,CUED:5},Player:function(){return player;}},
    setInterval:()=>0, setTimeout:(callback,delay)=>{timers.set(++sequence,{callback,delay});return sequence;},
    clearTimeout:id=>timers.delete(id), alert(){}, AbortSignal:{timeout:()=>undefined},
    fetch:async()=>({ok:true,status:200,json:async()=>({playlist:[]})})});
vm.runInContext(source,context);
function ready() {context.onYouTubeIframeAPIReady();context.onPlayerReady({});}
function socket() {if (!sockets.length) ready();const value=sockets.at(-1);value.open();return value;}
function fireDelay(delay) {for (const [id,timer] of [...timers]) if(timer.delay===delay){timers.delete(id);timer.callback();}}
const scenario=process.argv[3];
if (scenario==='iframe-independent-presence') {
    assert.equal(sockets.length,1,'presence must connect before YouTube readiness');
    const ws=socket();
    ws.receive({type:'user_list',users:['Synthetic A','Synthetic B'],revision:2});
    assert.equal(elements.get('users-badge-list').children.length,2);
    ws.receive({type:'user_list',users:[],revision:1});
    assert.equal(elements.get('users-badge-list').children.length,2,'stale revision ignored');
    ready(); assert.equal(sockets.length,1,'iframe readiness cannot duplicate a socket');
} else if (scenario==='empty-player-protocol') {
    ready(); const ws=socket();
    ws.receive({type:'sync_request',revision:1});
    ws.receive({type:'user_joined',message:'Synthetic join',revision:2});
    assert.equal(ws.sent.filter(v=>v.type==='sync_response').length,0,'empty iframe must not send null videoId');
} else if (scenario==='hydrate-before-player') {
    assert.equal(sockets.length,1,'socket must precede iframe');
    const ws=socket();
    ws.receive({type:'sync_response',state:'paused',time:17,videoId:'aaaaaaaaaaa',revision:2});
    ready(); assert.equal(loaded,'aaaaaaaaaaa'); assert.equal(time,17); assert.equal(state,5);
} else if (scenario==='select-before-player') {
    const ws=socket();
    context.loadVideoById('aaaaaaaaaaa');
    assert.equal(ws.sent.at(-1).videoId,'aaaaaaaaaaa','selection must reach peers before iframe readiness');
    ready(); assert.equal(loaded,'aaaaaaaaaaa'); assert.equal(state,1);
    assert.equal(ws.sent.filter(v=>v.type==='sync_response').length,1);
} else if (scenario==='recoverable-return') {
    const ws=socket(); ws.receive({type:'user_list',users:['Synthetic'],revision:1});
    ws.close(4008);
    assert.ok([...timers.values()].some(t=>t.delay<3000),'recoverable closure needs prompt bounded retry');
    assert.ok(listeners.has('visibilitychange'),'browser return must check transport');
    listeners.get('visibilitychange')();
    assert.equal(sockets.length,2); const newer=sockets.at(-1);newer.open();
    ws.close(4001); // A retired socket must not make the replacement terminal.
    newer.receive({type:'user_list',users:['Synthetic','Returned'],revision:2});
    assert.equal(elements.get('users-badge-list').children.length,2);
} else if (scenario==='terminal-stays-closed') {
    const ws=socket();ws.close(4003);
    listeners.get('visibilitychange')?.();listeners.get('online')?.();
    fireDelay(500);fireDelay(1000);fireDelay(3000);
    assert.equal(sockets.length,1,'revoked session cannot be reconnected');
} else if (scenario==='page-lifecycle') {
    const ws=socket();
    assert.ok(listeners.has('pagehide') && listeners.has('pageshow'));
    listeners.get('pagehide')();assert.equal(ws.readyState,Socket.CLOSED);
    listeners.get('pageshow')();assert.equal(sockets.length,2);
} else if (scenario==='bounded-reconnect') {
    let ws=socket();
    for (let attempt=0;attempt<5;attempt++) {
        ws.close(1006);
        const next=[...timers].find(([,t])=>t.callback===context.initWebSocket);
        assert.ok(next,'retry must be scheduled');
        timers.delete(next[0]);next[1].callback();
        ws=sockets.at(-1);ws.open();
    }
    ws.close(1006);
    assert.equal(sockets.length,6);
    assert.equal([...timers.values()].filter(t=>t.callback===context.initWebSocket).length,0);
} else if (scenario==='return-open-probe') {
    const ws=socket();ws.receive({type:'user_list',users:['Synthetic'],revision:1});
    listeners.get('visibilitychange')();
    assert.equal(ws.sent.at(-1).type,'sync_request');
    ws.receive({type:'user_list',users:['Synthetic'],revision:2});
    fireDelay(2000);assert.equal(ws.readyState,Socket.OPEN,'server response cancels return watchdog');
    listeners.get('visibilitychange')();fireDelay(2000);
    assert.equal(ws.readyState,Socket.CLOSED,'half-open connection is replaced after a bounded probe');
} else { throw new Error('unknown synthetic scenario'); }
console.log('PASS '+scenario);
