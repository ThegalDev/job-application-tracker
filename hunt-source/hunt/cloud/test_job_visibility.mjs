import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
import {visibilitySettings,jobVisibility,updateVisibility} from './visibility.mjs';
globalThis.crypto??=webcrypto;globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));globalThis.DRAFTING_INSTRUCTIONS='';globalThis.ASSETS={};
const {handle}=await import('./server.mjs');
class Bucket{data=new Map();n=0;async get(k){const x=this.data.get(k);return x?{etag:x.etag,json:async()=>JSON.parse(x.v)}:null}async put(k,v,o={}){const old=this.data.get(k);if(o.onlyIf?.etagDoesNotMatch==='*'&&old||o.onlyIf?.etagMatches&&old?.etag!==o.onlyIf.etagMatches)return null;const etag=String(++this.n);this.data.set(k,{v,etag});return {etag}}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key}))}}}
const job=(id,company='Moniepoint')=>({id,company,title:'People Operations Partner',description:'Own onboarding. USD 3000 per month.',location:'Remote worldwide',remote:true,open:1,verified:new Date().toISOString(),discovered:new Date().toISOString()});
test('employer hiding persists across new postings; per-role hiding can be independently restored',async()=>{
 const b=new Bucket(),jobs=[job('one'),job('two')];await updateVisibility(b,{scope:'employer',hidden:true,company:'Moniepoint'},jobs);
 let settings=await visibilitySettings(b);assert.equal(jobVisibility(job('future','Moniepoint Inc.'),settings).hidden,true);
 await updateVisibility(b,{scope:'job',hidden:true,job_id:'one'},jobs);await updateVisibility(b,{scope:'employer',hidden:false,company:'Moniepoint'},jobs);settings=await visibilitySettings(b);
 assert.equal(jobVisibility(jobs[0],settings).hidden,true);assert.equal(jobVisibility(jobs[1],settings).hidden,false);
 await updateVisibility(b,{scope:'job',hidden:false,job_id:'one'},jobs);assert.equal(jobVisibility(jobs[0],await visibilitySettings(b)).hidden,false);
});
test('owner hide action changes job visibility without deleting application history',async()=>{
 const b=new Bucket(),history=[{id:'application',company:'Moniepoint',role:'Earlier role',status:'Rejected'}];await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{jobs:[job('one')],applications:history,packages:[],facts:[],sources:[],events:[]}}));
 const env={BUCKET:b,HUNT_PUBLIC_READ:'true'},request=(path,opts={})=>handle(new Request('https://hunt.example'+path,{...opts,headers:{'oai-authenticated-user-id':'owner',...opts.headers}}),env),state=await(await request('/api/state')).json();
 const result=await request('/api/job-visibility',{method:'POST',headers:{Origin:'https://hunt.example','Content-Type':'application/json',Cookie:'__Host-hunt_csrf='+state.csrf,'X-CSRF-Token':state.csrf},body:JSON.stringify({scope:'employer',hidden:true,company:'Moniepoint'})});assert.equal(result.status,200);
 const next=await(await request('/api/state')).json();assert.equal(next.jobs[0].hidden,true);assert.deepEqual(next.applications,history);
 const denied=await handle(new Request('https://hunt.example/api/job-visibility',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"scope":"employer","company":"Moniepoint","hidden":false}'}),env);assert.equal(denied.status,401);
});
test('hidden jobs stay out of ordinary views and appear only in the explicit management view',()=>{
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8'),context=vm.createContext({});vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+'\nglobalThis.show=(s,f)=>{state=s;filter=f;return opportunities()};',context);
 const assessment={score:60,tier:'A',status:'Review',duplicate_applications:[],compensation:{status:'unknown'}};
 const s={hosted:true,jobs:[{...job('hidden'),hidden:true,hidden_employer:true,assessment},{...job('visible','Other Employer'),hidden:false,assessment}]};
 const normal=context.show(s,'all');assert.doesNotMatch(normal,/data-job="hidden"/);assert.match(normal,/data-job="visible"/);assert.match(normal,/Hide employer/);
 const hidden=context.show(s,'hidden');assert.match(hidden,/data-job="hidden"/);assert.doesNotMatch(hidden,/data-job="visible"/);assert.match(hidden,/Unhide employer/);
});
