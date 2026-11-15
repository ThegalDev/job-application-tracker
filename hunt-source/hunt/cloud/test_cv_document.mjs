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
