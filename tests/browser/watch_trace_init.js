(() => {
 window.__watchTrace = [];
 window.__mark = (event, data={}) => {if(window.__watchTrace.length<300)window.__watchTrace.push({ms:Math.round(performance.now()),event,...data});};
 Object.defineProperty(window,'onYouTubeIframeAPIReady',{configurable:true,
  get(){window.__mark('api_callback_lookup_before_registration');return undefined;},
  set(value){Object.defineProperty(window,'onYouTubeIframeAPIReady',{value,writable:true,configurable:true});}
 });
 const Socket=window.WebSocket;
 window.WebSocket=class extends Socket {
  constructor(...args){super(...args);window.__mark('ws_created');
   this.addEventListener('open',()=>window.__mark('ws_open'));
   this.addEventListener('close',e=>window.__mark('ws_closed',{code:e.code}));
   this.addEventListener('message',e=>{try{const m=JSON.parse(e.data);window.__mark('ws_'+m.type,
    {revision:m.revision,hasVideo:!!m.videoId,position:typeof m.time==='number'?m.time:undefined,
     state:['playing','paused'].includes(m.state)?m.state:undefined});}catch{}});
  }
  send(raw){try{const m=JSON.parse(raw);window.__mark('send_'+m.type);}catch{}return super.send(raw);}
 };
 window.addEventListener('error',e=>window.__mark('js_error',{line:e.lineno,category:/video_id/.test(e.message)?'video_data_unavailable':'other'}));
 document.addEventListener('securitypolicyviolation',e=>window.__mark('csp_violation',{directive:e.effectiveDirective}));
 new MutationObserver(()=>{if(document.querySelector('iframe#yt-player'))window.__mark('iframe_present');}).observe(document,{childList:true,subtree:true});
})();
