const KEY='hunt/preferences/job-visibility.json';
export const employerKey=value=>String(value||'').toLowerCase().replace(/&/g,' and ').replace(/[^a-z0-9]+/g,' ').replace(/\b(?:incorporated|inc|limited|ltd|llc|plc)\b/g,'').trim().replace(/\s+/g,' ');
export async function visibilitySettings(bucket){const x=await bucket.get(KEY);return x?x.json():{hidden_employers:[],hidden_jobs:[]};}
export function jobVisibility(job,settings){
 const role=settings.hidden_jobs.some(x=>x.id===job.id),employer=settings.hidden_employers.some(x=>x.key===employerKey(job.company));
 return {hidden:role||employer,hidden_role:role,hidden_employer:employer};
}
export async function updateVisibility(bucket,body,jobs){
 if(!['job','employer'].includes(body.scope)||typeof body.hidden!=='boolean')throw Error('Choose a role or employer and whether to hide it');
 const job=jobs.find(j=>j.id===body.job_id),company=job?.company||body.company,key=employerKey(company);
 if(body.scope==='job'&&!job)throw Error('Job not found');
 if(body.scope==='employer'&&(!key||key.length>180||!jobs.some(j=>employerKey(j.company)===key)))throw Error('Employer not found in this workspace');
 for(let attempt=0;attempt<3;attempt++){
  const old=await bucket.get(KEY),settings=old?await old.json():{hidden_employers:[],hidden_jobs:[]},field=body.scope==='job'?'hidden_jobs':'hidden_employers',identity=body.scope==='job'?job.id:key;
  settings[field]=settings[field].filter(row=>(body.scope==='job'?row.id:row.key)!==identity);
  if(body.hidden)settings[field].push(body.scope==='job'?{id:job.id,hidden_at:new Date().toISOString()}:{key,name:company,hidden_at:new Date().toISOString()});
  const saved=await bucket.put(KEY,JSON.stringify(settings),{onlyIf:old?{etagMatches:old.etag}:{etagDoesNotMatch:'*'}});
  if(saved)return {ok:true,visibility:settings,message:body.hidden?(body.scope==='employer'?company+' is hidden from job views, including future postings.':'Role hidden from job views.'):'Visibility restored. An employer rule may still hide this role.'};
 }
 throw Error('Visibility changed in another session. Reload and try again');
}
