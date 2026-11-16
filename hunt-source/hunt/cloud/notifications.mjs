// Fixed-recipient operational notices only; never employer emails or CV contents.
export const RECIPIENT='majekadegbeaminat85@gmail.com';
const CONNECTION='hunt/private/notification-google.json',PREFIX='hunt/private/run-notifications/';
const SEND_SCOPE='https://www.googleapis.com/auth/gmail.send';
const get=async(b,k)=>{const x=await b.get(k);return x?x.json():null};
const put=(b,k,v,o={})=>b.put(k,JSON.stringify(v),o);
const allowed=new Set([SEND_SCOPE,'openid','email','https://www.googleapis.com/auth/userinfo.email']);
async function token(connection,fetcher){
 const r=await fetcher('https://oauth2.googleapis.com/token',{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:connection.client_id,client_secret:connection.client_secret,refresh_token:connection.refresh_token,grant_type:'refresh_token'})});
 if(!r.ok)throw Error('Google notification authorization needs reconnection');const data=await r.json();if(!data.access_token)throw Error('Google notification authorization returned no token');return data.access_token;
}
export async function notificationStatus(bucket,runId){const last=runId&&/^[A-Za-z0-9_:.\-]{1,150}$/.test(runId)?await get(bucket,PREFIX+runId+'.json'):null;const c=await get(bucket,CONNECTION);return {enabled:true,recipient:RECIPIENT,last_notification:last?{status:last.status,reason:last.reason||null}:null,status:c?'connected':'awaiting_send_authorization',scope:'Run summaries only; no application sending',schedule:'07:00, 12:00, 18:00 Africa/Lagos and manual runs'};}
export async function connectNotifications(bucket,connection,fetcher=fetch){
 if(connection.account!==RECIPIENT||!Array.isArray(connection.scopes)||!connection.scopes.includes(SEND_SCOPE)||connection.scopes.some(s=>!allowed.has(s)))throw Error('A dedicated notification send-only Google grant for the owner account is required');
 for(const k of ['client_id','client_secret','refresh_token'])if(typeof connection[k]!=='string'||!connection[k]||connection[k].length>4096)throw Error('Incomplete notification authorization');
 const access=await token(connection,fetcher),r=await fetcher('https://openidconnect.googleapis.com/v1/userinfo',{redirect:'error',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer '+access}});
 if(!r.ok)throw Error('Notification account could not be verified');const profile=await r.json();if(profile.email!==RECIPIENT||profile.email_verified!==true)throw Error('Notification account must match the owner');
 await put(bucket,CONNECTION,{...Object.fromEntries(['client_id','client_secret','refresh_token','account','scopes'].map(k=>[k,connection[k]])),connected_at:new Date().toISOString()});return notificationStatus(bucket);
}
export function notice(run){
 if(run.kind==='application_batch'){const rows=run.attempts||[],counts=Object.fromEntries([...new Set(rows.map(a=>a.status))].map(status=>[status,rows.filter(a=>a.status===status).length]));return {subject:'HUNT application outcomes · '+rows.length+' attempts',text:'HUNT finished processing its current application pool.\n\n'+Object.entries(counts).map(([s,n])=>s.replaceAll('_',' ')+': '+n).join('\n')+'\n\n'+rows.map(a=>a.company+' · '+a.role+' — '+a.status+' — '+a.message).join('\n')+'\n\nSubmitted means employer-page confirmation. Email sent means Gmail accepted delivery; employer acknowledgement is separate. Unconfirmed attempts are held to prevent duplicates.\nhttps://hunt-aminat.netlify.app/'};}
 const status=['success','partial','failed','blocked'].includes(run.status)?run.status:'failed',f=run.funnel||{},when=new Date(run.finished||Date.now()).toLocaleString('en-NG',{timeZone:'Africa/Lagos'});
 return {subject:`HUNT run ${status} · ${when} WAT`,text:`HUNT finished a discovery run.\n\nStatus: ${status}\nFinished: ${when} WAT\nRun: ${String(run.id).replace(/[\r\n]/g,'').slice(0,120)}\nSources completed: ${Number(run.sources_verified||0)}/${Number(run.sources_checked||0)}\nPosting records: ${Number(f.relevant_postings_observed||0)}\nConfirmed matches: ${Number(f.record_breakdown?.confirmed||0)}\n\nYour 48-hour window and USD 2,500/month minimum are unchanged.\nOpen your owner dashboard: https://hunt-aminat.netlify.app/\nUse your private login shortcut if asked to sign in.\n\nNo application or employer email was sent by this discovery run.`};
}
export async function notifyRun(bucket,run,fetcher=fetch){
 const id=String(run.id);if(!/^[A-Za-z0-9_:.\-]{1,150}$/.test(id))throw Error('Invalid notification run identity');
 const key=PREFIX+id+'.json',existing=await get(bucket,key);if(existing)return {...existing,replayed:true};
 const at=new Date().toISOString(),connection=await get(bucket,CONNECTION),base={run_id:id,recipient:RECIPIENT,at};
 if(!connection){const row={...base,status:'blocked',reason:'Send authorization not connected'};await put(bucket,key,row,{onlyIf:{etagDoesNotMatch:'*'}});return row;}
 const reservation=await put(bucket,key,{...base,status:'sending'},{onlyIf:{etagDoesNotMatch:'*'}});if(!reservation)return {...await get(bucket,key),replayed:true};
 let sending=false;
 try{const access=await token(connection,fetcher),n=notice(run),mime=`From: HUNT <${RECIPIENT}>\r\nTo: ${RECIPIENT}\r\nSubject: ${n.subject}\r\nMIME-Version: 1.0\r\nContent-Type: text/plain; charset=UTF-8\r\n\r\n${n.text}`,raw=btoa(String.fromCharCode(...new TextEncoder().encode(mime))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
  sending=true;const response=await fetcher('https://gmail.googleapis.com/gmail/v1/users/me/messages/send',{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer '+access,'Content-Type':'application/json'},body:JSON.stringify({raw})});
  if(!response.ok){const row={...base,status:'failed',reason:'Google rejected notification ('+response.status+')'};await put(bucket,key,row);return row;}
  const receipt=await response.json();if(!receipt.id)throw Error('No provider receipt');const row={...base,status:'sent',provider_message_id:receipt.id};await put(bucket,key,row);return row;
 }catch{const row={...base,status:sending?'uncertain':'failed',reason:sending?'Send outcome unconfirmed; no automatic resend':'Notification authorization failed'};await put(bucket,key,row);return row;}
}
