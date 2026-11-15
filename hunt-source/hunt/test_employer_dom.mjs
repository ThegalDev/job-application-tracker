// Controlled local HTML only: no employer navigation, no uploads, no submission.
import assert from 'node:assert/strict';
import {inspectLeverDocument} from './employer_browser.mjs';
const {chromium}=await import('/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 const context=await browser.newContext();await context.route('**/*',r=>r.abort());const page=await context.newPage();
 await page.setContent('<form action="https://jobs.lever.co/fixture/apply"><div class="application-question"><label for="name">Full name *</label><input id="name" name="name" required></div><div class="application-question"><label for="email">Email *</label><input id="email" name="email" type="email" required></div><div class="application-question"><label for="resume">Resume *</label><input id="resume" name="resume" type="file" style="display:none" required></div><div class="application-question"><label for="choice">Eligibility *</label><select id="choice" name="choice" required><option value="">Select</option><option value="yes">Yes</option><option value="no">No</option></select></div><button type="submit">Submit application</button></form>');
 const result=await page.evaluate(inspectLeverDocument);assert.equal(result.questions.length,4);assert.equal(result.questions.filter(q=>q.required).length,4);assert.equal(result.questions.find(q=>q.type==='file').id,'id:resume');assert.deepEqual(result.questions.find(q=>q.type==='select').options,['yes','no']);assert.equal(result.captcha,false);
 await page.evaluate(()=>{const node=document.createElement('div');node.className='g-recaptcha';node.textContent='Verify you are human';document.body.append(node)});assert.equal((await page.evaluate(inspectLeverDocument)).captcha,true);
 console.log('Controlled real-browser form extraction passed: hidden file input, labels, required fields, select choices, security challenge. No external requests or submissions.');
}finally{await browser.close()}
