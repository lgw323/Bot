// Opt-in external browser exercise. Never part of the offline pytest suite.
// Real Chrome, real YouTube iframe, real HTTP/WebSocket/Watch actor, synthetic DB only.
const {chromium}=require('playwright');
const fs=require('node:fs'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const root='http://127.0.0.1:8765';
const video='M7lc1UVf-VE'; // Public official IFrame API example; not user media.
const out=process.env.WATCH_BROWSER_RESULT || 'scratch/watch-browser/result.json';
const hash=s=>crypto.createHash('sha256').update(s).digest('hex');
const evidence={browser:null,production:false,assets:[],stages:[],errors:[]};
const state=()=>({ready:playerReady,iframe:!!document.querySelector('iframe#yt-player'),
 ws:ws?.readyState,terminal,hydrating:awaitingHydration,syncing:isSyncing,blocked:playbackBlocked,
 videoConfirmed:!!currentVideoId&&player?.getVideoData?.()?.video_id===currentVideoId,
 state:player?.getPlayerState?.(),position:player?.getCurrentTime?.(),
 expectedState:pendingPlayback?.state,expectedPosition:pendingPlayback?.time,
 recovery:!document.getElementById('resume-playback-btn').hidden,
 serviceWorker:!!navigator.serviceWorker?.controller});
function save(){fs.mkdirSync(require('node:path').dirname(out),{recursive:true});fs.writeFileSync(out,JSON.stringify(evidence,null,2));}
// Playwright evaluation may set userGesture=true. Read-only probes must not
// accidentally grant activation and conceal the real autoplay-blocked path.
const sessions=new WeakMap();
async function read(page,fn){
 if(!sessions.has(page))sessions.set(page,await page.context().newCDPSession(page));
 const value=await sessions.get(page).send('Runtime.evaluate',{expression:'('+fn.toString()+')()',returnByValue:true,userGesture:false});
 if(value.exceptionDetails)throw new Error('safe browser probe unavailable');
 return value.result.value;
}
async function wait(page,predicate,timeout=15000){
 const until=Date.now()+timeout;
 while(Date.now()<until){if(await read(page,predicate))return;await new Promise(resolve=>setTimeout(resolve,100));}
 const error=new Error('browser state deadline');error.name='TimeoutError';throw error;
}
(async()=>{
 const proxy=process.env.WATCH_TCP_FAULT==='1'?await require('./watch_fault_proxy.cjs')():null;
 const browser=await chromium.launch({executablePath:process.env.WATCH_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,
  args:process.env.WATCH_STRICT_AUTOPLAY==='1'?['--autoplay-policy=document-user-activation-required']:[]});
 evidence.browser=browser.version();
 const a=await browser.newContext(),b=await browser.newContext(proxy?{proxy:{server:proxy.server,bypass:'<-loopback>'}}:{});
 const A=await a.newPage(),B=await b.newPage();
 async function wire(page){
  await page.addInitScript({path:require('node:path').join(__dirname,'watch_trace_init.js')});
  page.on('pageerror',e=>{evidence.errors.push({type:e.name,category:/video_id/.test(e.message)?'video_data_unavailable':'other'});});
  page.on('response',async r=>{if(new URL(r.url()).pathname==='/watch'){
   const body=await r.text();evidence.assets.push({status:r.status(),normalizedHTML:hash(body.replace(/nonce="[^"]+"/g,'nonce="__WATCH_NONCE__"')),
    inlineJS:hash(body.match(/<script nonce="[^"]+">([\s\S]*?)<\/script>/)?.[1]||''),
    revision:r.headers()['x-watch-client-revision']||null,cacheControl:r.headers()['cache-control'],etag:r.headers().etag||null});
  }});
 }
 async function record(name,pages=[A],extra={}){
  const server=await(await a.request.get(root+'/fixture/state')).json();
  evidence.stages.push({name,pages:await Promise.all(pages.map(p=>read(p,state))),server,
   traces:await Promise.all(pages.map(p=>read(p,()=>window.__watchTrace))),...extra});save();console.log(name);
 }
 async function aligned(page){await wait(page,()=>playerReady&&!isSyncing&&player.getPlayerState()===1&&player.getVideoData()?.video_id===currentVideoId);}
 async function recover(page){
  await wait(page,()=>playerReady&&((!isSyncing&&player.getPlayerState()===1)||playbackBlocked));
  if(await read(page,()=>playbackBlocked)){await page.locator('#resume-playback-btn').click();await aligned(page);return true;}
  return false;
 }
 try{
  await wire(A);await wire(B);
  const invite=await(await a.request.post(root+'/fixture/new')).json();
  const target=root+'/watch?session='+invite.capability;
  await A.goto(target,{waitUntil:'domcontentloaded'});await wait(A,()=>playerReady&&ws?.readyState===1);
  if(process.env.WATCH_REFRESH_ONLY==='1'){
   // Establish an already-playing room with the real iframe and wire protocol.
   // This isolates reload startup from separate initial-selection defects.
   await A.evaluate(id=>{player.loadVideoById({videoId:id,startSeconds:40});
    sendWsMessage({type:'sync_response',videoId:id,state:'playing',time:40});},video);
   await wait(A,()=>player.getPlayerState()===1);await record('existing_playing_room');
   await A.reload({waitUntil:'domcontentloaded'});await recover(A);await record('warm_refresh');
   assert.ok((await read(A,state)).position>=39);assert.equal(evidence.errors.length,0);
   evidence.status='PASS';save();return;
  }
  await a.request.post(root+'/api/playlist/'+invite.capability+'/add',{headers:{origin:root,'x-watch-csrf':'1'},data:{video_url:'https://youtu.be/'+video,added_by:'Synthetic'}});
  await A.locator('.item-info').first().click();await aligned(A);
  await A.evaluate(()=>player.seekTo(40,true));await A.waitForTimeout(1800);
  await record('initial_playing');
  await A.reload({waitUntil:'domcontentloaded'});await recover(A);await record('playing_refresh');
  assert.ok((await read(A,state)).position>39);
  await A.evaluate(()=>player.pauseVideo());await wait(A,()=>player.getPlayerState()===2);await A.waitForTimeout(250);
  const paused=await read(A,()=>player.getCurrentTime());
  await A.reload({waitUntil:'domcontentloaded'});await wait(A,()=>playerReady&&!isSyncing&&[2,5].includes(player.getPlayerState()));
  await record('paused_refresh');
  assert.ok(Math.abs((await read(A,state)).expectedPosition-paused)<1.5);
  await A.evaluate(()=>player.playVideo());await aligned(A);assert.ok((await read(A,state)).position>=paused-1.5);
  await record('paused_refresh_resume_position');
  await B.goto(target,{waitUntil:'domcontentloaded'});await record('second_context_loaded',[A,B]);
  await wait(B,()=>playerReady&&((!isSyncing&&player.getPlayerState()===1)||playbackBlocked));
  if(await read(B,()=>playbackBlocked)){
   await record('autoplay_blocked_authority_preserved',[A,B]);
   assert.equal((await(await a.request.get(root+'/fixture/state')).json()).states.find(x=>x.clients===2)?.state,'playing');
  }
  const recovered=await recover(B);
  await record('two_contexts_playing',[A,B],{explicitRecovery:recovered});
  let room=(await(await a.request.get(root+'/fixture/state')).json()).states.find(x=>x.clients===2);
  assert.equal(room?.unique_clients,2);
  await A.evaluate(()=>player.pauseVideo());await wait(B,()=>playerReady&&!isSyncing&&[2,5].includes(player.getPlayerState()));
  await record('peer_pause',[A,B]);
  await A.evaluate(()=>player.playVideo());await aligned(A);await aligned(B);await record('peer_resume',[A,B]);
  await A.evaluate(()=>player.seekTo(75,true));await wait(B,()=>player.getCurrentTime()>73&&player.getCurrentTime()<85&&!isSyncing);
  await record('peer_seek',[A,B]);
  const cutCount=proxy?proxy.cut():null;
  if(!proxy)await b.setOffline(true);await B.waitForTimeout(1800);
  const interrupted=await read(B,()=>ws.readyState!==1);
  await record(proxy?'tcp_disconnected':'devtools_offline',[A,B],{websocketInterrupted:interrupted,cutConnections:cutCount});
  if(proxy)proxy.online();else await b.setOffline(false);
  await wait(B,()=>ws.readyState===1&&!awaitingHydration);await recover(B);await record('online_playing',[A,B]);
  if(interrupted){
   room=(await(await a.request.get(root+'/fixture/state')).json()).states.find(x=>x.clients===2);assert.equal(room?.unique_clients,2);
   if(proxy)proxy.cut();else await b.setOffline(true);
   await A.evaluate(()=>player.pauseVideo());await B.waitForTimeout(1500);
   if(proxy)proxy.online();else await b.setOffline(false);
   await wait(B,()=>ws.readyState===1&&!awaitingHydration&&!isSyncing&&[2,5].includes(player.getPlayerState()));await record('online_paused',[A,B]);
  }
  await a.request.post(root+'/fixture/close');await wait(A,()=>terminal);await wait(B,()=>terminal);
  await a.setOffline(true);await a.setOffline(false);await A.waitForTimeout(3500);
  await record('terminal_no_reconnect',[A,B]);
  assert.equal((await(await a.request.get(root+'/fixture/state')).json()).clients,0);
  assert.equal(evidence.errors.length,0);evidence.status=interrupted?'PASS':'RECONNECT_NOT_REPRODUCED';save();
 }catch(e){try{await record('failure_snapshot',[A,B].filter(p=>p.url().startsWith(root+'/watch?')));}catch{}evidence.status='FAIL';evidence.failure={type:e.name,stage:evidence.stages.at(-1)?.name||'initial',category:/Timeout/.test(e.name)?'state_timeout':'assertion_or_application'};save();process.exitCode=1;}
 finally{await browser.close();if(proxy)await proxy.close();console.log(JSON.stringify({status:evidence.status,stages:evidence.stages.map(x=>x.name),errors:evidence.errors}));}
})().catch(e=>{console.log(JSON.stringify({error_type:e.name}));process.exitCode=1;});
