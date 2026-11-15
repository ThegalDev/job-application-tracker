import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {recordApplied,manualApplications,syncTracker,connectTracker,recordConfirmedApplication,TRACKER_ID} from './applications.mjs';
globalThis.crypto??=webcrypto;globalThis.WRITING_PROFILE=JSON.parse(readFileSync(new URL('../writing-profile.json',import.meta.url)));globalThis.DRAFTING_INSTRUCTIONS='';globalThis.ASSETS={};
const {handle}=await import('./server.mjs');
class Bucket{data=new Map();n=0;async get(k){const v=this.data.get(k);return v?{etag:v.etag,json:async()=>JSON.parse(v.data)}:null}async put(k,data,o={}){const old=this.data.get(k);if(o.onlyIf?.etagDoesNotMatch==='*'&&old||o.onlyIf?.etagMatches&&old?.etag!==o.onlyIf.etagMatches)return null;const etag=String(++this.n);this.data.set(k,{etag,data});return {etag}}async delete(k){this.data.delete(k)}async list({prefix}){return {objects:[...this.data.keys()].filter(k=>k.startsWith(prefix)).map(key=>({key}))}}}
const job={id:'fixture-recruiter',company:'Fixture Employer',title:'Recruiter',location:'Remote worldwide',remote:true,open:1,url:'https://jobs.lever.co/fixture/role',description:'Own recruitment.'};
const body={job_id:job.id,confirmed:true,applied_date:'2026-11-14',notes:'Owner application note'};
const snapshot={jobs:[job],applications:[]};
const headers=['S/N','Company','Role','Applied / first email','Latest email','Current status','Response type','Follow-up priority','Email evidence','Notes'];
const grant={account:'majekadegbeaminat85@gmail.com',scopes:['openid','email','https://www.googleapis.com/auth/spreadsheets'],client_id:'fixture-client',client_secret:'fixture-secret',refresh_token:'fixture-refresh'};
function provider({commitThenThrow=false,throwBeforeCommit=false}={}){
 const rows=[headers,['1','Existing Employer','Earlier job','2026-10-01','','Application reported','','Monitor','','Preserve this note']],batches=[];
 const template=Array.from({length:10},()=>({userEnteredFormat:{textFormat:{fontFamily:'Arial',link:{uri:'https://old-row.test'}}}}));
 template[5].dataValidation={condition:{type:'ONE_OF_LIST',values:[{userEnteredValue:'Application reported'},{userEnteredValue:'Application acknowledged'},{userEnteredValue:'Rejected'}]},strict:true};template[7].dataValidation={condition:{type:'ONE_OF_LIST',values:[{userEnteredValue:'Monitor'}]},strict:true};
 const fetcher=async(url,opts={})=>{const u=String(url);if(u.endsWith('/token'))return Response.json({access_token:'fixture-access'});if(u.includes('/userinfo'))return Response.json({email:grant.account,email_verified:true});
  assert.ok(u.startsWith('https://sheets.googleapis.com/v4/spreadsheets/'+TRACKER_ID),'Only the authorized tracker can be accessed');
  if(u.includes('/values/'))return Response.json({values:rows});
  if(u.includes('includeGridData'))return Response.json({sheets:[{data:[{rowData:[{values:template}]}]}]});
  if(u.endsWith(':batchUpdate')){const batch=JSON.parse(opts.body);batches.push(batch);if(throwBeforeCommit)throw Error('Network timeout');const cells=batch.requests[0].appendCells.rows[0].values;rows.push(cells.map(c=>String(c.userEnteredValue.stringValue??c.userEnteredValue.numberValue)));if(commitThenThrow)throw Error('Lost acknowledgement');return Response.json({replies:[{}]});}
  return Response.json({spreadsheetId:TRACKER_ID,sheets:[{properties:{title:'Applications',sheetId:1126513841,gridProperties:{rowCount:999}},tables:[]}]});};
 return {rows,batches,fetcher};
}
test('manual confirmation persists without a tracker connection and never claims acknowledgement',async()=>{
 const b=new Bucket(),r=await recordApplied(b,body,snapshot);assert.equal(r.application.status,'Application reported');assert.equal(r.application.employer_acknowledged,false);assert.equal(r.application.tracker_sync.status,'blocked');await recordApplied(b,body,snapshot);assert.equal((await manualApplications(b)).length,1);
 await assert.rejects(recordApplied(b,{...body,applied_date:'2099-01-01'},snapshot),/future/);await assert.rejects(recordApplied(b,{...body,confirmed:false},snapshot),/Confirm/);
});
test('existing application status is preserved and no duplicate is recorded',async()=>{
 const b=new Bucket(),existing={id:'history',company:job.company,role:job.title,status:'Rejected'};const r=await recordApplied(b,body,{...snapshot,applications:[existing]});assert.equal(r.replayed,true);assert.equal(r.application.status,'Rejected');assert.equal((await manualApplications(b)).length,0);
});
test('Sheets sync appends a validated complete row, strips old row links and verifies readback',async()=>{
 const b=new Bucket(),p=provider();await connectTracker(b,grant,p.fetcher);const r=await recordApplied(b,body,snapshot,p.fetcher);assert.equal(r.application.tracker_sync.status,'synced');assert.equal(p.rows.length,3);assert.equal(p.rows[2][5],'Application reported');assert.equal(p.rows[2][4],'');assert.equal(p.rows[1][9],'Preserve this note');
 const append=p.batches[0].requests[0].appendCells;assert.equal(append.sheetId,1126513841);assert.equal(append.rows[0].values[5].dataValidation.strict,true);assert.equal(append.rows[0].values[1].userEnteredFormat.textFormat.link,undefined);
 await syncTracker(b,r.application.id,p.fetcher);assert.equal(p.batches.length,1);assert.ok(!JSON.stringify(r).includes('fixture-refresh'));
});
test('lost Sheet acknowledgement is reconciled by marker without a second append',async()=>{
 const b=new Bucket(),p=provider({commitThenThrow:true});await connectTracker(b,grant,p.fetcher);const r=await recordApplied(b,body,snapshot,p.fetcher);assert.equal(r.application.tracker_sync.status,'uncertain');assert.equal((await syncTracker(b,r.application.id,p.fetcher)).status,'synced');assert.equal(p.batches.length,1);
});
test('an uncertain write with no matching row cannot blindly append again',async()=>{
 const b=new Bucket(),p=provider({throwBeforeCommit:true});await connectTracker(b,grant,p.fetcher);const r=await recordApplied(b,body,snapshot,p.fetcher);assert.equal((await syncTracker(b,r.application.id,p.fetcher)).status,'uncertain');assert.equal(p.batches.length,1);
});
test('saved manual applications reach owner state and suppress repeat job suggestions',async()=>{
 const b=new Bucket();await b.put('hunt/owner.json','{"id":"owner"}');await b.put('hunt/snapshot.json',JSON.stringify({snapshot:{...snapshot,facts:[],packages:[],sources:[],events:[]}}));await recordApplied(b,body,snapshot);
 const r=await handle(new Request('https://hunt.example/api/state',{headers:{'oai-authenticated-user-id':'owner'}}),{BUCKET:b,HUNT_PUBLIC_READ:'true'}),state=await r.json();assert.equal(state.applications.length,1);assert.equal(state.jobs[0].assessment.duplicate_applications.length,1);assert.equal(state.jobs[0].assessment.status,'Already applied');assert.equal(state.applications[0].applied,body.applied_date);
});
test('quick apply returns before Google sync and undo removes only owner marks',async()=>{
 const b=new Bucket(),fail=()=>{throw Error('must not contact Google during quick action')};
 const r=await recordApplied(b,{...body,defer_sync:true},snapshot,fail);assert.equal(r.applied,true);assert.equal((await manualApplications(b)).length,1);
 const undo=await recordApplied(b,{job_id:job.id,applied:false},snapshot,fail);assert.equal(undo.applied,false);assert.equal((await manualApplications(b)).length,0);assert.equal((await manualApplications(b,true)).length,1);
 await recordApplied(b,{...body,defer_sync:true},snapshot,fail);assert.equal((await manualApplications(b)).length,1);
});
test('undo clears only the exact HUNT-created Sheet row, preserving existing history',async()=>{
 const b=new Bucket(),p=provider();await connectTracker(b,grant,p.fetcher);const r=await recordApplied(b,body,snapshot,p.fetcher);
 await recordApplied(b,{job_id:job.id,applied:false},snapshot);
 let cleared=0;const fetcher=async(url,opts)=>{if(String(url).endsWith(':clear')){assert.match(decodeURIComponent(String(url)),/A3:J3:clear$/);p.rows[2]=[];cleared++;return Response.json({});}return p.fetcher(url,opts)};
 assert.equal((await syncTracker(b,r.application.id,fetcher)).status,'removed');assert.equal(cleared,1);assert.equal(p.rows[1][9],'Preserve this note');
});

