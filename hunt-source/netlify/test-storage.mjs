import assert from 'node:assert/strict';
import {test} from 'node:test';
import {NetlifyBucket} from './runtime/storage.mjs';
import {bootstrap} from './runtime/bootstrap.mjs';
class Store{
 data=new Map();n=0;
 async getWithMetadata(k){return this.data.get(k)||null;}
 async set(k,value,o={}){const old=this.data.get(k);if(o.onlyIfNew&&old||o.onlyIfMatch&&old?.etag!==o.onlyIfMatch)return {modified:false};const row={data:value,etag:String(++this.n)};this.data.set(k,row);return {modified:true,etag:row.etag};}
 async delete(k){this.data.delete(k);}
 async list({prefix}){return {blobs:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key,etag:this.data.get(key).etag}))};}
}
test('durable adapter preserves JSON, conditional creation and stale version denial',async()=>{
 const b=new NetlifyBucket(new Store());assert.equal(await b.get('a'),null);
 const first=await b.put('a','{"count":1}',{onlyIf:{etagDoesNotMatch:'*'}});assert.ok(first.etag);
 assert.equal(await b.put('a','bad',{onlyIf:{etagDoesNotMatch:'*'}}),null);
 assert.equal(await b.put('a','bad',{onlyIf:{etagMatches:'stale'}}),null);
 assert.deepEqual(await (await b.get('a')).json(),{count:1});
 await b.put('a','{"count":2}',{onlyIf:{etagMatches:first.etag}});assert.equal((await(await b.get('a')).json()).count,2);
});
test('claimed success without persisted data fails closed',async()=>{
 const b=new NetlifyBucket({set:async()=>({modified:true}),getWithMetadata:async()=>null});
 await assert.rejects(()=>b.put('a','value'),/not confirmed/);
});
test('migration preserves records and full packages then no longer contacts original host',async()=>{
 const b=new NetlifyBucket(new Store()),original=globalThis.fetch;let reads=0;
 globalThis.fetch=async url=>{reads++;return Response.json(String(url).includes('/api/package')?{id:'p',resume_full:'Full CV fixture'}:{jobs:[],applications:[{id:'a'}],facts:[],packages:[{id:'p'}],sources:[],events:[],cloud_runs:[{id:'r'}],reports:[]});};
 try{await bootstrap(b);assert.equal(reads,2);const snapshot=await(await b.get('hunt/snapshot.json')).json();assert.equal(snapshot.snapshot.applications.length,1);assert.equal(snapshot.snapshot.packages[0].resume_full,'Full CV fixture');globalThis.fetch=async()=>{throw Error('Old host is unavailable');};await bootstrap(b);assert.equal(reads,2);}finally{globalThis.fetch=original;}
});
