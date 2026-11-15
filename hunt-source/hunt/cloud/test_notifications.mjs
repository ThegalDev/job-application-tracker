import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {connectNotifications,notifyRun,notificationStatus,RECIPIENT} from './notifications.mjs';
import {dispatchDiscovery,executeDiscoveryTask} from './netlify/discovery-tasks.mjs';
globalThis.crypto??=webcrypto;
class Bucket{data=new Map();version=0;async get(k){const r=this.data.get(k);return r?{etag:r.etag,json:async()=>JSON.parse(r.value)}:null}async put(k,v,o={}){const prior=this.data.get(k);if(o.onlyIf?.etagDoesNotMatch==='*'&&prior||o.onlyIf?.etagMatches&&prior?.etag!==o.onlyIf.etagMatches)return null;const etag=String(++this.version);this.data.set(k,{value:v,etag});return {etag}}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key}))}}}
const grant={account:RECIPIENT,scopes:['openid','email','https://www.googleapis.com/auth/gmail.send'],client_id:'fixture-client',client_secret:'fixture-secret',refresh_token:'fixture-refresh'};
const run={id:'fixture-discovery-run',status:'partial',finished:new Date().toISOString(),sources_verified:25,sources_checked:29,funnel:{relevant_postings_observed:160,record_breakdown:{confirmed:0}},private_cv:'DO_NOT_SEND_CV'};
function provider(captured){return async(url,opts)=>{if(String(url).endsWith('/token'))return Response.json({access_token:'fixture-access'});if(String(url).includes('/userinfo'))return Response.json({email:RECIPIENT,email_verified:true});assert.equal(String(url),'https://gmail.googleapis.com/gmail/v1/users/me/messages/send');captured.push(JSON.parse(opts.body));return Response.json({id:'fixture-message-id'})};}
test('notifications require a separate send grant; inbox-read grant cannot enable them',async()=>{
 const b=new Bucket();assert.equal((await notificationStatus(b)).status,'awaiting_send_authorization');assert.equal((await notifyRun(b,run)).status,'blocked');
 await assert.rejects(connectNotifications(b,{...grant,scopes:['https://www.googleapis.com/auth/gmail.readonly']}),/send-only/);
});
test('completed run sends one fixed-recipient summary and no CV; replay cannot send twice',async()=>{
 const b=new Bucket(),sent=[];await connectNotifications(b,grant,provider(sent));assert.equal((await notifyRun(b,run,provider(sent))).status,'sent');assert.equal((await notifyRun(b,run,provider(sent))).replayed,true);assert.equal(sent.length,1);
 const mime=Buffer.from(sent[0].raw,'base64url').toString();assert.match(mime,/To: majekadegbeaminat85@gmail.com/);assert.match(mime,/Sources completed: 25\/29/);assert.match(mime,/160/);assert.doesNotMatch(mime,/DO_NOT_SEND_CV|fixture-secret|fixture-refresh/);
 const state=await notificationStatus(b,run.id);assert.equal(state.last_notification.status,'sent');assert.doesNotMatch(JSON.stringify(state),/fixture-secret|fixture-refresh/);
});
test('unconfirmed email delivery is never retried automatically',async()=>{
 const b=new Bucket();await connectNotifications(b,grant,provider([]));let attempts=0;const network=async(url,opts)=>{if(String(url).endsWith('/token'))return Response.json({access_token:'fixture'});attempts++;throw Error('network timeout')};
 assert.equal((await notifyRun(b,run,network)).status,'uncertain');await notifyRun(b,run,network);assert.equal(attempts,1);
});
test('manual discovery acknowledges background work and completes through a durable task once',async()=>{
 const b=new Bucket(),env={BUCKET:b};let dispatches=0,executions=0;const dispatcher=async()=>{dispatches++;return new Response(null,{status:202})};
 const task=await dispatchDiscovery(env,'manual-fixture-run','https://hunt.example','fixture-service',dispatcher);assert.equal(task.status,'queued');await dispatchDiscovery(env,task.id,'https://hunt.example','fixture-service',dispatcher);assert.equal(dispatches,1);
 const discover=async()=>{executions++;return {...run,id:task.id}};await Promise.all([executeDiscoveryTask(env,task.id,discover),executeDiscoveryTask(env,task.id,discover)]);assert.equal(executions,1);assert.equal((await(await b.get('hunt/runtime/discovery-tasks/'+task.id+'.json')).json()).status,'completed');
});
test('background failure remains a failed saved task, never a completed discovery',async()=>{
 const b=new Bucket(),env={BUCKET:b};await dispatchDiscovery(env,'manual-failure-run','https://hunt.example','fixture-service',async()=>new Response(null,{status:202}));
 const result=await executeDiscoveryTask(env,'manual-failure-run',async()=>{throw Error('source unavailable')});assert.equal(result.status,'failed');assert.equal(result.result,undefined);
});
