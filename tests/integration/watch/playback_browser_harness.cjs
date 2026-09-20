// Two independent shipped-client VMs, asynchronous iframe commands and no network.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8').match(/<script nonce="__WATCH_NONCE__">([\s\S]*?)<\/script>/)[1];
class Room {
    constructor(state=null) {this.state=state; this.at=0; this.now=0; this.revision=0; this.peers=new Set(); this.messages=[]; this.input=[];}
    snapshot() {return this.state && {...this.state,time:this.state.time+(this.state.state==='playing'?(this.now-this.at)/1000:0)};}
    emit(peer, data) {this.messages.push([peer,{...data,revision:++this.revision}]);}
    broadcast(data, exclude) {for (const peer of this.peers) if(peer!==exclude)this.emit(peer,data);}
    send(peer, data) {
        this.input.push(data);
        if(data.type==='join') {
            this.peers.add(peer); this.emit(peer,{type:'user_list',users:['Synthetic']});
            if(this.state)this.emit(peer,{type:'sync_response',...this.snapshot()});
            this.broadcast({type:'user_joined',message:'Synthetic joined'},peer);
            // Also exercise compatibility with the old server's peer requests.
            this.broadcast({type:'sync_request'},peer);
        } else if(data.type==='sync_request') {
            this.emit(peer,{type:'user_list',users:['Synthetic']});
            if(this.state)this.emit(peer,{type:'sync_response',...this.snapshot()});
        } else if(['sync_response','state_change','seek'].includes(data.type)) {
            this.state={...this.snapshot(),...data}; delete this.state.type; this.at=this.now;
            this.broadcast(data,peer);
        }
    }
    drain() {
        let count=0;
        while(this.messages.length) {
            assert.ok(++count<200,'unbounded peer feedback');
            const [peer,data]=this.messages.shift();
            if(peer.readyState===1)peer.onmessage({data:JSON.stringify(data)});
        }
    }
}
function client(room, blocked=false) {
    const elements=new Map(), listeners=new Map(), timers=new Map(), sockets=[], intervals=[];
    let serial=0, options;
    function element() {return {children:[],style:{},hidden:true,value:'',innerText:'',textContent:'',className:'',
        set innerHTML(v){this.children=[];},classList:{add(){},remove(){}},addEventListener(){},
        appendChild(v){this.children.push(v);},append(...v){this.children.push(...v);},replaceChildren(...v){this.children=v;},remove(){}};}
    const document={visibilityState:'visible',addEventListener:(n,f)=>listeners.set(n,f),
        getElementById(n){if(!elements.has(n))elements.set(n,element());return elements.get(n);},
        createElement:element,querySelectorAll:()=>[]};
    const frame={id:null,time:0,state:-1,at:room.now,pending:null,blocked,gesture:false,commands:[],
        getCurrentTime(){return this.time+(this.state===1?(room.now-this.at)/1000:0);},getPlayerState(){return this.state;},
        // The real iframe API clears metadata synchronously while loading and
        // fills it again in a later message. It is not always an object.
        getVideoData(){return this.pending ? undefined : {video_id:this.id};},
        loadVideoById(value,start=0){this.load(value,start,'playing');},
        cueVideoById(value,start=0){this.load(value,start,'paused');},
        load(value,start,intent){this.commands.push(intent);this.pending=typeof value==='string'?{videoId:value,startSeconds:start,intent}:{...value,intent};this.state=-1;},
        // Loading is asynchronous. Premature seek/play/pause does not change the
        // future media's start offset; this catches the old load-then-seek race.
        seekTo(time){if(!this.pending){this.time=time;this.at=room.now;}},
        playVideo(){if(this.pending)return;if(this.blocked&&!this.gesture){options.events.onAutoplayBlocked?.({target:this});return;}this.native(1,this.getCurrentTime());},
        pauseVideo(){if(!this.pending)this.native(2,this.getCurrentTime());},
        complete(){const p=this.pending;if(!p)return;this.pending=null;this.id=p.videoId;this.time=p.startSeconds??0;this.at=room.now;
            this.state=p.intent==='playing'&&!this.blocked?1:5;
            if(p.intent==='playing'&&this.blocked)options.events.onAutoplayBlocked?.({target:this});
            options.events.onStateChange({target:this,data:this.state});},
        native(state,time){this.state=state;this.time=time;this.at=room.now;options.events.onStateChange({target:this,data:state});}
    };
    class Socket {
        static CONNECTING=0; static OPEN=1; static CLOSING=2; static CLOSED=3;
        constructor(){this.readyState=0;this.sent=[];sockets.push(this);}
        open(){this.readyState=1;this.onopen();}
        send(raw){const data=JSON.parse(raw);this.sent.push(data);room.send(this,data);}
        close(code=1000){this.readyState=3;room.peers.delete(this);this.onclose({code});}
    }
    const window={location:{search:'?session=synthetic-capability',protocol:'https:',host:'watch.example.test',origin:'https://watch.example.test'},
        stop(){},addEventListener:(n,f)=>listeners.set(n,f)};
    const ctx=vm.createContext({window,document,URLSearchParams,WebSocket:Socket,console,
        Date:class extends Date {static now(){return room.now;}},
        YT:{PlayerState:{UNSTARTED:-1,PLAYING:1,PAUSED:2,ENDED:0,BUFFERING:3,CUED:5},Player:function(_,value){options=value;return frame;}},
        setTimeout:(f,delay)=>{timers.set(++serial,{f,delay,at:room.now+delay});return serial;},clearTimeout:n=>timers.delete(n),
        setInterval:f=>{intervals.push(f);return intervals.length;},alert(){},AbortSignal:{timeout:()=>undefined},fetch:async()=>({ok:true,status:200,json:async()=>({playlist:[]})})});
    vm.runInContext(source,ctx);
    return {ctx,frame,elements,listeners,timers,sockets,
        ready(){ctx.onYouTubeIframeAPIReady();options.events.onReady({target:frame});},
        open(){sockets.at(-1).open();room.drain();},
        tick(ms){room.now+=ms;for(const [id,t] of [...timers])if(t.at<=room.now){timers.delete(id);t.f();}for(const f of intervals)f();room.drain();},
        receive(message){room.emit(sockets.at(-1),message);room.drain();},
        recover(){frame.gesture=true;frame.blocked=false;elements.get('resume-playback-btn').onclick();frame.complete();room.drain();}
    };
}
const current=(state='playing',time=42)=>({videoId:'aaaaaaaaaaa',state,time});
const scenario=process.argv[3];
if(['playing-refresh','paused-refresh','hydrate-before-ready','ready-before-hydrate','same-invite-return'].includes(scenario)) {
    const paused=scenario==='paused-refresh', room=new Room(current(paused?'paused':'playing',42)), c=client(room);
    if(scenario==='ready-before-hydrate')c.ready();
    c.open();
    if(scenario!=='ready-before-hydrate'){c.tick(1200);c.ready();}
    c.frame.complete();room.drain();
    assert.equal(c.frame.id,'aaaaaaaaaaa');
    assert.ok(Math.abs(c.frame.getCurrentTime()-(paused?42:room.snapshot().time))<0.1,'hydration must use authoritative position, not zero');
    assert.ok(paused?[2,5].includes(c.frame.state):c.frame.state===1);
    if(scenario==='same-invite-return') {
        c.sockets.at(-1).close(1000);room.now+=1000;const d=client(room);d.ready();d.open();d.frame.complete();room.drain();
        assert.ok(d.frame.getCurrentTime()>=43,'valid invitation return must not restart at zero');
    }
} else if(scenario==='paused-cue-reports-zero') {
    const room=new Room(current('paused',42)),c=client(room);c.ready();c.open();
    let seeks=0;
    c.frame.seekTo=()=>{seeks++;c.frame.native(1,0);};
    c.frame.getCurrentTime=()=>c.frame.state===5?0:c.frame.time;
    c.frame.complete();room.drain();
    assert.equal(c.frame.state,5);assert.equal(seeks,0,'seekTo on a cued video must not start paused media');
    assert.equal(c.elements.get('playback-status').innerText,'일시정지 동기화됨');
    c.receive({type:'seek',time:81});assert.equal(c.frame.pending.startSeconds,81);
    c.frame.complete();room.drain();assert.equal(c.frame.state,5);assert.equal(seeks,0);
    c.receive({type:'state_change',state:'playing',time:81});room.drain();
    assert.equal(c.frame.state,1);
} else if(scenario==='latest-before-ready') {
    const room=new Room(current()), c=client(room);c.open();
    c.receive({type:'sync_response',...current('paused',81)});c.ready();c.frame.complete();room.drain();
    assert.equal(c.frame.getCurrentTime(),81);assert.ok([2,5].includes(c.frame.state));
} else if(scenario==='late-iframe-ack') {
    const room=new Room(current()),c=client(room);c.ready();c.open();c.tick(1200);c.frame.complete();room.drain();
    assert.equal(room.input.filter(m=>['sync_response','state_change'].includes(m.type)).length,0,'late remote acknowledgement is not a local user command');
} else if(scenario==='video-change-before-ack') {
    const room=new Room(current()),c=client(room);c.ready();c.open();
    c.receive({type:'sync_response',videoId:'bbbbbbbbbbb',state:'paused',time:81});
    // A delayed event from the retired video must not acknowledge the new one.
    c.frame.id='aaaaaaaaaaa';c.frame.native(1,0);room.drain();
    assert.equal(room.input.filter(m=>m.type==='state_change').length,0);
    c.frame.complete();room.drain();
    assert.equal(c.frame.id,'bbbbbbbbbbb');assert.equal(c.frame.time,81);assert.equal(c.frame.state,5);
} else if(scenario==='seek-ack-is-asynchronous') {
    const room=new Room(current()),c=client(room);c.ready();c.open();c.frame.complete();
    let seek;
    c.frame.seekTo=time=>{seek=time;};
    c.receive({type:'seek',time:91});
    assert.equal(c.elements.get('playback-status').innerText,'재생 상태 확인 중');
    assert.equal(seek,91);
    c.frame.time=seek;c.frame.at=room.now;c.tick(800);
    assert.equal(c.elements.get('playback-status').innerText,'재생 동기화됨');
    assert.equal(room.input.filter(m=>m.type==='seek').length,0,'seek ACK must not echo');
} else if(scenario==='peer-cannot-overwrite-authority') {
    const room=new Room(current()),a=client(room);a.ready();a.open();a.frame.complete();room.drain();
    a.frame.state=2;a.frame.time=0; // suspended/stale iframe, without a user pause event
    const b=client(room);b.open();room.drain();
    assert.equal(room.state.state,'playing');assert.equal(room.state.time,42,'join must not solicit stale peer snapshots');
} else if(scenario==='multi-client-timing') {
    const room=new Room(current()),a=client(room),b=client(room);a.ready();a.open();a.frame.complete();b.open();
    a.frame.native(2,73);room.drain();b.ready();b.frame.complete();room.drain();
    assert.ok([2,5].includes(b.frame.state));assert.equal(b.frame.getCurrentTime(),73);
    a.frame.native(1,73);room.drain();b.frame.complete();room.drain();assert.equal(b.frame.state,1);
    a.ctx.sendWsMessage({type:'seek',time:91});room.drain();assert.equal(b.frame.getCurrentTime(),91);
    assert.equal(room.peers.size,2);
} else if(scenario==='autoplay-recovery') {
    const room=new Room(current()),a=client(room),b=client(room,true);a.ready();a.open();a.frame.complete();b.ready();b.open();b.frame.complete();room.drain();
    assert.equal(b.elements.get('resume-playback-btn')?.hidden,false,'blocked playback requires an explicit recovery affordance');
    assert.equal(room.state.state,'playing','blocked client must not pause everyone');
    b.tick(2000);b.recover();assert.equal(b.frame.state,1);assert.ok(b.frame.getCurrentTime()>=44);
    assert.equal(b.elements.get('resume-playback-btn').hidden,true);
} else if(scenario==='unacknowledged-playback') {
    const room=new Room(current()),c=client(room);c.ready();c.open();c.tick(6000);
    assert.equal(c.elements.get('resume-playback-btn')?.hidden,false,'silent/black iframe must not claim success forever');
    assert.equal(c.frame.commands.length,1,'timeout must not automatically retry external media');
} else if(['reconnect-hydration','reconnect-paused'].includes(scenario)) {
    const room=new Room(current()),a=client(room),b=client(room);a.ready();a.open();a.frame.complete();b.ready();b.open();b.frame.complete();
    const old=b.sockets.at(-1);old.close(1006);
    if(scenario==='reconnect-paused'){a.frame.native(2,73);room.drain();}
    b.tick(500);b.open();b.frame.complete();room.drain();
    assert.equal(room.peers.size,2);assert.equal(b.sockets.length,2);assert.equal(b.frame.id,'aaaaaaaaaaa');
    assert.ok(Math.abs(b.frame.getCurrentTime()-room.snapshot().time)<1.5);
    old.onmessage({data:JSON.stringify({type:'sync_response',...current('paused',0),revision:999})});
    assert.equal(b.frame.state,scenario==='reconnect-paused'?2:1,'retired socket cannot overwrite rehydrated player');
} else if(scenario.startsWith('terminal-')) {
    const room=new Room(current()),c=client(room);c.open();c.sockets[0].close(Number(scenario.slice(9)));
    c.listeners.get('online')();c.listeners.get('pageshow')();c.tick(20000);assert.equal(c.sockets.length,1);
} else if(scenario==='stale-revision') {
    const room=new Room(current()),c=client(room);c.ready();c.open();c.frame.complete();
    c.sockets[0].onmessage({data:JSON.stringify({type:'sync_response',...current('paused',0),revision:1})});
    assert.equal(c.frame.state,1);assert.equal(c.frame.time,42);
} else if(scenario==='empty-session') {
    const room=new Room(),c=client(room);c.open();c.ready();c.tick(6000);
    assert.equal(c.frame.commands.length,0);assert.equal(room.state,null);
    assert.equal(room.input.filter(m=>m.type==='sync_response').length,0);
} else {throw Error('unknown scenario');}
console.log('PASS '+scenario);
