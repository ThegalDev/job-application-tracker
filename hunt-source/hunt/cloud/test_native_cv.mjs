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
 assert.doesNotThrow(()=>validateNativeRewrites([{id:1,text:'Built a practical recruitment assistant workflow.',editable:true,kind:'bullet'}],{replacements:[{id:1,text:'Built a practical recruitment assistant workflow using n8n.'}]}));
 assert.doesNotThrow(()=>validateNativeRewrites(source,{replacements:[{id:1,text:'Maintained accurate records for 1000 employees.'}]}));
 const project=[{id:0,text:'PROJECTS',editable:false},{id:1,text:'Culture project',editable:false},{id:2,text:'Tech Stack: Next.js 14, TypeScript, React',editable:false},{id:3,text:'Built a useful culture platform for HR teams.',kind:'bullet',editable:true}];
 assert.doesNotThrow(()=>validateNativeRewrites(project,{replacements:[{id:3,text:'Built a useful culture platform for HR teams using Next.js 14.'}]}));
 assert.throws(()=>validateNativeRewrites(project,{replacements:[{id:3,text:'Built a useful culture platform serving 14 HR teams.'}]}));
 assert.throws(()=>validateNativeRewrites([{id:1,text:'Managed HR operations and full-cycle recruitment.',kind:'bullet',editable:true}],{replacements:[{id:1,text:'Managed HR operations and full-cycle recruitment for Sales and Marketing.'}]}),/unsourced/);
 const labelled={replacements:[{id:1,text:'Recruitment Systems: Workable and HireFlix.'}]};validateNativeRewrites([{id:1,text:'Workable and HireFlix.',prefix:'Recruitment Systems:',kind:'bullet',editable:true}],labelled);assert.equal(labelled.replacements[0].text,'Workable and HireFlix.');
});
test('native draft reserves once and repeated background delivery does not call the model twice',async()=>{
 const BUCKET=new Bucket(),env={BUCKET,OPENAI_API_KEY:'fixture'},input={source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'revision',paragraphs:[{id:1,text:'Maintained accurate employee records.',editable:true,kind:'bullet'}]};
 const task=await createNativeCVTask(BUCKET,input,{id:'job',raw_hash:'v1'});let calls=0;
 const fetcher=async()=>{calls++;return Response.json({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({replacements:[{id:1,text:'Maintained accurate employee records.'}]})}]}]})};
 await Promise.all([executeNativeCVDraft(env,task.id,'fixture',fetcher),executeNativeCVDraft(env,task.id,'fixture',fetcher)]);assert.equal(calls,1);assert.equal((await (await BUCKET.get('hunt/private/native-cv-tasks/'+task.id+'.json')).json()).status,'completed');
});
test('a shortened bullet gets one scoped correction; every model call consumes allowance',async()=>{
 const BUCKET=new Bucket(),env={BUCKET,OPENAI_API_KEY:'fixture'},paragraphs=[{id:1,text:'Maintained accurate employee records across several distributed operational teams.',editable:true,kind:'bullet'},{id:2,text:'Supported recruitment workflows.',editable:true,kind:'bullet'}],task=await createNativeCVTask(BUCKET,{source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'r1',paragraphs},{id:'job',raw_hash:'v1'});let calls=0;
 const fetcher=async(url,options)=>{calls++;const input=JSON.parse(JSON.parse(options.body).input);if(calls===2)assert.deepEqual(input.paragraphs.filter(p=>p.editable).map(p=>p.id),[1]);const replacements=calls===1?[{id:1,text:'Managed records.'},{id:2,text:'Supported recruitment workflows.'}]:[{id:1,text:'Maintained accurate employee records across several distributed operational teams.'}];return Response.json({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({replacements})}]}]})};
 await executeNativeCVDraft(env,task.id,'fixture',fetcher);assert.equal(calls,2);const stored=await (await BUCKET.get('hunt/private/native-cv-tasks/'+task.id+'.json')).json();assert.equal(stored.status,'completed');assert.equal(stored.result.replacements.length,2);
 const allowance=await (await BUCKET.get('hunt/private/native-cv-ai-attempts/'+new Date().toISOString().slice(0,10)+'.json')).json();assert.equal(allowance.count,2);
 await executeNativeCVDraft(env,task.id,'fixture',fetcher);assert.equal(calls,2);
});
test('saved drafts recover without another generation only after every current validation passes',async()=>{
 const bucket=new Bucket(),body={source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'r1',paragraphs:[{id:1,text:'Built a practical recruitment assistant workflow.',editable:true,kind:'bullet'}]},job={id:'job',raw_hash:'v1'},task=await createNativeCVTask(bucket,body,job),key='hunt/private/native-cv-tasks/'+task.id+'.json',original=await (await bucket.get(key)).json();
 await bucket.put(key,JSON.stringify({...original,status:'failed',repair_attempts:2,candidate:{replacements:[{id:1,text:'Built a practical recruitment assistant workflow serving 900 employers.'}]}}));assert.equal((await createNativeCVTask(bucket,body,job)).status,'failed');
 await bucket.put(key,JSON.stringify({...original,status:'failed',candidate:{replacements:[{id:1,text:'Built a practical recruitment assistant workflow using n8n.'}]}}));assert.equal((await createNativeCVTask(bucket,body,job)).status,'completed');assert.equal((await (await bucket.get(key)).json()).recovered_without_model_call,true);
});
test('a missing non-bulleted project paragraph is repaired and merged back exactly once',async()=>{
 const BUCKET=new Bucket(),env={BUCKET,OPENAI_API_KEY:'fixture'},paragraphs=[{id:1,text:'Supported employee records.',editable:true,kind:'bullet'},{id:2,text:'A manual process needed reliable reporting.',prefix:'Problem: ',editable:true,kind:'project'}],task=await createNativeCVTask(BUCKET,{source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'r2',paragraphs},{id:'job',raw_hash:'v1'});let calls=0;
 const fetcher=async()=>Response.json({status:'completed',output:[{content:[{type:'output_text',text:JSON.stringify({replacements:++calls===1?[{id:1,text:'Supported employee records.'}]:[{id:2,text:'A manual process needed reliable operational reporting.'}]})}]}]});await executeNativeCVDraft(env,task.id,'fixture',fetcher);const result=await(await BUCKET.get('hunt/private/native-cv-tasks/'+task.id+'.json')).json();assert.equal(result.status,'completed');assert.deepEqual(result.result.replacements.map(p=>p.id),[1,2]);assert.equal(calls,2);
});
test('native PDF downloads bind exact private bytes and reject corrupted storage and anonymous access',async()=>{
 const BUCKET=new Bucket(),bytes=Buffer.from('%PDF-1.4\nfixture-native-export'),sha256=createHash('sha256').update(bytes).digest('hex'),p={id:'native-fixture',payload_hash:'a'.repeat(64),native_cv:{sha256,document_revision:'revision'}};
 await BUCKET.put('hunt/owner.json','{"id":"owner"}');await BUCKET.put('hunt/runtime/packages.json',JSON.stringify([p]));await BUCKET.put('hunt/private/native-cv-pdfs/'+sha256+'.json',JSON.stringify({pdf_base64:bytes.toString('base64')}));
 const url='https://hunt.example/api/cv-artifact?id='+p.id+'&hash='+p.payload_hash,env={BUCKET,HUNT_PUBLIC_READ:'true'},headers={'oai-authenticated-user-id':'owner'};
 assert.equal((await handle(new Request(url),env)).status,403);
 const result=await handle(new Request(url,{headers}),env);assert.equal(result.headers.get('Content-Type'),'application/pdf');assert.deepEqual(Buffer.from(await result.arrayBuffer()),bytes);
 await BUCKET.put('hunt/private/native-cv-pdfs/'+sha256+'.json',JSON.stringify({pdf_base64:Buffer.from('%PDF-tampered').toString('base64')}));assert.equal((await handle(new Request(url,{headers}),env)).status,400);
});
test('native attachment creates a new package version and rejects stale parents or missing provenance',async()=>{
 const BUCKET=new Bucket(),job={id:'job',company:'Fixture',title:'People Operations',raw_hash:'v1',open:true,description:'Remote worldwide HR operations.',location:'Remote worldwide'},base={id:'parent',job_id:'job',job_version:'v1',payload_hash:'a'.repeat(64),status:'review',company:'Fixture',role:'People Operations'},bytes=Buffer.from('%PDF-1.4\nfixture-export'),sha256=createHash('sha256').update(bytes).digest('hex');
 await BUCKET.put('hunt/owner.json','{"id":"owner"}');await BUCKET.put('hunt/snapshot.json',JSON.stringify({snapshot:{jobs:[job],packages:[],applications:[]}}));await BUCKET.put('hunt/runtime/packages.json',JSON.stringify([base]));
 const env={BUCKET},origin='https://hunt.example',token='a'.repeat(64),headers={'oai-authenticated-user-id':'owner',Origin:origin,Cookie:'__Host-hunt_csrf='+token,'X-CSRF-Token':token,'Content-Type':'application/json'},native_cv={source_doc_id:'1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ',source_revision:'r1',document_id:'fixture-copy-document-id',document_revision:'r2',master_unchanged:true,paragraphs_reviewed:98,qa:{paragraphs:177,bullets:90,drawings:7,links:Array(12).fill({url:'https://example.test'})},sha256,bytes:bytes.length},body={package_id:base.id,expected_payload_hash:base.payload_hash,native_cv,pdf_base64:bytes.toString('base64'),tailored_text:'Fixture tailored CV. '.repeat(65),master_text:'Fixture authoritative CV. '.repeat(60)};
 const post=b=>handle(new Request(origin+'/api/native-cv-attach',{method:'POST',headers,body:JSON.stringify(b)}),env);
 assert.equal((await post({...body,native_cv:{...native_cv,master_unchanged:false}})).status,400);
 const response=await post(body);assert.equal(response.status,200);const result=await response.json();assert.notEqual(result.id,base.id);assert.notEqual(result.payload_hash,base.payload_hash);assert.equal(result.native_cv.sha256,sha256);
 assert.equal((await post({...body,expected_payload_hash:'stale'})).status,400);
 const download=await handle(new Request(origin+'/api/cv-artifact?id='+result.id+'&hash='+result.payload_hash,{headers}),env);assert.deepEqual(Buffer.from(await download.arrayBuffer()),bytes);
});
