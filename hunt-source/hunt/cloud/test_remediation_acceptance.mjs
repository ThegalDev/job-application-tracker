// Independent remediation fixtures. All storage is in memory and all fetches are mocked.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto,createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
globalThis.crypto ??= webcrypto;
globalThis.WRITING_PROFILE=JSON.parse(await readFile(new URL('../writing-profile.json',import.meta.url),'utf8'));
globalThis.DRAFTING_INSTRUCTIONS=await readFile(new URL('../drafting-instructions.txt',import.meta.url),'utf8');
globalThis.ASSETS={'/':'<h1>HUNT fixture</h1>'};
const app=await import('./server.mjs');
const NOW=Date.parse('2026-11-12T12:00:00Z'),HOUR=3600000;
const original=(published)=>({published,publication_verified_original:true,
  publication_source:'https://job-boards.greenhouse.io/fixture/jobs/one',
  publication_semantics:'employer_first_publication',publication_observed_at:'2026-11-12T12:00:00Z'});

class MemoryR2{
 data=new Map();version=0;
 async get(key){const entry=this.data.get(key);return entry?{etag:entry.etag,json:async()=>JSON.parse(entry.value)}:null}
 async put(key,value,options={}){const old=this.data.get(key);if(options.onlyIf?.etagDoesNotMatch==='*'&&old)return null;if(options.onlyIf?.etagMatches&&old?.etag!==options.onlyIf.etagMatches)return null;const entry={value,etag:String(++this.version)};this.data.set(key,entry);return {key,etag:entry.etag}}
 async delete(key){this.data.delete(key)}
 async list({prefix,limit=1000}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).sort().slice(0,limit).map(key=>({key})),truncated:false}}
}
const facts=['lifecycle','recruitment','notion','make','records','onboarding','policies','performance'].map(id=>({id,text:'Verified onboarding and workflow work in '+id+'.',source:'https://private-source.test/'+id,private_notes:'PRIVATE_METADATA_SENTINEL'}));
function posting(change={}){return {id:'fixture:one',company:'Fixture International',title:'People Operations Specialist',location:'Remote worldwide',description:'Own onboarding and workflow automation. Full-time. USD 3000 per month.',url:'https://job-boards.greenhouse.io/fixture/jobs/one',open:1,raw_hash:'fixture-version',verified:new Date().toISOString(),...original(new Date().toISOString()),...change}}
function snapshot(jobs=[]){return {at:new Date().toISOString(),jobs,applications:[],facts,packages:[],sources:[],events:[],runs:[],resources:{portfolio:'https://example.test/portfolio'},paused:false,preferences:{monthly_usd:2500,salary_is_hard_floor:true}}}
async function environment(jobs=[]){const env={BUCKET:new MemoryR2()};const s=snapshot(jobs);for(const j of s.jobs)j.assessment=app.assess(j,s);await env.BUCKET.put('hunt/snapshot.json',JSON.stringify({snapshot:s,stored_at:new Date().toISOString()}));return env}
async function request(env,path,{method='GET',body,token}={}){const headers={'oai-authenticated-user-id':'fixture-owner'};if(body!==undefined)headers['Content-Type']='application/json';if(token){headers.Cookie='__Host-hunt_csrf='+token;headers['X-CSRF-Token']=token;headers.Origin='https://hunt.example'}const response=await app.handle(new Request('https://hunt.example'+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)}),env);return {response,data:await response.json()}}

