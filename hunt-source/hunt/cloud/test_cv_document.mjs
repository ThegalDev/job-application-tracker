import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
import {renderCV,cvArtifact,cvParagraphs} from './cv-document.mjs';
globalThis.crypto??=webcrypto;globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));globalThis.DRAFTING_INSTRUCTIONS='';globalThis.ASSETS={};
const {handle,preserveFullCV,selectProjectEvidence}=await import('./server.mjs');
const master='Fixture Candidate\nHR Professional\nPROFESSIONAL SUMMARY\nVerified recruitment experience.\nCORE COMPETENCIES\n* Recruitment & operations\nPROFESSIONAL EXPERIENCE\nEarlier Employer                 Lagos\nHR Officer                 2024–2025\n* Supported employee records.\nEDUCATION\nVerified qualification\nPROJECTS\nRecruitment Workflow\n* Built recruitment reporting with verified tools.';
const tailored=preserveFullCV(master,'Supported recruitment and employee records.','People Operations Specialist',selectProjectEvidence(master,'Recruitment reporting'));
const pkg={id:'fixture-p',payload_hash:'a'.repeat(64),company:'Fixture',role:'People Operations Specialist',resume_full:tailored,full_cv_preserved:true};
class Bucket{data=new Map();async get(k){const v=this.data.get(k);return v?{json:async()=>JSON.parse(v)}:null}async put(k,v){this.data.set(k,v);return {}}async list(){return {objects:[]}}}
test('tailored document preserves experience and qualifications and has deterministic bytes',async()=>{
 assert.ok(tailored.includes(master.slice(master.indexOf('CORE COMPETENCIES'))));assert.match(tailored,/Target role: People Operations Specialist/);assert.match(tailored,/SELECTED PROJECT HIGHLIGHTS/);
 const a=await cvArtifact(pkg),b=await cvArtifact(pkg);assert.deepEqual(a.bytes,b.bytes);assert.equal(a.sha256,createHash('sha256').update(a.bytes).digest('hex'));assert.equal(a.bytes[0],0x50);assert.equal(a.bytes[1],0x4b);assert.equal(a.filename,'Fixture-People-Operations-Specialist-CV.docx');
 const paragraphs=cvParagraphs(tailored);for(const phrase of ['Earlier Employer','HR Officer','Verified qualification','Supported employee records.'])assert.ok(paragraphs.some(p=>p.text.includes(phrase)));
 assert.notEqual((await cvArtifact({...pkg,resume_full:tailored+'\nNew owner revision'})).sha256,a.sha256);
});
test('document escapes candidate content and rejects incomplete CV packages',async()=>{
 assert.ok(new TextDecoder().decode(renderCV(master)).includes('Recruitment &amp; operations'));
 await assert.rejects(cvArtifact({...pkg,full_cv_preserved:false}),/complete preserved CV/);assert.throws(()=>renderCV('short'),/Complete/);
});
test('owner download returns exact verified document; anonymous and stale version requests cannot fetch it',async()=>{
 const b=new Bucket();await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/runtime/packages.json',JSON.stringify([pkg]));const env={BUCKET:b,HUNT_PUBLIC_READ:'true'};
 const path='https://hunt.example/api/cv-artifact?id=fixture-p&hash='+pkg.payload_hash,headers={'oai-authenticated-user-id':'owner'};
 assert.equal((await handle(new Request(path),env)).status,403);assert.equal((await handle(new Request(path.replace(pkg.payload_hash,'stale'),{headers}),env)).status,409);
 const r=await handle(new Request(path,{headers}),env);assert.equal(r.status,200);assert.match(r.headers.get('Content-Type'),/wordprocessingml/);const bytes=new Uint8Array(await r.arrayBuffer());assert.deepEqual(bytes,(await cvArtifact(pkg)).bytes);assert.equal(createHash('sha256').update(bytes).digest('hex'),r.headers.get('X-HUNT-Artifact-SHA256'));
 const meta=await (await handle(new Request(path+'&metadata=1',{headers}),env)).json();assert.equal(meta.sha256,r.headers.get('X-HUNT-Artifact-SHA256'));assert.equal(meta.bytes,undefined);
});
test('execution context is owner-only, binds job/package/document, and honors inherited pause',async()=>{
 const b=new Bucket(),job={id:'fixture-job',company:'Fixture',title:'People Operations Specialist',raw_hash:'v1',open:true,remote:true,location:'Remote worldwide',description:'Own recruitment workflows. USD 3000 per month.',url:'https://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111',verified:new Date().toISOString()};
 await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{paused:true,jobs:[job],packages:[],applications:[],facts:[],sources:[],events:[]}}));await b.put('hunt/runtime/packages.json',JSON.stringify([{...pkg,job_id:job.id,job_version:'v1'}]));
 const env={BUCKET:b,HUNT_PUBLIC_READ:'true'},url='https://hunt.example/api/application-context?job_id=fixture-job&package_id='+pkg.id;
 assert.equal((await handle(new Request(url),env)).status,403);
 const r=await handle(new Request(url,{headers:{'oai-authenticated-user-id':'owner'}}),env);assert.equal(r.status,200);const context=await r.json();assert.equal(context.paused,true);assert.equal(context.job.id,job.id);assert.equal(context.cv_artifact.package_hash,pkg.payload_hash);assert.equal(context.package.master_cv_current,false);assert.equal(context.resume_full,undefined);assert.equal(context.cv_artifact.bytes,undefined);
});
test('autonomous candidates respect priority, provider, original date, hidden employers and pause',async()=>{
 const b=new Bucket(),job={id:'lever-fixture',company:'Fixture',title:'People Operations Specialist',raw_hash:'v1',open:true,remote:true,location:'Remote worldwide',description:'Own recruitment workflows. Full-time. USD 3000 per month.',url:'https://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111',verified:new Date().toISOString(),published:new Date().toISOString(),publication_verified_original:true};
 await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{paused:false,jobs:[job],packages:[],applications:[],facts:[{id:'recruitment',text:'Verified recruitment workflows'}],sources:[],events:[]}}));
 const env={BUCKET:b,HUNT_PUBLIC_READ:'true'},request=()=>handle(new Request('https://hunt.example/api/application-candidates',{headers:{'oai-authenticated-user-id':'owner'}}),env);
 let result=await(await request()).json();assert.equal(result.candidates.length,1);assert.equal(result.candidates[0].job_version,'v1');
 await b.put('hunt/preferences/job-visibility.json',JSON.stringify({hidden_jobs:[],hidden_employers:[{key:'fixture'}]}));assert.equal((await(await request()).json()).candidates.length,0);
 await b.put('hunt/preferences/job-visibility.json',JSON.stringify({hidden_jobs:[],hidden_employers:[]}));await b.put('hunt/control.json','{"paused":true}');assert.equal((await(await request()).json()).candidates.length,0);
});
test('explicit available-role policy relaxes fit filters while keeping hidden jobs blocked',async()=>{
 const b=new Bucket(),job={id:'available-role',company:'Fixture',title:'People Operations Specialist',raw_hash:'v1',open:true,location:'United States',description:'HR operations and recruiting.',url:'https://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111'};
 await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{paused:false,jobs:[job],packages:[],applications:[],facts:[],sources:[],events:[]}}));const env={BUCKET:b},request=()=>handle(new Request('https://hunt.example/api/application-candidates',{headers:{'oai-authenticated-user-id':'owner'}}),env);
 assert.equal((await(await request()).json()).candidates.length,0);await b.put('hunt/private/application-policy.json','{"version":2,"mode":"apply_available"}');assert.equal((await(await request()).json()).candidates.length,1);
 await b.put('hunt/preferences/job-visibility.json',JSON.stringify({hidden_jobs:[{id:job.id}],hidden_employers:[{key:'fixture'}]}));assert.equal((await(await request()).json()).candidates.length,0);
});
