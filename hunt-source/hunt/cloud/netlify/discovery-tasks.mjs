const PREFIX='hunt/runtime/discovery-tasks/';
const valid=id=>/^[A-Za-z0-9_-]{8,100}$/.test(id||'');
export async function dispatchDiscovery(env,id,origin,secret,fetcher=fetch){
 if(!secret)throw Error('Background discovery service is not configured');
 id=id||crypto.randomUUID();if(!valid(id))throw Error('Invalid run identity');const key=PREFIX+id+'.json',existing=await env.BUCKET.get(key);if(existing)return existing.json();
 const task={id,status:'queued',created_at:new Date().toISOString(),progress:{events:[{seq:1,at:new Date().toISOString(),phase:'queued',message:'Your discovery request is saved and waiting for the cloud runner.'}],completed_sources:0,total_sources:null,records_observed:0}};
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
 let finished,lastWrite=0,writes=Promise.resolve();
 const progress={events:[...(task.progress?.events||[])],completed_sources:0,total_sources:null,records_observed:0};
 const report=async event=>{
  const row={seq:(progress.events.at(-1)?.seq||0)+1,at:new Date().toISOString(),phase:String(event.phase||'running').slice(0,50),message:String(event.message||'').slice(0,400)};
  if(event.source)row.source=String(event.source).slice(0,150);
  for(const key of ['completed_sources','total_sources','records_observed'])if(Number.isFinite(event[key]))progress[key]=event[key];
  progress.events.push(row);if(progress.events.length>160)progress.events.shift();
  if(Date.now()-lastWrite<500&&!['starting','collating','filtering','saving','notifying'].includes(row.phase))return;
  lastWrite=Date.now();const snapshot=JSON.stringify({...running,progress});writes=writes.catch(()=>{}).then(()=>env.BUCKET.put(key,snapshot));await writes;
 };
 try{const result=await discover({...env,reportDiscoveryProgress:report},{idempotency_key:id});finished={...running,status:result.status==='failed'?'failed':'completed',finished_at:new Date().toISOString(),result};}
 catch{finished={...running,status:'failed',finished_at:new Date().toISOString(),message:'Discovery failed. Inspect Activity for the saved run and source errors.'};}
 await writes.catch(()=>{});
 progress.events.push({seq:(progress.events.at(-1)?.seq||0)+1,at:new Date().toISOString(),phase:finished.status==='completed'?'done':'failed',message:finished.status==='completed'?'Run finished. '+finished.result.sources_verified+' of '+finished.result.sources_checked+' sources completed; results are saved.':finished.message});
 finished.progress=progress;await env.BUCKET.put(key,JSON.stringify(finished));return finished;
}
