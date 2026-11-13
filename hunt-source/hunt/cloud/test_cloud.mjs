import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import worker from './dist/server/index.js';
globalThis.crypto??=webcrypto;
class MemoryR2{
  data=new Map();
  async get(key){const value=this.data.get(key);return value===undefined?null:{json:async()=>JSON.parse(value)}}
  async put(key,value,options={}){if(options.onlyIf?.etagDoesNotMatch==='*'&&this.data.has(key))return null;this.data.set(key,value);return {key}}
  async delete(key){this.data.delete(key)}
  async list({prefix,limit=1000}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).sort().slice(0,limit).map(key=>({key})),truncated:false}}
}
const env={BUCKET:new MemoryR2()},base='https://hunt.example';
const snapshot={at:new Date().toISOString(),jobs:[],applications:[],facts:[],packages:[],sources:[],events:[],runs:[],resources:{},paused:false,preferences:{monthly_usd:2500,salary_is_hard_floor:true},csrf:'do-not-store',session_token:'do-not-store'};
async function request(path,{user='owner',method='GET',body,token,origin,idempotency}={}){
  const headers={};if(user)headers['oai-authenticated-user-id']=user;if(body!==undefined)headers['Content-Type']='application/json';if(token){headers.Cookie='__Host-hunt_csrf='+token;headers['X-CSRF-Token']=token}if(origin)headers.Origin=origin;if(idempotency)headers['Idempotency-Key']=idempotency;
  const response=await worker.fetch(new Request(base+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)}),env);
  const data=await response.json().catch(()=>null);return {response,data};
}
assert.equal((await request('/api/state',{user:null})).response.status,401);
assert.equal((await request('/api/bridge/snapshot',{user:null,method:'POST',body:{snapshot}})).response.status,200);
let state=await request('/api/state');assert.equal(state.data.hosted,true);assert.equal(state.data.mode,'hosted_runtime');assert.equal(state.data.bridge.pending_commands,0);
const token=state.data.csrf;assert.match(state.response.headers.get('Set-Cookie'),/Secure; HttpOnly; SameSite=Strict/);
assert.equal((await request('/api/state',{user:'other-owner'})).response.status,403);
assert.equal((await request('/api/discover',{method:'POST',body:{}})).response.status,403);
assert.equal((await request('/api/discover',{method:'POST',body:{},token,origin:'https://evil.example'})).response.status,403);
assert.equal((await request('/api/bridge/snapshot',{method:'POST',body:{snapshot}})).response.status,403);
assert.equal((await request('/api/bridge/snapshot',{user:null,method:'POST',body:{snapshot},origin:'https://evil.example'})).response.status,403);
const queued=await request('/api/pause',{method:'POST',body:{paused:false},token,origin:base,idempotency:'test-pause-one'});
assert.equal(queued.response.status,202);assert.equal(queued.data.queued,true);assert.match(queued.data.message,/Pause state saved/);
const replay=await request('/api/pause',{method:'POST',body:{paused:false},token,origin:base,idempotency:'test-pause-one'});assert.equal(replay.data.command_id,queued.data.command_id);
let commands=await request('/api/bridge/commands',{user:null});assert.equal(commands.data.commands.length,1);assert.equal(commands.data.commands[0].type,'pause');
const ack=await request('/api/bridge/ack',{user:null,method:'POST',body:{id:queued.data.command_id,status:'completed',result:{run_id:'one'}}});assert.equal(ack.response.status,200);
assert.equal((await request('/api/bridge/commands',{user:null})).data.commands.length,0);
assert.equal((await request('/api/bridge/ack',{user:null,method:'POST',body:{id:queued.data.command_id,status:'completed'}})).data.replayed,true);
assert.equal((await request('/api/send',{method:'POST',body:{},token,origin:base})).response.status,403);
assert.equal((await request('/api/pause',{method:'POST',body:{paused:true},token,origin:base})).response.status,202);
assert.equal((await request('/api/state')).data.paused,true);
const meta=await request('/api/bridge/state',{user:null});assert.equal(meta.data.counts.applications,0);assert.equal(meta.data.control.paused,true);
const stored=JSON.parse(env.BUCKET.data.get('hunt/snapshot.json'));assert.equal(stored.snapshot.csrf,undefined);assert.equal(stored.snapshot.session_token,undefined);
assert.equal((await request('/api/bridge/snapshot',{user:null,method:'POST',body:{snapshot:{...snapshot,api_key:'fake'}}})).response.status,400);
assert.equal((await request('/api/package',{method:'POST',body:{job_id:'missing'},token,origin:base})).response.status,400);
const j={id:'job',open:1,raw_hash:'version',verified:new Date().toISOString(),assessment:{tier:'A',score:90,duplicate_applications:[],compensation:{status:'unknown',monthly_min:null}}};
const p={id:'package',job_id:'job',job_version:'version',payload_hash:'a'.repeat(64)};
await request('/api/bridge/snapshot',{user:null,method:'POST',body:{snapshot:{...snapshot,jobs:[j],packages:[p]}}});
assert.equal((await request('/api/review',{method:'POST',body:{package_id:'package',decision:'approved_for_manual_action'},token,origin:base})).response.status,400);
j.assessment.compensation={status:'meets_floor',monthly_min:2500};
await request('/api/bridge/snapshot',{user:null,method:'POST',body:{snapshot:{...snapshot,jobs:[j],packages:[p]}}});
const review=await request('/api/review',{method:'POST',body:{package_id:'package',decision:'approved_for_manual_action'},token,origin:base});assert.equal(review.response.status,202);
commands=await request('/api/bridge/commands',{user:null});const c=commands.data.commands.find(x=>x.type==='review');assert.equal(c.payload.payload_hash,p.payload_hash);assert.equal(c.payload.job_version,'version');
const assetResponse=await worker.fetch(new Request(base+'/',{headers:{'oai-authenticated-user-id':'owner'}}),env);assert.equal(assetResponse.status,200);assert.match(await assetResponse.text(),/HUNT/);
console.log('Cloud checks passed: durable snapshot/control/queue, owner isolation, CSRF/origin, idempotent receipts, salary approval gates, redaction, assets.');
