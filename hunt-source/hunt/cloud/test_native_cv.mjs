import {test} from 'node:test';
import assert from 'node:assert/strict';
import {webcrypto,createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {createNativeCVTask,validateNativeRewrites,executeNativeCVDraft} from './native-cv.mjs';
globalThis.crypto??=webcrypto;
globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));globalThis.ASSETS={};globalThis.DRAFTING_INSTRUCTIONS='';
const {handle}=await import('./server.mjs');
class Bucket{data=new Map();version=0;async get(k){const row=this.data.get(k);return row?{etag:row.etag,json:async()=>JSON.parse(row.value)}:null}async put(k,value,options={}){const prior=this.data.get(k);if(options.onlyIf?.etagDoesNotMatch==='*'&&prior||options.onlyIf?.etagMatches&&prior?.etag!==options.onlyIf.etagMatches)return null;const etag=String(++this.version);this.data.set(k,{value,etag});return {etag}}async list(){return {objects:[]}}}
test('complete native mapping preserves paragraph boundaries, metrics and protected sections',()=>{
 const source=[{id:1,text:'Managed records for 1,000 employees.',editable:true,kind:'bullet'},{id:2,text:'Verified degree',editable:false}];
 assert.deepEqual(validateNativeRewrites(source,{replacements:[{id:1,text:'Maintained accurate records for 1,000 employees.'}]}).replacements.length,1);
 for(const text of ['Managed records for 5,000 employees.','Managed records.','Managed\nrecords for 1,000 employees.'])assert.throws(()=>validateNativeRewrites(source,{replacements:[{id:1,text}]}));
 assert.throws(()=>validateNativeRewrites(source,{replacements:[]}));assert.throws(()=>validateNativeRewrites(source,{replacements:[{id:1,text:source[0].text},{id:2,text:'Invented degree'}]}));
});
test('native draft reserves once and repeated background delivery does not call the model twice',async()=>{
 const BUCKET=new Bucket(),env={BUCKET,OPENAI_API_KEY:'fixture'},input={source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'revision',paragraphs:[{id:1,text:'Maintained accurate employee records.',editable:true,kind:'bullet'}]};
 const task=await createNativeCVTask(BUCKET,input,{id:'job',raw_hash:'v1'});let calls=0;
 const fetcher=async()=>{calls++;return Response.json({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({replacements:[{id:1,text:'Maintained accurate employee records.'}]})}]}]})};
 await Promise.all([executeNativeCVDraft(env,task.id,'fixture',fetcher),executeNativeCVDraft(env,task.id,'fixture',fetcher)]);assert.equal(calls,1);assert.equal((await (await BUCKET.get('hunt/private/native-cv-tasks/'+task.id+'.json')).json()).status,'completed');
});
test('native PDF downloads bind exact private bytes and reject corrupted storage and anonymous access',async()=>{
 const BUCKET=new Bucket(),bytes=Buffer.from('%PDF-1.4\nfixture-native-export'),sha256=createHash('sha256').update(bytes).digest('hex'),p={id:'native-fixture',payload_hash:'a'.repeat(64),native_cv:{sha256,document_revision:'revision'}};
 await BUCKET.put('hunt/owner.json','{"id":"owner"}');await BUCKET.put('hunt/runtime/packages.json',JSON.stringify([p]));await BUCKET.put('hunt/private/native-cv-pdfs/'+sha256+'.json',JSON.stringify({pdf_base64:bytes.toString('base64')}));
 const url='https://hunt.example/api/cv-artifact?id='+p.id+'&hash='+p.payload_hash,env={BUCKET,HUNT_PUBLIC_READ:'true'},headers={'oai-authenticated-user-id':'owner'};
 assert.equal((await handle(new Request(url),env)).status,403);
 const result=await handle(new Request(url,{headers}),env);assert.equal(result.headers.get('Content-Type'),'application/pdf');assert.deepEqual(Buffer.from(await result.arrayBuffer()),bytes);
 await BUCKET.put('hunt/private/native-cv-pdfs/'+sha256+'.json',JSON.stringify({pdf_base64:Buffer.from('%PDF-tampered').toString('base64')}));assert.equal((await handle(new Request(url,{headers}),env)).status,400);
});