test('rolling48h uses publication instant including exact boundary and timezone offset',()=>{
 assert.equal(app.freshness(original('2026-11-10T12:00:00Z'),NOW),'within_48_hours');
 assert.notEqual(app.freshness(original('2026-11-10T11:59:59Z'),NOW),'within_48_hours');
 assert.equal(app.freshness(original('2026-11-10T13:00:00+01:00'),NOW),'within_48_hours');
 assert.notEqual(app.freshness(original('2026-11-12T12:00:01Z'),NOW),'within_48_hours');
});
test('unknown timezone, date-only, observed and updated dates never prove freshness',()=>{
 for(const value of ['2026-11-12','2026-11-12T11:00:00','not-a-date',null])assert.notEqual(app.freshness(original(value),NOW),'within_48_hours',String(value));
 assert.notEqual(app.freshness({updated:'2026-11-12T11:00:00Z',discovered:'2026-11-12T11:00:00Z',verified:'2026-11-12T11:00:00Z'},NOW),'within_48_hours');
 assert.notEqual(app.freshness({...original('2026-11-12T11:00:00Z'),publication_verified_original:false},NOW),'within_48_hours');
});
test('Greenhouse retrieve-job first_published is publication; updates do not refresh old roles',async()=>{
 const f={kind:'greenhouse',board:'fixture',company:'Fixture'};
 const base={id:1,title:'People Operations Specialist',location:{name:'Remote worldwide'},absolute_url:'https://job-boards.greenhouse.io/fixture/jobs/1',content:'Own onboarding. USD 3000 per month.'};
 const [old]=await app.normalizeHostedFeed(f,{jobs:[{...base,first_published:'2026-01-01T12:00:00Z',updated_at:'2026-11-12T11:00:00Z'}]});
 assert.notEqual(app.freshness(old,NOW),'within_48_hours');
 const [fresh]=await app.normalizeHostedFeed(f,{jobs:[{...base,first_published:'2026-11-12T11:00:00Z'}]});
 assert.equal(app.freshness(fresh,NOW),'within_48_hours');
 assert.equal(fresh.publication_verified_original,true);
 assert.ok(fresh.publication_source,'Publication must retain source provenance');
});
test('Ashby last-published and Lever created are not proven original-new publication',async()=>{
 const [ashby]=await app.normalizeHostedFeed({kind:'ashby',board:'fixture',company:'Fixture'},{jobs:[{id:'a',title:'People Operations Specialist',location:'Remote worldwide',jobUrl:'https://jobs.ashbyhq.com/fixture/a',descriptionPlain:'Own onboarding.',publishedAt:'2026-11-12T11:00:00Z',workplaceType:'Remote'}]});
 assert.notEqual(app.freshness(ashby,NOW),'within_48_hours');
 const [lever]=await app.normalizeHostedFeed({kind:'lever',board:'fixture',company:'Fixture'},[{id:'l',text:'People Operations Specialist',categories:{location:'Remote worldwide'},hostedUrl:'https://jobs.lever.co/fixture/l',descriptionPlain:'Own onboarding.',createdAt:NOW-HOUR}]);
 assert.notEqual(app.freshness(lever,NOW),'within_48_hours');
});
test('worldwide marketing cannot override multiple foreign restrictions',()=>{
 const cases=[['Remote worldwide','US-only role.'],['Remote worldwide','Applicants must reside within Canada.'],['Remote worldwide','Candidates must have UK work authorization.'],['Remote worldwide','Eligible countries: United States, Canada.'],['Remote worldwide','Applicants based in Nigeria are not eligible.'],['Remote worldwide (US and Canada)','Own onboarding.']];
 const falsePositives=cases.map(([location,description])=>({location,description,tier:app.assess(posting({location,description:description+' USD 3000 per month.'}),snapshot()).tier})).filter(x=>['A','B'].includes(x.tier));
 assert.deepEqual(falsePositives,[]);
});
test('hosted discovery has no successful refresh when every source fails',async()=>{
 const env=await environment();const attempts=[];const originalFetch=globalThis.fetch;
 globalThis.fetch=async(url)=>{attempts.push(String(url));return new Response('Fixture outage',{status:503})};
 try{const result=await app.hostedDiscover(env,{idempotency_key:'qa-outage-fixture'});assert.equal(result.status,'failed');assert.equal(result.sources_verified,0);assert.ok(result.sources_checked>=10);assert.notEqual(result.queued,true);assert.ok(!/successfully refreshed/i.test(result.message||''));}
 finally{globalThis.fetch=originalFetch}
 const hosts=new Set(attempts.map(u=>new URL(u).hostname));assert.ok([...hosts].filter(h=>!['boards-api.greenhouse.io','api.ashbyhq.com','api.lever.co'].includes(h)).length>=2,'Discovery must actually attempt at least two broad feeds beyond ATS boards');
});
test('hosted source package honestly stays an outline; missing AI is no fake success',async()=>{
 const env=await environment([posting()]);
 const result=await app.hostedPackage(env,'fixture:one',false);
 assert.match(result.generation,/source|outline/i);
 assert.match(result.cover_letter,/not a finished|outline/i);
 assert.ok(result.limitations.some(x=>/not a tailored full CV|full CV.*not.*uploaded/i.test(x)));
 await assert.rejects(app.hostedPackage(env,'fixture:one',true),/not connected|runtime.*secret|not configured/i);
});
test('hosted missing Google pipeline returns blocker and never reports inbox checked',async()=>{
 const env=await environment();const state=await request(env,'/api/state');
 const result=await request(env,'/api/run',{method:'POST',body:{trigger:'pipeline'},token:state.data.csrf});
 assert.equal(result.response.status,503);assert.match(result.data.error,/not connected|not configured/i);assert.notEqual(result.data.status,'success');
 assert.equal((await request(env,'/api/state')).data.bridge.pending_commands,0);
});
test('review intent remains queued, never mislabeled completed approval',async()=>{
 const env=await environment([posting()]);await app.hostedPackage(env,'fixture:one',false);const state=await request(env,'/api/state');const p=state.data.packages[0];
 const review=await request(env,'/api/review',{method:'POST',body:{package_id:p.id,decision:'approved_for_manual_action'},token:state.data.csrf});
 assert.equal(review.response.status,202);assert.equal(review.data.queued,true);assert.equal(review.data.status,'queued');assert.match(review.data.message,/not executed|queued/i);
 const next=(await request(env,'/api/state')).data;assert.notEqual(next.packages.find(x=>x.id===p.id).status,'approved_for_manual_action');
});
test('hybrid and local onsite jobs cannot enter global fully remote presentation',async()=>{
 const env=await environment([posting({id:'hybrid-loc',location:'Remote worldwide / Hybrid'}),posting({id:'hybrid-body',description:'This is a hybrid role. Own onboarding. USD 3000 per month.'}),posting({id:'local',location:'Lagos, Nigeria',description:'Onsite People Operations. USD 3000 per month.'})]);
 const state=(await request(env,'/api/state')).data;
 for(const j of state.jobs)assert.equal(j.global_remote,false,j.id);
});

