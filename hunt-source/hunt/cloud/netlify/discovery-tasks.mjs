const PREFIX='hunt/runtime/discovery-tasks/';
const valid=id=>/^[A-Za-z0-9_-]{8,100}$/.test(id||'');
export async function dispatchDiscovery(env,id,origin,secret,fetcher=fetch){
 if(!secret)throw Error('Background discovery service is not configured');
 id=id||crypto.randomUUID();if(!valid(id))throw Error('Invalid run identity');const key=PREFIX+id+'.json',existing=await env.BUCKET.get(key);if(existing)return existing.json();
 const task={id,status:'queued',created_at:new Date().toISOString()};
 const saved=await env.BUCKET.put(key,JSON.stringify(task),{onlyIf:{etagDoesNotMatch:'*'}});if(!saved)return (await env.BUCKET.get(key)).json();
 try{const response=await fetcher(new URL('/.netlify/functions/discovery-background',origin),{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/json','X-HUNT-Background-Key':secret},body:JSON.stringify({id})});if(response.status!==202)throw Error('Background dispatch not accepted');}
 catch{const uncertain={...task,status:'dispatch_uncertain',message:'Run dispatch was not confirmed. Inspect this run before starting another.'};await env.BUCKET.put(key,JSON.stringify(uncertain));return uncertain;}
 return task;
}
export async function executeDiscoveryTask(env,id,discover){
 if(!valid(id))throw Error('Invalid run identity');const key=PREFIX+id+'.json',obj=await env.BUCKET.get(key);if(!obj)return;
 const task=await obj.json();if(!['queued','dispatch_uncertain'].includes(task.status))return task;
 if(!obj.etag)throw Error('Run reservation has no version');
 const running={...task,status:'running',started_at:new Date().toISOString()};
 const claim=await env.BUCKET.put(key,JSON.stringify(running),{onlyIf:{etagMatches:obj.etag}});if(!claim)return;
 let finished;
 try{const result=await discover(env,{idempotency_key:id});finished={...running,status:result.status==='failed'?'failed':'completed',finished_at:new Date().toISOString(),result};}
 catch{finished={...running,status:'failed',finished_at:new Date().toISOString(),message:'Discovery failed. Inspect Activity for the saved run and source errors.'};}
 await env.BUCKET.put(key,JSON.stringify(finished));return finished;
}
