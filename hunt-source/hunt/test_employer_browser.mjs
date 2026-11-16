import {test} from 'node:test';
import assert from 'node:assert/strict';
import {employerURL,requestAllowed,confirmationEvidence} from './employer_browser.mjs';
const url='https://jobs.lever.co/fixture/11111111-1111-1111-1111-111111111111';
test('browser restricts initial navigation to exact public ATS job identity',()=>{assert.equal(employerURL(url).hostname,'jobs.lever.co');for(const value of [url+'?next=https://evil.test','http://jobs.lever.co/x',url.replace('jobs.lever.co','jobs.lever.co.evil.test')])assert.throws(()=>employerURL(value));});
test('inspection cannot post answers; filling cannot submit the application',()=>{
 const origin='https://jobs.lever.co';assert.equal(requestAllowed(url,'GET','inspect',origin,'document'),true);assert.equal(requestAllowed(url+'/apply','POST','inspect',origin,'fetch'),false);assert.equal(requestAllowed(url+'/apply','POST','fill',origin,'fetch'),false);assert.equal(requestAllowed('https://uploads.lever.co/file','PUT','fill',origin,'fetch'),true);assert.equal(requestAllowed(url+'/apply','POST','submit',origin,'fetch'),true);assert.equal(requestAllowed('https://evil.test/file','POST','submit',origin,'fetch'),false);
});
test('normal hCaptcha assets and child frames can load without allowing external main-page navigation',()=>{
 const origin='https://jobs.lever.co';assert.equal(requestAllowed('https://js.hcaptcha.com/1/api.js','GET','inspect',origin,'script'),true);assert.equal(requestAllowed('https://newassets.hcaptcha.com/captcha/frame','GET','inspect',origin,'document',false),true);assert.equal(requestAllowed('https://newassets.hcaptcha.com/captcha/frame','GET','inspect',origin,'document',true),false);assert.equal(requestAllowed('https://hcaptcha.com.evil.test/x','GET','inspect',origin,'script'),false);
});
test('only positive employer confirmation is accepted as a receipt',()=>{const args={url:url+'/thanks',applicationURL:url,idempotencyKey:'fixture'};assert.equal(confirmationEvidence({...args,text:'Submit application'}),null);assert.equal(confirmationEvidence({...args,text:'Thanks for applying',url:'https://evil.test/thanks'}),null);assert.equal(confirmationEvidence({...args,text:'Your application has been submitted'}).submitted,true);});