const FULL_CV='\ufeffPRIVATE_CV_CONTACT_SENTINEL\r\nPROFESSIONAL SUMMARY  \r\nOriginal career summary.\r\nCORE COMPETENCIES\r\nAll original systems and skills.\r\nPROFESSIONAL EXPERIENCE\r\nFirst role 2024—2025; every original bullet.\r\nSecond role 2025—Present; detailed achievements.\r\nEDUCATION\r\nAll original qualifications.\r\nPROJECTS\r\nComplete project architectures and evidence.\r\nCERTIFICATIONS\r\nOriginal training details.\r\n';
const hashText=text=>createHash('sha256').update(text).digest('hex');
async function storeCV(env,text=FULL_CV){const state=await request(env,'/api/state');return request(env,'/api/bridge/master-cv',{method:'POST',token:state.data.csrf,body:{text,source_url:'https://private-cv-source.test/original',sha256:hashText(text)}})}
const draft={cover_letter:'Dear hiring team,\nYour people systems need dependable ownership. My verified lifecycle work is relevant.\nAminat',cold_email_subject:'The person behind the process',cold_email:'Your people systems need ownership that keeps the team moving. My lifecycle work is relevant. Please put this application before the person leading the search.\nAminat',cv_summary:'Verified People Operations and lifecycle experience.',fact_ids:['lifecycle']};
function aiResponse(value=draft){return new Response(JSON.stringify({status:'completed',id:'fixture-model-response',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(value)}]}]}),{headers:{'Content-Type':'application/json'}})}
test('private hosted full CV remains exact in source mode and absent from generic state',async()=>{
 const env=await environment([posting()]);const saved=await storeCV(env);assert.equal(saved.response.status,200);assert.equal(saved.data.model_input,false);assert.equal(saved.data.snapshot_visible,false);
 const result=await app.hostedPackage(env,'fixture:one',false);assert.equal(result.resume_full,FULL_CV);assert.equal(result.full_cv_preserved,true);assert.equal(result.full_cv_source_hash,hashText(FULL_CV));
 const state=await request(env,'/api/state');assert.ok(!JSON.stringify(state.data).includes('PRIVATE_CV_CONTACT_SENTINEL'));assert.equal(state.data.packages[0].resume_full,undefined);
});
test('hosted AI changes only fullCV summary and transmits exactly eight approved excerpts',async()=>{
 const env={...await environment([posting()]),OPENAI_API_KEY:'fixture-not-a-real-key'};await storeCV(env);const captured=[];const originalFetch=globalThis.fetch;
 globalThis.fetch=async(url,options)=>{assert.equal(String(url),'https://api.openai.com/v1/responses');captured.push(JSON.parse(options.body));return aiResponse()};
 try{const result=await app.hostedPackage(env,'fixture:one',true);const end=FULL_CV.indexOf('\n',FULL_CV.indexOf('PROFESSIONAL SUMMARY'))+1;const suffix=FULL_CV.slice(FULL_CV.indexOf('CORE COMPETENCIES'));assert.equal(result.resume_full,FULL_CV.slice(0,end)+draft.cv_summary+'\n\n'+suffix);assert.equal(result.full_cv_preserved,true);assert.equal(result.writing_profile_version,WRITING_PROFILE.version);}
 finally{globalThis.fetch=originalFetch}
 assert.equal(captured.length,1);const body=captured[0],input=JSON.parse(body.input);assert.equal(body.store,false);assert.equal(body.tools,undefined);assert.deepEqual(input.approved_facts,facts.map(({id,text})=>({id,text})));assert.equal(input.approved_facts.length,8);for(const sentinel of ['PRIVATE_CV_CONTACT_SENTINEL','private-cv-source.test','PRIVATE_METADATA_SENTINEL','private-source.test'])assert.ok(!body.input.includes(sentinel),sentinel);
});
test('private CV hash mismatch cannot be stored as trusted source',async()=>{
 const env=await environment();const state=await request(env,'/api/state');const saved=await request(env,'/api/bridge/master-cv',{method:'POST',token:state.data.csrf,body:{text:FULL_CV,source_url:'https://private-cv-source.test/original',sha256:'0'.repeat(64)}});assert.equal(saved.response.status,400);assert.equal((await request(env,'/api/state')).data.cloud_runtime.full_cv_stored,false);
});
test('a changed master CV invalidates cached source packages instead of returning old chronology',async()=>{
 const env=await environment([posting()]);await storeCV(env);const first=await app.hostedPackage(env,'fixture:one',false);
 const updated=FULL_CV+'\r\nNEWLY_VERIFIED_PROJECT_SENTINEL\r\nComplete new project evidence.\r\n';await storeCV(env,updated);const second=await app.hostedPackage(env,'fixture:one',false);
 assert.equal(second.resume_full,updated);assert.notEqual(second.full_cv_source_hash,first.full_cv_source_hash);assert.notEqual(second.payload_hash,first.payload_hash);
});
test('hosted employer metric cannot become a candidate achievement with an unrelated fact citation',async()=>{
 const env={...await environment([posting({description:'Own onboarding. Employer target is to reduce turnover by 42%. USD 3000 per month.'})]),OPENAI_API_KEY:'fixture-not-a-real-key'};const originalFetch=globalThis.fetch;
 globalThis.fetch=async()=>aiResponse({...draft,cover_letter:'I reduced employee turnover by 42%.'});
 try{await assert.rejects(app.hostedPackage(env,'fixture:one',true),/unsupported|number|evidence/i)}
 finally{globalThis.fetch=originalFetch}
 assert.equal((await request(env,'/api/state')).data.packages.length,0);
});
test('default hosted opportunities excludes old local uncertain-pay and uncertain-geography records',async()=>{
 const source=await readFile(new URL('../web/app.js',import.meta.url),'utf8');
 const context=vm.createContext({});vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+'\nglobalThis.fixtureActive=(v)=>{state=v;return activeJobs().map(j=>j.id)};',context);
 const make=(id,tier='A',salary='meets_floor',changes={})=>({...posting({id}),within_discovery_window:true,global_remote:true,assessment:{tier,status:'Review',score:90,duplicate_applications:[],compensation:{status:salary}},...changes});
 const jobs=[make('qualified'),make('old-monies','A','meets_floor',{within_discovery_window:false}),make('unknown-geography','C'),make('unknown-pay','A','unknown'),make('range-crosses-floor','A','range_crosses_floor'),make('below-floor','D','below_floor'),make('hybrid','A','meets_floor',{global_remote:false}),make('closed','A','meets_floor',{open:0}),make('already-applied','A','meets_floor',{assessment:{tier:'A',status:'Already applied',score:90,duplicate_applications:['prior'],compensation:{status:'meets_floor'}}})];
 assert.deepEqual(Array.from(context.fixtureActive({hosted:true,jobs})),['qualified']);
 assert.deepEqual(Array.from(context.fixtureActive({hosted:true,jobs:jobs.filter(j=>j.id!=='qualified')})),[],'No confirmed match must display zero, without filling with old or uncertain jobs');
});
test('hosted Download package retrieves complete preserved CV rather than generic-state metadata',async()=>{
 const source=await readFile(new URL('../web/app.js',import.meta.url),'utf8');const button={dataset:{download:'fixture-package'}};
 const context=vm.createContext({button,document:{querySelectorAll:selector=>selector==='[data-download]'?[button]:[],querySelector:()=>null}});
 vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+`\nstate={hosted:true,packages:[{id:'fixture-package',role:'People Operations',full_cv_preserved:true}]};globalThis.calls=[];api=async(path)=>{calls.push(path);return {id:'fixture-package',resume_full:${JSON.stringify(FULL_CV)},full_cv_preserved:true}};action=async(b,fn)=>fn();download=(name,data)=>{globalThis.downloaded=JSON.parse(data)};bind();`,context);
 await button.onclick();assert.equal(context.downloaded.resume_full,FULL_CV);assert.ok(context.calls.some(x=>x==='package?id=fixture-package'));
});
test('a queued preparation response never opens a nonexistent finished package',async()=>{
 const source=await readFile(new URL('../web/app.js',import.meta.url),'utf8');const button={dataset:{prepare:'fixture-job'}};
 const context=vm.createContext({button,document:{querySelectorAll:selector=>selector==='[data-prepare]'?[button]:[],querySelector:()=>null}});
 vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+`\nstate={hosted:true};globalThis.opened=0;globalThis.refreshed=0;api=async()=>({queued:true,status:'queued',message:'Waiting; has not executed.'});packageDetail=async()=>{opened++};refresh=async()=>{refreshed++};action=async(b,fn)=>fn();bind();`,context);
 const result=await button.onclick();assert.equal(result.queued,true);assert.equal(context.opened,0);assert.equal(context.refreshed,0);assert.match(result.message,/not executed|waiting/i);
});
test('hosted source preparation button endpoint completes on cloud storage without desktop queue',async()=>{
 const env=await environment([posting()]);await storeCV(env);const state=await request(env,'/api/state');
 const prepared=await request(env,'/api/package',{method:'POST',token:state.data.csrf,body:{job_id:'fixture:one',use_ai:false}});
 assert.equal(prepared.response.status,200);assert.equal(prepared.data.queued,undefined);assert.equal(prepared.data.resume_full,FULL_CV);
 const reopened=await request(env,'/api/package?id='+prepared.data.id);assert.equal(reopened.response.status,200);assert.equal(reopened.data.resume_full,FULL_CV);
 assert.equal((await request(env,'/api/state')).data.bridge.pending_commands,0);
});
test('research queue retains uncertain matches separately and suppresses duplicate listings',async()=>{
 const source=await readFile(new URL('../web/app.js',import.meta.url),'utf8');const context=vm.createContext({});
 vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+'\nglobalThis.fixtureResearch=(v)=>{state=v;filter="verification";return opportunities()};',context);
 const make=(id,tier,salary,status='Research needed')=>({...posting({id}),within_discovery_window:true,global_remote:true,assessment:{tier,status,score:80,salary:'Unknown',duplicate_applications:[],compensation:{status:salary}}});
 const jobs=[make('unknown-geography','C','meets_floor'),make('unknown-pay','A','unknown'),make('crossing-pay','A','range_crosses_floor'),make('qualified','A','meets_floor','Review'),make('excluded','D','below_floor','Excluded'),{...make('duplicate-unknown-pay','A','unknown','Duplicate listing'),assessment:{...make('x','A','unknown').assessment,status:'Duplicate listing',duplicate_listing_of:'unknown-pay'}}];
 const html=context.fixtureResearch({hosted:true,jobs});const ids=[...html.matchAll(/data-job="([^"]+)"/g)].map(m=>m[1]);
 assert.deepEqual(ids,['unknown-geography','unknown-pay','crossing-pay']);
});
test('hosted numeric claim must match a complete approved metric rather than a substring',async()=>{
 const env={...await environment([posting()]),OPENAI_API_KEY:'fixture-not-a-real-key'};const record=await (await env.BUCKET.get('hunt/snapshot.json')).json();record.snapshot.facts[0].text='Managed records for 1000 employees.';await env.BUCKET.put('hunt/snapshot.json',JSON.stringify(record));const originalFetch=globalThis.fetch;
 globalThis.fetch=async()=>aiResponse({...draft,cover_letter:'I managed records for 100 employees.'});
 try{await assert.rejects(app.hostedPackage(env,'fixture:one',true),/unsupported|number|evidence/i)}
 finally{globalThis.fetch=originalFetch}
});
test('original employer country restrictions override a worldwide broad-board listing during discovery',async()=>{
 const env=await environment();const originalFetch=globalThis.fetch;const calls=[];const date=new Date().toISOString();
 globalThis.fetch=async(url)=>{const u=new URL(url);calls.push(u.href);if(u.hostname==='remoteok.com')return new Response(JSON.stringify([{id:42,position:'People Operations Specialist',company:'Fixture',location:'Worldwide',description:'Remote worldwide. Own onboarding. Full-time. USD 3000 per month.',date,url:'https://remoteok.com/remote-jobs/42',apply_url:'https://job-boards.greenhouse.io/fixture/jobs/42'}]));if(u.hostname==='weworkremotely.com')return new Response('<rss><channel></channel></rss>');if(u.pathname.endsWith('/jobs/42'))return new Response(JSON.stringify({id:42,title:'People Operations Specialist',first_published:date,location:{name:'United States'},content:'US-only role. Applicants must reside in the United States. Full-time. USD 3000 per month.',absolute_url:'https://job-boards.greenhouse.io/fixture/jobs/42'}));return new Response(JSON.stringify(u.hostname==='api.lever.co'?[]:{jobs:[]}))};
 try{await app.hostedDiscover(env,{idempotency_key:'qa-original-geography'});const state=(await request(env,'/api/state')).data;const broad=state.jobs.find(j=>j.id==='remoteok:42');assert.ok(broad);assert.ok(calls.some(x=>x.includes('/boards/fixture/jobs/42')),'Must actually fetch original employer source');assert.equal(broad.assessment.tier,'D','Original US-only restriction must win over board worldwide label');}
 finally{globalThis.fetch=originalFetch}
});
test('a genuinely fresh worldwide employer posting remains discoverable through a broad feed',async()=>{
 const env=await environment();const originalFetch=globalThis.fetch;const date=new Date().toISOString();
 globalThis.fetch=async(url)=>{const u=new URL(url);if(u.hostname==='remoteok.com')return new Response(JSON.stringify([{id:43,position:'People Operations Specialist',company:'Fixture',location:'Worldwide',description:'Remote worldwide. Own onboarding. Full-time. USD 3000 per month.',date,url:'https://remoteok.com/remote-jobs/43',apply_url:'https://job-boards.greenhouse.io/fixture/jobs/43'}]));if(u.hostname==='weworkremotely.com')return new Response('<rss><channel></channel></rss>');if(u.pathname.endsWith('/jobs/43'))return new Response(JSON.stringify({id:43,title:'People Operations Specialist',first_published:date,location:{name:'Remote worldwide'},content:'Remote worldwide. We accept applicants from Nigeria. Own onboarding. Full-time. USD 3000 per month.',absolute_url:'https://job-boards.greenhouse.io/fixture/jobs/43'}));return new Response(JSON.stringify(u.hostname==='api.lever.co'?[]:{jobs:[]}))};
 try{const result=await app.hostedDiscover(env,{idempotency_key:'qa-original-worldwide'});const state=(await request(env,'/api/state')).data;const broad=state.jobs.find(j=>j.id==='remoteok:43');assert.ok(broad);assert.equal(broad.assessment.tier,'A');assert.equal(broad.within_discovery_window,true);assert.equal(broad.global_remote,true);assert.equal(broad.assessment.compensation.status,'meets_floor');assert.equal(result.eligible_recent_remote,1);}
 finally{globalThis.fetch=originalFetch}
});
test('source-backed employer Day1 reference normalizes to words while candidate1 remains unsupported',async()=>{
 for(const token of ['Day 1','Day1']){
  const env={...await environment([posting({description:'Coordinate '+token+' readiness. Own onboarding. USD 3000 per month.'})]),OPENAI_API_KEY:'fixture-not-a-real-key'};const originalFetch=globalThis.fetch;
  globalThis.fetch=async()=>aiResponse({...draft,cover_letter:'Your '+token+' readiness depends on reliable coordination.\n\nMy verified lifecycle work is relevant.',cold_email_subject:'The welcome before '+token});
  try{const result=await app.hostedPackage(env,'fixture:one',true);assert.match(result.cover_letter,/first day/i);assert.doesNotMatch(result.cover_letter,/\b1\b/);assert.doesNotMatch(result.cold_email_subject,/\b1\b/)}
  finally{globalThis.fetch=originalFetch}
 }
 const env={...await environment([posting({description:'Coordinate Day 1 readiness. Own onboarding. USD 3000 per month.'})]),OPENAI_API_KEY:'fixture-not-a-real-key'};const originalFetch=globalThis.fetch;globalThis.fetch=async()=>aiResponse({...draft,cover_letter:'I supported 1 employee.'});
 try{await assert.rejects(app.hostedPackage(env,'fixture:one',true),/unsupported|number|evidence/i)}finally{globalThis.fetch=originalFetch}
});
test('Day1 without source evidence is rejected and actual failed-writing patterns stay blocked',async()=>{
 for(const [cover,pattern] of [['Your Day 1 readiness needs coordination.',/unsupported|number|evidence/i],['See [Candidate Portfolio Placeholder].',/placeholder/i],['I built onboarding programs supporting hundreds of new hires.',/ownership|coordination/i],['I bring operational excellence to your team.',/filler|writing|style/i]]){
  const env={...await environment([posting()]),OPENAI_API_KEY:'fixture-not-a-real-key'};const originalFetch=globalThis.fetch;globalThis.fetch=async()=>aiResponse({...draft,cover_letter:cover});
  try{await assert.rejects(app.hostedPackage(env,'fixture:one',true),pattern);assert.equal((await request(env,'/api/state')).data.packages.length,0)}finally{globalThis.fetch=originalFetch}
 }
});
test('private Day1 failure recovers to internal review without provider calls or a paid-attempt reservation',async()=>{
 const env=await environment([posting({description:'Coordinate Day 1 readiness. Own onboarding. USD 3000 per month.'})]);await storeCV(env);
 const failure={id:'fe12a005-807b-4cb2-b02e-0e3c8d0a20b8',job_id:'fixture:one',job_version:'fixture-version',writing_profile_version:WRITING_PROFILE.version,status:'requires_revision',error_code:'unsupported_numerical_tokens',unsupported_tokens:['1'],fact_ids:['lifecycle'],drafts:{...draft,cover_letter:'Your Day 1 readiness depends on reliable coordination.\n\nMy verified lifecycle work is relevant.'}};
 const counterKey='hunt/runtime/ai-attempts/'+new Date().toISOString().slice(0,10)+'.json';const counter={count:5,last_attempt:'fixture-existing-paid-attempt'};await env.BUCKET.put(counterKey,JSON.stringify(counter));
 await env.BUCKET.put('hunt/private/failed-drafts.json',JSON.stringify([failure]));const originalFetch=globalThis.fetch;let providerCalls=0;globalThis.fetch=async()=>{providerCalls++;throw new Error('Recovery must not call any provider')};
 try{const result=await app.recoverDraft(env,failure.id);assert.equal(result.status,'review');assert.match(result.cover_letter,/first day/i);assert.doesNotMatch(result.cover_letter,/\b1\b/);assert.deepEqual(result.claim_fact_ids,['lifecycle']);assert.equal(result.resume_full,FULL_CV.slice(0,FULL_CV.indexOf('\n',FULL_CV.indexOf('PROFESSIONAL SUMMARY'))+1)+draft.cv_summary+'\n\n'+FULL_CV.slice(FULL_CV.indexOf('CORE COMPETENCIES')));assert.equal(result.recovery.model_calls,0);const repeat=await app.recoverDraft(env,failure.id);assert.equal(repeat.id,result.id);assert.equal(providerCalls,0);assert.deepEqual(await (await env.BUCKET.get(counterKey)).json(),counter);const state=(await request(env,'/api/state')).data;assert.equal(state.bridge.pending_commands,0);assert.equal(state.packages.length,1);}
 finally{globalThis.fetch=originalFetch}
});
test('recovery rejects a changed job version without calling the model',async()=>{
 const env=await environment([posting()]);const failure={id:'fixture-stale-failure',job_id:'fixture:one',job_version:'old-job-version',writing_profile_version:WRITING_PROFILE.version,status:'requires_revision',fact_ids:['lifecycle'],drafts:draft};await env.BUCKET.put('hunt/private/failed-drafts.json',JSON.stringify([failure]));const originalFetch=globalThis.fetch;let providerCalls=0;globalThis.fetch=async()=>{providerCalls++;throw new Error('No provider permitted')};
 try{await assert.rejects(app.recoverDraft(env,failure.id),/version|changed|stale|job/i);assert.equal(providerCalls,0)}finally{globalThis.fetch=originalFetch}
});
test('recovery rejects a stale writing profile without calling the model',async()=>{
 const env=await environment([posting()]);const failure={id:'fixture-stale-profile',job_id:'fixture:one',job_version:'fixture-version',writing_profile_version:'previous-owner-writing-profile',status:'requires_revision',fact_ids:['lifecycle'],drafts:draft};await env.BUCKET.put('hunt/private/failed-drafts.json',JSON.stringify([failure]));const originalFetch=globalThis.fetch;let providerCalls=0;globalThis.fetch=async()=>{providerCalls++;throw new Error('No provider permitted')};
 try{await assert.rejects(app.recoverDraft(env,failure.id),/profile|writing|revision/i);assert.equal(providerCalls,0)}finally{globalThis.fetch=originalFetch}
});
