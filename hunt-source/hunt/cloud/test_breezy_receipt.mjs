import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {confirmedEmployerURL,recordConfirmedApplication} from './applications.mjs';
globalThis.crypto??=webcrypto;
const employer='https://fixture-company.breezy.hr/p/aaaaaaaaaaaa-recruiter';
const job={id:'j',company:'Fixture Company',title:'Recruiter',url:'https://startup.jobs/fixture-recruiter-123?utm_source=rss'};
const receipt={submitted:true,confirmation_id:'breezy-dom-fixture',evidence_kind:'confirmation_page',evidence_url:employer+'/apply/submitted',confirmation_text:'Your application has been submitted successfully. Good luck!'};
const body={job_id:'j',package_id:'p',package_hash:'hash',cv_sha256:'a'.repeat(64),receipt,application_resolution:{listing_url:job.url,company:job.company,role:job.title,verified_by:'owner_desktop_employer_board',employer_url:employer}};
test('Breezy receipts bind listing, employer identity and exact position',()=>{
 assert.equal(confirmedEmployerURL(job,body).href,employer);
 for(const mutation of [b=>b.application_resolution.listing_url='https://startup.jobs/different',b=>b.application_resolution.company='Other Company',b=>b.application_resolution.role='Engineer',b=>b.application_resolution.employer_url=employer.replace('fixture-company','evil'),b=>b.receipt.evidence_url=employer.replace('aaaaaaaaaaaa','bbbbbbbbbbbb')+'/apply/submitted',b=>b.receipt.evidence_url=employer+'/apply',b=>b.receipt.evidence_url=employer+'/apply/submitted?next=x',b=>b.application_resolution.verified_by='unverified']){const bad=structuredClone(body);mutation(bad);assert.throws(()=>confirmedEmployerURL(job,bad));}
 assert.throws(()=>confirmedEmployerURL(job,{...body,application_resolution:null}));
});
test('confirmed Breezy receipt records acknowledgement, retains resolution and does not fabricate email evidence',async()=>{
 const data=new Map(),bucket={get:async k=>data.has(k)?{json:async()=>JSON.parse(data.get(k))}:null,put:async(k,v)=>{data.set(k,v);return {etag:'1'}}};
 const snapshot={jobs:[job],packages:[{id:'p',job_id:'j',payload_hash:'hash'}]};
 const result=await recordConfirmedApplication(bucket,body,snapshot);assert.equal(result.application.status,'Application acknowledged');assert.equal(result.application.employer_form_submitted_by_hunt,true);assert.equal(result.application.submission_receipt.email_verified,false);assert.deepEqual(result.application.application_resolution,body.application_resolution);assert.equal(result.tracker_sync.status,'blocked');
 const repeat=await recordConfirmedApplication(bucket,body,snapshot);assert.equal(repeat.application.id,result.application.id);assert.equal(data.size,1);
 await assert.rejects(()=>recordConfirmedApplication(bucket,{...body,receipt:{...receipt,fixture_only:true}},snapshot),/Positive production/);
 await assert.rejects(()=>recordConfirmedApplication(bucket,{...body,receipt:{...receipt,confirmation_id:'different'}},snapshot),/different submission receipt/);
});