test('real-form receipt is distinct from an email; fixtures cannot enter the real tracker',async()=>{
 const b=new Bucket(),p=provider();await connectTracker(b,grant,p.fetcher);const pack={id:'p',job_id:job.id,payload_hash:'h'};const input={job_id:job.id,package_id:'p',package_hash:'h',cv_sha256:'a'.repeat(64),receipt:{submitted:true,confirmation_id:'lever-confirmation',evidence_kind:'confirmation_page',evidence_url:job.url+'/thanks',confirmation_text:'Your application has been submitted'}};
 await assert.rejects(recordConfirmedApplication(b,{...input,receipt:{...input.receipt,fixture_only:true}},{...snapshot,packages:[pack]},p.fetcher),/production employer/);assert.equal((await manualApplications(b)).length,0);
 const result=await recordConfirmedApplication(b,input,{...snapshot,packages:[pack]},p.fetcher);assert.equal(result.application.employer_form_submitted_by_hunt,true);assert.equal(result.application.submission_receipt.email_verified,false);assert.equal(result.tracker_sync.status,'synced');assert.equal(p.rows[2][5],'Application acknowledged');assert.match(p.rows[2][6],/no email verified/);
 await recordConfirmedApplication(b,input,{...snapshot,packages:[pack]},p.fetcher);assert.equal(p.batches.length,1);
});
