// Extend the production-script VM with terminal lifecycle races; no network.
const fs = require('node:fs');
const prefix = fs.readFileSync(require('node:path').join(__dirname, 'playback_browser_harness.cjs'), 'utf8')
    .split('const scenario=process.argv[3];')[0];

async function run() {
    const scenario=process.argv[3], room=new Room(current()), controlRoom=new Room(current());
    const c=client(room), control=client(controlRoom);
    control.ready();control.open();control.frame.complete();
    if(scenario!=='before-api') c.initialize();
    if(!['before-api','before-ready'].includes(scenario)) c.ready();
    c.open();
    if(!['before-api','before-ready','pending-load'].includes(scenario)) c.frame.complete();
    if(scenario==='retired-terminal') {
        const retired=c.sockets[0];retired.close(4008);
        c.tick(500);c.open();c.frame.complete();
        retired.onclose({code:4001});
        assert.equal(vm.runInContext('terminal',c.ctx),false);
        assert.equal(c.frame.destroyed,false);assert.equal(c.frame.state,1);
        assert.equal(c.sockets.length,2);assert.equal(c.activeListeners.size,4);
        c.tick(2000);assert.ok(c.frame.getCurrentTime()>=44);
        console.log('PASS '+scenario);return;
    }
    const owned=c.constructions, oldSocket=c.sockets[0];
    const before=room.input.length;
    if(scenario==='session-event') {
        // Browser close handshake completion may be delayed indefinitely.
        oldSocket.close=()=>{oldSocket.readyState=2;};
        c.receive({type:'session_closed'});
    } else if(scenario.startsWith('http-')) {
        // Allow initial successful fetch microtasks to drain before revocation.
        await new Promise(resolve=>setImmediate(resolve));
        c.ctx.fetch=async()=>({status:Number(scenario.slice(5)),ok:false});
        await c.ctx.fetchPlaylist();
    } else if(scenario==='destroy-throws') {
        let removed=false;
        const destroy=c.frame.destroy.bind(c.frame);
        c.frame.destroy=()=>{throw Error('synthetic provider failure');};
        c.ctx.document.getElementById('yt-player').remove=()=>{removed=true;destroy();};
        oldSocket.close(4001);
        assert.ok(removed,'provider failure must still unload its DOM iframe');
    } else if(scenario==='destroy-reentrant') {
        const destroy=c.frame.destroy.bind(c.frame);
        c.frame.destroy=()=>{c.lateCallbacks();c.ctx.loadVideoById('bbbbbbbbbbb');destroy();};
        oldSocket.close(4001);
    } else if(scenario==='pending-add') {
        await new Promise(resolve=>setImmediate(resolve));
        vm.runInContext('currentVideoId=null',c.ctx);
        c.elements.get('youtube-url-input').value='https://youtu.be/bbbbbbbbbbb';
        await c.ctx.addVideoFromInput();
        assert.equal(vm.runInContext('pendingLoads.size',c.ctx),1);
        oldSocket.close(4001);
        assert.equal(vm.runInContext('pendingLoads.size',c.ctx),0);
    } else if(scenario==='late-add-response') {
        await new Promise(resolve=>setImmediate(resolve));
        let resolve;
        c.ctx.fetch=()=>new Promise(r=>{resolve=r;});
        c.elements.get('youtube-url-input').value='https://youtu.be/bbbbbbbbbbb';
        const added=c.ctx.addVideoFromInput();
        oldSocket.close(4001);resolve({ok:true});await added;
        assert.equal(vm.runInContext('pendingLoads.size',c.ctx),0);
    } else {
        oldSocket.close(scenario==='protocol'?4002:scenario==='revoked'?4003:4001);
    }
    assert.equal(vm.runInContext('terminal',c.ctx),true);
    assert.equal(c.activeListeners.size,0,'terminal must unregister page/reconnect listeners');
    assert.equal(c.intervals.size,0,'terminal must release playback polling');
    assert.equal(vm.runInContext('pendingPlayback',c.ctx),null);
    assert.equal(c.elements.get('connection-badge').className,'badge badge-ws disconnected');
    if(owned) assert.ok(c.frame.destroyed,'owned player must be destroyed before any late callback');
    const commandCount=c.frame.commands.length;
    for(let i=0;i<2;i++) {
        c.ready();c.lateCallbacks();c.frame.complete();
        for(const callback of c.listeners.values()) callback(); // already queued event handles
        c.ctx.loadVideoById('bbbbbbbbbbb');c.ctx.receivePlayback(current());
        c.elements.get('resume-playback-btn').onclick();
        oldSocket.onmessage({data:JSON.stringify({type:'sync_response',...current(),revision:999+i})});
        oldSocket.onclose({code:4001});
    }
    const stoppedTime=c.frame.getCurrentTime();
    c.tick(20000);control.tick(2000);
    assert.equal(c.constructions,owned,'late API callback cannot create another iframe');
    assert.equal(c.frame.commands.length,commandCount,'late callbacks cannot issue media commands');
    assert.notEqual(c.frame.state,1);
    assert.equal(c.frame.getCurrentTime(),stoppedTime);
    assert.equal(c.sockets.length,1);
    assert.equal(c.timers.size,0,'no terminal work may remain after the finite toast expires');
    assert.equal(room.input.length,before,'terminal lifecycle cannot publish playback');
    assert.equal(control.frame.state,1);assert.equal(control.frame.getCurrentTime(),44);
    console.log('PASS '+scenario);
}
new Function('require', 'process', prefix + `(${run.toString()})().catch(e=>{console.error(e);process.exitCode=1;});`)(require,process);
