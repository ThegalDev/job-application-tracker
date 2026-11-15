import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
globalThis.crypto ??= webcrypto;
globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));
globalThis.DRAFTING_INSTRUCTIONS='';globalThis.ASSETS={};
const {handle}=await import('./server.mjs');
class Bucket {data=new Map();async get(k){return this.data.has(k)?{json:async()=>JSON.parse(this.data.get(k))}:null}async put(k,v){this.data.set(k,v);return {etag:'1'}}async list(){return {objects:[]}}async delete(k){this.data.delete(k)}}
test('polling a second HUNT tab must not invalidate the first tab action token',async()=>{
 const b=new Bucket();await b.put('hunt/owner.json',JSON.stringify({id:'owner'}));await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{jobs:[],applications:[],facts:[],packages:[],events:[],sources:[]}}));
 const env={BUCKET:b,HUNT_PUBLIC_READ:'true'},request=(path,opts={})=>handle(new Request('https://hunt.example'+path,{...opts,headers:{'oai-authenticated-user-id':'owner',...opts.headers}}),env);
 const tab1=await (await request('/api/state')).json(),cookie='__Host-hunt_csrf='+tab1.csrf;
 const tab2=await (await request('/api/state',{headers:{Cookie:cookie}})).json();
 assert.equal(tab2.csrf,tab1.csrf,'Second-tab polling must reuse the valid browser cookie');
 const action=await request('/api/pause',{method:'POST',headers:{Cookie:'__Host-hunt_csrf='+tab2.csrf,'X-CSRF-Token':tab1.csrf,Origin:'https://hunt.example','Content-Type':'application/json'},body:'{"paused":false}'});
 assert.equal(action.status,202);
 const denied=await request('/api/pause',{method:'POST',headers:{Cookie:cookie,'X-CSRF-Token':'0'.repeat(64),Origin:'https://hunt.example','Content-Type':'application/json'},body:'{"paused":true}'});
 assert.equal(denied.status,403);assert.equal((await denied.json()).code,'CSRF_TOKEN_MISMATCH');
});
