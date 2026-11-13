import assert from 'node:assert/strict';
import test from 'node:test';
import {webcrypto} from 'node:crypto';
import worker,{hostedPackage} from './dist/server/index.js';
globalThis.crypto??=webcrypto;
class MemoryR2{data=new Map();async get(k){const v=this.data.get(k);return v===undefined?null:{etag:'v',json:async()=>JSON.parse(v)}}async put(k,v,opts={}){if(opts.onlyIf?.etagDoesNotMatch==='*'&&this.data.has(k))return null;this.data.set(k,v);return {key:k}}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key}))}}async delete(k){this.data.delete(k)}}
test('numeric failures preserve bounded private drafts while diagnostics expose only IDs and exact tokens',async()=>{
 const bucket=new MemoryR2(),env={BUCKET:bucket,OPENAI_API_KEY:'not-a-real-test-credential'};
 const job={id:'test-job',company:'Example',title:'People Operations',location:'Remote worldwide',description:'Coordinate onboarding and workflow processes.',url:'https://jobs.ashbyhq.com/example/test-job',open:1,raw_hash:'v',assessment:{tier:'A',duplicate_applications:[],matches:[]}};
 const snapshot={at:new Date().toISOString(),paused:false,jobs:[job],applications:[],facts:[{id:'onboarding',text:'Coordinated onboarding for more than 300 employees.',source:'https://private-source.test/cv'}],packages:[],sources:[],events:[],resources:{}};
 await bucket.put('hunt/snapshot.json',JSON.stringify({snapshot}));
 await bucket.put('hunt/private/master-cv.json',JSON.stringify({text:'PRIVATE_FULL_CV_SENTINEL',sha256:'unused-during-failed-validation'}));
 await bucket.put('hunt/private/failed-drafts.json',JSON.stringify(Array.from({length:5},(_,i)=>({id:'old-'+i,status:'requires_revision',drafts:{cover_letter:'old private draft'}}))));
 const generated={cover_letter:'Day 1 needs consistency. I coordinated onboarding for 301 employees.',cold_email_subject:'Keep the first day moving',cold_email:'Your onboarding needs dependable coordination.',cv_summary:'People Operations experience.',fact_ids:['onboarding']};
 const originalFetch=globalThis.fetch;let calls=0;
 globalThis.fetch=async(url,options)=>{calls++;assert.ok(!options.body.includes('PRIVATE_FULL_CV_SENTINEL'));assert.ok(!options.body.includes(env.OPENAI_API_KEY));return new Response(JSON.stringify({status:'completed',output:[{type:'message',content:[{type:'output_text',text:JSON.stringify(generated)}]}]}))};
 let diagnostic;
 try{await assert.rejects(hostedPackage(env,job.id,true),error=>{diagnostic=error.diagnostic;return /unsupported number/i.test(error.message)})}finally{globalThis.fetch=originalFetch}
 assert.equal(calls,1);assert.deepEqual(diagnostic.fact_ids,['onboarding']);assert.deepEqual(diagnostic.unsupported_tokens,['1','301']);assert.equal(diagnostic.status,'requires_revision');
 const stored=JSON.parse(bucket.data.get('hunt/private/failed-drafts.json'));assert.equal(stored.length,5);assert.equal(stored[0].drafts.cover_letter,generated.cover_letter);assert.ok(!JSON.stringify(stored).includes('PRIVATE_FULL_CV_SENTINEL'));assert.ok(!JSON.stringify(stored).includes(env.OPENAI_API_KEY));assert.equal(await bucket.get('hunt/runtime/packages.json'),null);
 const request=(path,user)=>worker.fetch(new Request('https://hunt.example'+path,{headers:user?{'oai-authenticated-user-id':user}:{}}),env);
 const metadata=await (await request('/api/bridge/draft-failures')).json();assert.equal(metadata.failures[0].drafts,undefined);assert.deepEqual(metadata.failures[0].unsupported_tokens,['1','301']);
 const bridgeState=await (await request('/api/bridge/state')).json();assert.equal(bridgeState.latest_failed_drafts[0].drafts,undefined);assert.equal(bridgeState.latest_failed_drafts[0].id,diagnostic.id);
 const ownerState=await (await request('/api/state','owner')).json();assert.ok(!JSON.stringify(ownerState).includes(generated.cover_letter));assert.ok(!JSON.stringify(ownerState).includes('PRIVATE_FULL_CV_SENTINEL'));
 const privateFailure=await (await request('/api/draft-failures?id='+diagnostic.id,'owner')).json();assert.equal(privateFailure.drafts.cover_letter,generated.cover_letter);
 assert.equal((await request('/api/draft-failures?id='+diagnostic.id)).status,401);
 assert.equal((await request('/api/draft-failures?id='+diagnostic.id,'someone-else')).status,403);
});
