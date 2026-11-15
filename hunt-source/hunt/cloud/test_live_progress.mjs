import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {executeDiscoveryTask} from './netlify/discovery-tasks.mjs';
globalThis.crypto??=webcrypto;
const {discoveryEventStream,handle}=await import('./server.mjs');
class Bucket{data=new Map();n=0;async get(k){const x=this.data.get(k);return x?{etag:x.etag,json:async()=>JSON.parse(x.value)}:null}async put(k,v,o={}){const old=this.data.get(k);if(o.onlyIf?.etagMatches&&old?.etag!==o.onlyIf.etagMatches)return null;const etag=String(++this.n);this.data.set(k,{value:v,etag});return {etag}}}
test('event stream delivers observed updates before completion and closes at the terminal record',async()=>{
 const b=new Bucket(),key='hunt/runtime/discovery-tasks/fixture-progress.json';
 const task=(status,seq,message)=>({id:'fixture-progress',status,progress:{events:[{seq,at:new Date().toISOString(),phase:status==='completed'?'done':'searching',message}],completed_sources:seq-1,total_sources:2,records_observed:seq*4}});
 await b.put(key,JSON.stringify(task('running',1,'Checking real fixture source')));
 const response=discoveryEventStream(b,'fixture-progress',{intervalMs:1,durationMs:1000});assert.match(response.headers.get('Content-Type'),/text\/event-stream/);
 const reader=response.body.getReader(),decode=x=>new TextDecoder().decode(x.value);let chunk=decode(await reader.read());assert.match(chunk,/Checking real fixture source/);assert.doesNotMatch(chunk,/"phase":"done"/);
 await b.put(key,JSON.stringify(task('completed',2,'Saved fixture result')));
 do{chunk=decode(await reader.read());}while(!chunk.includes('Saved fixture result'));
 assert.match(chunk,/"status":"completed"/);assert.equal((await reader.read()).done,true);
});
test('background reporter persists work in flight without inventing terminal progress',async()=>{
 const b=new Bucket(),key='hunt/runtime/discovery-tasks/fixture-task-progress.json';await b.put(key,JSON.stringify({id:'fixture-task-progress',status:'queued'}));
 let release,started;const gate=new Promise(r=>release=r),ready=new Promise(r=>started=r);
 const running=executeDiscoveryTask({BUCKET:b},'fixture-task-progress',async env=>{await env.reportDiscoveryProgress({phase:'starting',message:'Loading saved records'});await env.reportDiscoveryProgress({phase:'source_started',message:'Checking source',source:'fixture:one',total_sources:2,completed_sources:0});started();await gate;await env.reportDiscoveryProgress({phase:'saving',message:'Saving actual results',total_sources:2,completed_sources:2,records_observed:7});return {status:'partial',sources_verified:1,sources_checked:2}});
 await ready;const mid=await(await b.get(key)).json();assert.equal(mid.status,'running');assert.ok(mid.progress.events.some(e=>e.phase==='starting'));assert.ok(mid.progress.events.every(e=>e.phase!=='done'));
 release();const final=await running;assert.equal(final.progress.events.at(-1).phase,'done');assert.equal(final.progress.records_observed,7);assert.deepEqual(final.progress.events.map(e=>e.seq),[1,2,3,4]);
});
test('private run event streams require owner authentication',async()=>{
 const b=new Bucket();await b.put('hunt/owner.json','{"id":"owner"}');const denied=await handle(new Request('https://hunt.example/api/discovery-events?id=fixture-progress'),{BUCKET:b,HUNT_PUBLIC_READ:'true'});assert.equal(denied.status,403);
});
test('UI renders actual source counts, failures and timestamps with escaped messages',()=>{
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8'),host={dataset:{},querySelector:()=>null},context=vm.createContext({document:{querySelector:()=>host}});
 vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick")),context);
 context.showDiscoveryProgress({id:'fixture-progress',status:'running',progress:{completed_sources:3,total_sources:9,records_observed:12,events:[{seq:1,at:'2026-11-15T08:00:00Z',phase:'source_failed',message:'Feed unavailable <unsafe>'}]}});
 assert.match(host.innerHTML,/3 \/ 9/);assert.match(host.innerHTML,/12/);assert.match(host.innerHTML,/09:00:00/);assert.match(host.innerHTML,/Feed unavailable &lt;unsafe&gt;/);assert.doesNotMatch(host.innerHTML,/Almost done|<unsafe>/);assert.equal(host.hidden,false);
});
