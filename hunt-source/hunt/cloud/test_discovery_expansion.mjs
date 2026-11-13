import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
globalThis.crypto ??= webcrypto;
const app=await import('./server.mjs');
class MemoryR2{data=new Map();async get(k){return this.data.has(k)?{json:async()=>JSON.parse(this.data.get(k))}:null}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key})),truncated:false}}async put(k,v){this.data.set(k,v);return {key:k}}}
const job=(extra={})=>({id:'one',title:'Contract Recruiter',company:'Global Co',location:'Remote worldwide',description:'Candidates must have three years of recruitment experience. Own hiring workflows. USD 3000 per month.',open:1,...extra});
test('work experience requirements do not masquerade as geographic restrictions',()=>{
 for(const text of ['Candidates must have three years of recruitment experience.','Applicants are required to have experience in US recruiting.','You need to have experience with UK candidates.'])assert.equal(app.assess(job({description:text+' USD 3000 per month.'}),{facts:[]}).tier,'A');
});
test('real foreign country work authorization and residency remain excluded',()=>{
 for(const text of ['Candidates must have US work authorization.','Applicants must reside in Canada.','You must be legally authorized to work in United States.','US-only role.'])assert.equal(app.assess(job({description:text+' USD 3000 per month.'}),{facts:[]}).tier,'D',text);
 assert.equal(app.assess(job({description:'Applicants based in Nigeria are not eligible. USD 3000 per month.'}),{facts:[]}).tier,'D');
});
test('new public providers preserve provenance, full descriptions and uncertain original publication',async()=>{
 const date=new Date().toISOString(),raw='<p>Recruitment workflow.</p><a href="https://jobs.ashbyhq.com/acme/123">Apply</a>';
 const [r]=await app.normalizeBroadFeed({kind:'remotive'},{jobs:[{id:1,title:'Contract Recruiter',company_name:'Acme',candidate_required_location:'Worldwide',description:raw,url:'https://remotive.com/remote-jobs/hr/recruiter-1',publication_date:date}]});
 assert.equal(r.original_application_url,'https://jobs.ashbyhq.com/acme/123');assert.equal(r.source_attribution,'Remotive');assert.equal(r.publication_verified_original,false);assert.equal(app.freshness(r),'publication_unverified');assert.equal(r.source_url,r.url);
 const [j]=await app.normalizeBroadFeed({kind:'jobicy'},{jobs:[{id:2,jobTitle:'Talent Acquisition Partner',companyName:'Other',jobGeo:'Anywhere',jobDescription:raw,url:'https://jobicy.com/jobs/2',pubDate:date,jobType:['Contract']}]});
 assert.equal(j.board_published,date);assert.equal(j.published,null);assert.equal(j.employment_type,'Contract');assert.equal(j.source_attribution,'Jobicy');
 assert.deepEqual(await app.normalizeBroadFeed({kind:'jobicy'},{jobs:[{id:3,jobTitle:'Recruiter',url:'https://evil.test/job'}]}),[]);
});
test('funnel distinguishes leads, publication uncertainty, eligibility and compensation from zero confirmed',()=>{
 const unknown=job({id:'unknown',publication_verified_original:false});unknown.assessment=app.assess(unknown,{facts:[]});
 const date=new Date().toISOString(),fresh=job({id:'fresh',published:date,publication_verified_original:true,description:'Recruiting full-time.'});fresh.assessment=app.assess(fresh,{facts:[]});
 const regional=job({id:'regional',location:'Remote Africa'});regional.assessment=app.assess(regional,{facts:[]});
 const f=app.discoveryFunnel([unknown,fresh,regional],new Set(['unknown','fresh','regional']));assert.equal(f.relevant_postings_observed,3);assert.equal(f.unique_unapplied_remote_leads,3);assert.equal(f.publication_needs_verification,2);assert.equal(f.confirmed_recent_eligible,1);assert.equal(f.nigeria_eligibility_needs_verification,1);assert.equal(f.compensation_needs_verification,1);assert.match(f.coverage,/not a whole-web/);
});
test('discovery actually queries broad providers, caches repeated reads and reports paging limits',async()=>{
 const env={BUCKET:new MemoryR2()},urls=[],old=globalThis.fetch;
 globalThis.fetch=async url=>{const u=new URL(url);urls.push(u.href);if(u.hostname==='remotive.com')return Response.json({jobs:[]});if(u.hostname==='jobicy.com')return Response.json({success:true,jobs:[],nextCursor:u.searchParams.has('cursor')?'next-page':'page-two'});if(u.hostname==='remoteok.com')return Response.json([]);if(u.hostname==='weworkremotely.com')return new Response('<rss></rss>');if(u.hostname==='api.lever.co')return Response.json([]);return Response.json({jobs:[]})};
 try{const a=await app.hostedDiscover(env,{idempotency_key:'first'});assert.equal(urls.filter(x=>x.startsWith('https://remotive.com/')).length,1);assert.equal(urls.filter(x=>x.startsWith('https://jobicy.com/')).length,8);assert.equal(a.source_results.filter(s=>s.id.startsWith('jobicy:')&&s.has_more).length,4);assert.equal(a.coverage.whole_web,false);assert.equal(a.coverage.authenticated_linkedin,false);assert.equal(a.funnel.relevant_postings_observed,0);const before=urls.length;const b=await app.hostedDiscover(env,{idempotency_key:'second'});assert.equal(urls.slice(before).filter(x=>/remotive.com|jobicy.com/.test(x)).length,0);assert.equal(b.source_results.filter(s=>s.cache_hit).length,7);assert.match(b.message,/bounded scan/)}finally{globalThis.fetch=old}
});

test('foreign country location does not enter Nigeria investigation as worldwide',()=>{for(const location of ['Remote U.S.','United States','France','Remote Canada','Philippines','Hong Kong, Singapore'])assert.equal(app.assess(job({location}),{facts:[]}).tier,'D',location);assert.equal(app.assess(job({location:'Remote worldwide'}),{facts:[]}).tier,'A');assert.equal(app.assess(job({location:'Remote Lagos Nigeria'}),{facts:[]}).tier,'A')});
