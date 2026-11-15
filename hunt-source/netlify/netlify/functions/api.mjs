import {createHmac,timingSafeEqual,randomBytes} from 'node:crypto';
import {handle} from '../../runtime/worker.mjs';
import {dispatchDiscovery} from '../../runtime/discovery-tasks.mjs';
import {environment} from '../../runtime/environment.mjs';
const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
const sign=(value,key)=>createHmac('sha256',key).update(value).digest('hex');
function ownerSession(req,key){
  if(!key)return false;
  const value=(req.headers.get('cookie')||'').split(';').map(x=>x.trim()).find(x=>x.startsWith('__Host-hunt_owner='))?.split('=').slice(1).join('=');
  if(!value)return false;
  const [expiry,nonce,signature]=value.split('.');
  return Number(expiry)>Date.now()&&Number(expiry)<Date.now()+25*60*60*1000&&/^[a-f0-9]{32}$/.test(nonce||'')&&same(signature,sign(expiry+'.'+nonce,key));
}
export default async function(request){
  const url=new URL(request.url),ownerKey=process.env.HUNT_OWNER_KEY||'';
  if(url.pathname==='/api/login'&&request.method==='POST'){
    if(!ownerKey||request.headers.get('origin')!==url.origin)return Response.json({error:'Owner access is not configured.'},{status:403});
    const body=await request.json();
    if(!same(body.token,ownerKey))return Response.json({error:'Owner access denied.'},{status:403});
    const value=String(Date.now()+24*60*60*1000)+'.'+randomBytes(16).toString('hex');
    return Response.json({ok:true},{headers:{'Set-Cookie':'__Host-hunt_owner='+value+'.'+sign(value,ownerKey)+'; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=86400','Cache-Control':'no-store'}});
  }
  const headers=new Headers(request.headers);
  // Never trust browser-supplied platform identity headers on a new host.
  headers.delete('oai-authenticated-user-id');
  if(ownerSession(request,ownerKey)||ownerKey&&same(headers.get('X-HUNT-Owner-Key'),ownerKey))headers.set('oai-authenticated-user-id','netlify-owner');
  try{const env=await environment();env.dispatchNativeCV=async id=>{const response=await fetch(new URL('/.netlify/functions/native-cv-background',request.url),{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/json','X-HUNT-Background-Key':process.env.HUNT_SERVICE_KEY||''},body:JSON.stringify({id})});if(response.status!==202)throw Error('Native CV background dispatch not confirmed');};env.dispatchDiscovery=id=>dispatchDiscovery(env,id,new URL(request.url).origin,process.env.HUNT_SERVICE_KEY||'');return await handle(new Request(request,{headers}),env);}
  catch(error){return Response.json({error:'HUNT could not load its Netlify storage. No operation is confirmed.'},{status:503,headers:{'Cache-Control':'no-store'}});}
}
export const config={path:'/api/*'};
