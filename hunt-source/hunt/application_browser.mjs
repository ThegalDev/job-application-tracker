// Controlled loopback-fixture adapter only. This is deliberately not a claimed
// production employer integration. It launches a fresh, ephemeral browser.
import readline from 'node:readline';
const url=new URL(process.argv[2]);
if(url.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||url.username||url.password)throw new Error('Only a controlled local fixture URL is permitted');
const modulePath=process.env.HUNT_PLAYWRIGHT_MODULE||'/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs';
const {chromium}=await import(modulePath);
const browser=await chromium.launch({headless:true,executablePath:process.env.HUNT_CHROME_EXECUTABLE||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--disable-background-networking','--disable-component-update']});
const context=await browser.newContext({serviceWorkers:'block'});
await context.route('**/*',route=>{const target=new URL(route.request().url());return target.origin===url.origin?route.continue():route.abort('blockedbyclient')});
const page=await context.newPage();
page.setDefaultTimeout(5000);
let loaded=false;
async function inspect(){
 if(!loaded){await page.goto(url.href,{waitUntil:'domcontentloaded',timeout:10000});loaded=true}
 if(new URL(page.url()).origin!==url.origin)throw new Error('Unexpected application origin');
 return page.evaluate(()=>{
  const form=document.querySelector('form[data-hunt-application]');if(!form)throw new Error('Controlled fixture form missing');
  const questions=[...form.querySelectorAll('input,textarea,select')].filter(e=>!['hidden','submit','button'].includes(e.type)).map(e=>({id:e.name,label:document.querySelector('label[for="'+CSS.escape(e.id)+'"]')?.textContent.trim()||e.getAttribute('aria-label')||'',type:e.tagName==='TEXTAREA'?'textarea':e.tagName==='SELECT'?'select':e.type,required:e.required,...(e.tagName==='SELECT'?{options:[...e.options].map(o=>o.value)}:{})}));
  return {url:location.href,action_url:form.action,questions,fixture_only:true,captcha:!!document.querySelector('[data-hunt-captcha],iframe[src*="captcha"],.g-recaptcha'),platform_restriction:!!document.querySelector('[data-hunt-platform-restriction]')};
 });
}
async function fill(payload){
 if(!loaded)throw new Error('Inspect the exact form before filling');
 for(const field of payload.form.questions){const loc=page.locator('[name='+JSON.stringify(field.id)+']');if(field.type==='file'){const file=payload.uploads[field.id];if(file)await loc.setInputFiles(file.path)}else if(payload.answers[field.id]){const value=payload.answers[field.id].value;if(field.type==='select')await loc.selectOption(value);else if(field.type==='checkbox')await loc.setChecked(value);else if(field.type==='radio')throw new Error('Radio groups require a separate supported employer adapter');else await loc.fill(value)}}
 const answers={};for(const [id,answer] of Object.entries(payload.answers)){const loc=page.locator('[name='+JSON.stringify(id)+']');answers[id]=typeof answer.value==='boolean'?await loc.isChecked():await loc.inputValue()}
 const uploads={};for(const [id,file] of Object.entries(payload.uploads)){const observed=await page.locator('[name='+JSON.stringify(id)+']').evaluate(async e=>{if(!e.files?.length)return null;const f=e.files[0],hash=await crypto.subtle.digest('SHA-256',await f.arrayBuffer());return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('')});uploads[id]=observed}
 return {answers,uploads};
}
async function submit(payload,ident){
 const buttons=page.locator('form[data-hunt-application] button[type=submit]');if(await buttons.count()!==1)throw new Error('Submission control is ambiguous');
 await buttons.click();const confirmation=page.locator('[data-hunt-confirmation-id]');await confirmation.waitFor({state:'visible'});
 return {submitted:true,confirmation_id:await confirmation.getAttribute('data-hunt-confirmation-id'),evidence_kind:'confirmation_page',evidence_url:page.url(),confirmation_text:await confirmation.innerText(),fixture_only:true};
}
const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
try{for await(const line of lines){let result;try{const request=JSON.parse(line);if(request.command==='close')break;result=request.command==='inspect'?await inspect():request.command==='fill'?await fill(request.payload):request.command==='submit'?await submit(request.payload,request.idempotency_key):(()=>{throw new Error('Unknown fixture command')})();process.stdout.write(JSON.stringify({ok:true,result})+'\n')}catch(error){process.stdout.write(JSON.stringify({ok:false,error_type:error.name,error:'Controlled browser step failed; no automatic retry'})+'\n')}}}finally{await browser.close()}
