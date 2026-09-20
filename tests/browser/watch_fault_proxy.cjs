// Synthetic-browser-only loopback proxy. Faults the real TCP transport, not JS events.
const http=require('node:http'),net=require('node:net');
module.exports=async function faultProxy(){
 const connections=new Set(),ws=new Set();let blocked=false;
 const server=http.createServer((req,res)=>{
  let target;try{target=new URL(req.url);}catch{res.writeHead(400);return res.end();}
  if(target.hostname!=='127.0.0.1'||target.port!=='8765'){res.writeHead(403);return res.end();}
  const upstream=http.request({host:'127.0.0.1',port:8765,method:req.method,path:target.pathname+target.search,headers:req.headers},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res);});
  upstream.on('error',()=>{res.writeHead(502);res.end();});req.pipe(upstream);
 });
 server.on('connection',socket=>{connections.add(socket);socket.on('close',()=>connections.delete(socket));socket.on('error',()=>{});});
 server.on('upgrade',(req,socket,head)=>{
  if(blocked){socket.destroy();return;}
  let target;try{target=new URL(req.url,'http://127.0.0.1:8765');}catch{socket.destroy();return;}
  if(target.hostname!=='127.0.0.1'||target.port!=='8765'){socket.destroy();return;}
  const upstream=net.connect(8765,'127.0.0.1');const pair={socket,upstream};ws.add(pair);
  const done=()=>{ws.delete(pair);socket.destroy();upstream.destroy();};
  socket.on('error',done);upstream.on('error',done);socket.on('close',done);upstream.on('close',done);
  upstream.on('connect',()=>{upstream.write(`${req.method} ${target.pathname+target.search} HTTP/${req.httpVersion}\r\n`+Object.entries(req.headers).map(([k,v])=>`${k}: ${v}`).join('\r\n')+'\r\n\r\n');if(head.length)upstream.write(head);socket.pipe(upstream);upstream.pipe(socket);});
 });
 server.on('connect',(req,socket,head)=>{
  const [host,port]=req.url.split(':');
  // Chrome also tunnels ws:// through CONNECT when using an HTTP proxy.
  if(host==='127.0.0.1'&&port==='8765'){
   if(blocked){socket.destroy();return;}
   const upstream=net.connect(8765,host);const pair={socket,upstream};ws.add(pair);
   const done=()=>{ws.delete(pair);socket.destroy();upstream.destroy();};
   socket.on('error',done);upstream.on('error',done);socket.on('close',done);upstream.on('close',done);
   upstream.on('connect',()=>{socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');if(head.length)upstream.write(head);socket.pipe(upstream);upstream.pipe(socket);});
   return;
  }
  if(port!=='443'||!['youtube.com','ytimg.com','googlevideo.com','google.com','gstatic.com','doubleclick.net','ggpht.com','googleusercontent.com'].some(domain=>host===domain||host.endsWith('.'+domain))){socket.destroy();return;}
  const upstream=net.connect(443,host);const done=()=>{socket.destroy();upstream.destroy();};
  socket.on('error',done);upstream.on('error',done);socket.on('close',done);upstream.on('close',done);
  upstream.on('connect',()=>{socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');if(head.length)upstream.write(head);socket.pipe(upstream);upstream.pipe(socket);});
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 return {server:'http://127.0.0.1:'+server.address().port,
  cut(){blocked=true;const count=ws.size;for(const p of ws){p.socket.destroy();p.upstream.destroy();}return count;},
  online(){blocked=false;},
  close(){for(const s of connections)s.destroy();return new Promise(resolve=>server.close(resolve));}};
};
