import assert from 'node:assert/strict';
import test from 'node:test';
import {webcrypto} from 'node:crypto';
import {hostedDiscover,hostedPackage} from './dist/server/index.js';
globalThis.crypto??=webcrypto;
class MemoryR2{
  data=new Map();
  async get(key){const value=this.data.get(key);return value===undefined?null:{etag:key+'-etag',json:async()=>JSON.parse(value)}}
  async put(key,value,options={}){if(options.onlyIf?.etagDoesNotMatch==='*'&&this.data.has(key))return null;this.data.set(key,value);return {key}}
  async list({prefix}){return {objects:[...this.data.keys()].filter(x=>x.startsWith(prefix)).map(key=>({key}))}}
  async delete(key){this.data.delete(key)}
}
const snapshot={at:new Date().toISOString(),paused:false,jobs:[],applications:[],facts:[],packages:[],sources:[],events:[],resources:{}};
async function bucketWith(data){const b=new MemoryR2();await b.put('hunt/snapshot.json',JSON.stringify({snapshot:data}));return b}

test('hosted runtime accepts manual redirects and never uses unsupported error redirect mode',async()=>{
 const bucket=await bucketWith(snapshot),calls=[],original=globalThis.fetch;
 globalThis.fetch=async(url,options)=>{calls.push({url,redirect:options.redirect});if(options.redirect==='error')throw Error('Invalid redirect value');assert.equal(options.redirect,'manual');return new Response(JSON.stringify(url.includes('greenhouse')?{jobs:[]}:url.includes('ashby')?{jobs:[]}:[]),{headers:{'Content-Type':'application/json'}})};
 try{const run=await hostedDiscover({BUCKET:bucket});assert.ok(run.sources_verified>0);assert.ok(calls.length>=12);assert.ok(calls.every(x=>x.redirect==='manual'))}finally{globalThis.fetch=original}
});

test('public feed redirects are rejected before body access and private destination is never fetched',async()=>{
 const bucket=await bucketWith(snapshot),calls=[],original=globalThis.fetch;
 globalThis.fetch=async(url,options)=>{calls.push(url);assert.equal(options.redirect,'manual');return {status:302,ok:false,headers:new Headers({Location:'http://169.254.169.254/latest/meta-data/'}),get body(){throw Error('Redirect body must not be read')}}};
 try{const run=await hostedDiscover({BUCKET:bucket});assert.equal(run.sources_verified,0);assert.equal(run.status,'failed');assert.ok(run.source_results.every(x=>x.error.includes('redirect rejected')));assert.ok(calls.every(x=>x.startsWith('https://')));assert.ok(!calls.some(x=>x.includes('169.254.169.254')))}finally{globalThis.fetch=original}
});

test('credential-bearing model redirect is never followed or retried and secret is not returned',async()=>{
 const job={id:'j',kind:'ashby',board:'acme',company:'Acme',title:'People Operations',location:'Remote worldwide',description:'Own onboarding and employee lifecycle operations.',url:'https://jobs.ashbyhq.com/acme/j',raw_hash:'v',open:1,assessment:{tier:'A',duplicate_applications:[],matches:[]}};
 const bucket=await bucketWith({...snapshot,jobs:[job],facts:[{id:'lifecycle',text:'Managed employee lifecycle operations.',source:'verified-cv'}]}),calls=[],original=globalThis.fetch;
 const sentinel='fake-secret-for-test-only';
 globalThis.fetch=async(url,options)=>{calls.push({url,mode:options.redirect});assert.equal(url,'https://api.openai.com/v1/responses');assert.equal(options.redirect,'manual');assert.equal(options.headers.Authorization,'Bearer '+sentinel);return {status:307,ok:false,headers:new Headers({Location:'https://untrusted.example/credential-capture'}),get body(){throw Error('Redirect body must not be read')}}};
 try{await assert.rejects(hostedPackage({BUCKET:bucket,OPENAI_API_KEY:sentinel},'j',true),error=>error.message.includes('redirect rejected')&&!error.message.includes(sentinel));assert.equal(calls.length,1);assert.ok(!calls.some(x=>x.url.includes('untrusted.example')))}finally{globalThis.fetch=original}
});
