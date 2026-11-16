import assert from 'node:assert/strict';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
globalThis.crypto??=webcrypto;
globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));
globalThis.DRAFTING_INSTRUCTIONS=readFileSync(new URL('../drafting-instructions.txt',import.meta.url),'utf8');
globalThis.ASSETS={'/':'<h1>HUNT</h1>','/app.js':'/* asset */','/style.css':'body{}'};
const app=await import('./server.mjs');
class Bucket{data=new Map();async get(k){return this.data.has(k)?{json:async()=>JSON.parse(this.data.get(k))}:null}async put(k,v){this.data.set(k,v);return {etag:'1'}}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key})),truncated:false}}async delete(k){this.data.delete(k)}}
const bucket=new Bucket();await bucket.put('hunt/owner.json',JSON.stringify({id:'owner'}));await bucket.put('hunt/snapshot.json',JSON.stringify({snapshot:{at:'2026-11-13',jobs:[{id:'one',company:'Fixture',title:'Recruiter',open:1}],applications:[{id:'one',company:'Fixture',role:'Recruiter'}],facts:[],packages:[{id:'package',resume_full:'User-authorized public CV'}],sources:[],events:[]}}));
const env={BUCKET:bucket,HUNT_PUBLIC_READ:'true',HUNT_BRIDGE_SECRET:'fixture-service-secret',OPENAI_API_KEY:'fixture-private-key'};
const request=(path,opts={})=>app.handle(new Request('https://hunt.example'+path,opts),env);
assert.equal((await request('/')).status,200);
assert.equal((await request('/api/state')).status,403);assert.equal((await request('/api/export')).status,403);assert.equal((await request('/api/package?id=package')).status,403);
const ownerRequest=(path,opts={})=>request(path,{...opts,headers:{...(opts.headers||{}),'oai-authenticated-user-id':'owner'}});
const state=await (await ownerRequest('/api/state')).json();assert.equal(state.public_view,undefined);assert.equal(state.applications.length,1);assert.ok(!JSON.stringify(state).includes('fixture-private-key'));
assert.equal((await request('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"trigger":"discovery"}'})).status,401);
assert.equal((await request('/api/bridge/state')).status,401);
assert.equal((await request('/api/bridge/state',{headers:{'X-HUNT-Service-Authorization':'wrong'}})).status,401);
assert.equal((await request('/api/bridge/state',{headers:{'X-HUNT-Service-Authorization':'fixture-service-secret'}})).status,200);
const ownerPackage=await ownerRequest('/api/package?id=package');assert.equal(ownerPackage.status,200);assert.equal((await ownerPackage.json()).resume_full,'User-authorized public CV');
assert.equal((await request('/api/draft-failures')).status,403);
assert.equal((await request('/api/apollo/contacts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:'one',company_domain:'fixture.test'})})).status,401);
env.APOLLO_API_KEY='fixture-apollo-secret';
const ownerState=await (await request('/api/state',{headers:{'oai-authenticated-user-id':'owner'}})).json();
let apolloRequest;const originalFetch=globalThis.fetch;
globalThis.fetch=async(url,options)=>{assert.equal(String(url),'https://api.apollo.io/api/v1/mixed_people/api_search');apolloRequest={headers:options.headers,body:JSON.parse(options.body)};return Response.json({total_entries:1,people:[{id:'person-one',first_name:'Amin',last_name_obfuscated:'Ma***e',title:'Talent Acquisition Lead',linkedin_url:'https://www.linkedin.com/in/example',has_email:true,email:'private@example.test',organization:{name:'Fixture'}}]})};
try{
 const token=ownerState.csrf,headers={'oai-authenticated-user-id':'owner','Content-Type':'application/json','Cookie':'__Host-hunt_csrf='+token,'X-CSRF-Token':token,Origin:'https://hunt.example'};
 const result=await request('/api/apollo/contacts',{method:'POST',headers,body:JSON.stringify({job_id:'one',company_domain:'https://www.fixture.test/careers'})});assert.equal(result.status,200);const data=await result.json();assert.equal(data.contacts[0].linkedin_url,'https://www.linkedin.com/in/example');assert.equal(data.contacts[0].has_email,true);assert.ok(!JSON.stringify(data).includes('private@example.test'));assert.equal(data.credits_used,0);assert.equal(apolloRequest.headers['x-api-key'],'fixture-apollo-secret');assert.deepEqual(apolloRequest.body.q_organization_domains_list,['fixture.test']);assert.ok(apolloRequest.body.person_titles.includes('Recruiter'));assert.equal(apolloRequest.body.per_page,10);
 const invalid=await request('/api/apollo/contacts',{method:'POST',headers,body:JSON.stringify({job_id:'one',company_domain:'not a domain'})});assert.equal(invalid.status,400);
}finally{globalThis.fetch=originalFetch;delete env.APOLLO_API_KEY}
console.log('Public data isolation, owner service boundary, and Apollo search safeguards passed.');
