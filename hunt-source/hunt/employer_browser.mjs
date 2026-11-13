/** Production Lever application adapter. Public HTTPS forms only.
 * The JSON-line interface never invents answers or approves a plan. Inspect is
 * read-only; fill/submit require an exact payload supplied by the Python ledger.
 * No employer interaction was performed by writing this module.
 */
import readline from 'node:readline';
import {createHash} from 'node:crypto';
import {mkdir,chmod} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

export const LEVER_HOSTS=new Set(['jobs.lever.co','jobs.eu.lever.co']);
export function employerURL(value){
  const u=new URL(value);
  if(u.protocol!=='https:'||!LEVER_HOSTS.has(u.hostname)||u.username||u.password||u.port||u.search||u.hash||!/^\/[a-zA-Z0-9_-]+\/[a-f0-9-]{36}(?:\/apply)?\/?$/.test(u.pathname))throw new Error('An exact public Lever application URL is required');
  return u;
}
const ASSET_HOSTS=new Set([...LEVER_HOSTS,'hire.lever.co','cdn.lever.co','uploads.lever.co','api.lever.co','api.eu.lever.co','cdnjs.cloudflare.com','cdn.jsdelivr.net','fonts.googleapis.com','fonts.gstatic.com','www.google.com','www.gstatic.com','challenges.cloudflare.com']);
export function requestAllowed(target,method,stage,origin,resourceType){
  let u;try{u=new URL(target)}catch{return false}
  if(u.protocol!=='https:'||u.username||u.password||u.port||!ASSET_HOSTS.has(u.hostname))return false;
  if(['GET','HEAD'].includes(method))return u.origin===origin||resourceType!=='document';
  // Inspection never discloses application answers. File parsing/uploads can
  // happen during an already approved fill, but only to the ATS itself.
  return ['fill','submit'].includes(stage)&&['POST','PUT'].includes(method)&&[...LEVER_HOSTS,'uploads.lever.co','api.lever.co','api.eu.lever.co'].includes(u.hostname);
}
export function confirmationEvidence({text,url,applicationURL,idempotencyKey}){
  const target=employerURL(applicationURL),u=new URL(url);
  if(u.origin!==target.origin||!/(?:your application (?:has been|was) (?:successfully )?(?:submitted|received)|application submitted|thanks for applying|thank you for applying)/i.test(text))return null;
  return {submitted:true,confirmation_id:'lever-dom-'+createHash('sha256').update(applicationURL+'\n'+idempotencyKey+'\n'+text).digest('hex').slice(0,32),evidence_kind:'confirmation_page',evidence_url:u.href,confirmation_text:text.slice(0,2000),provider_reference:null,confirmation_basis:'Observed employer confirmation text; no ATS reference number was exposed.'};
}

async function main(){
 const initial=employerURL(process.argv[2]);
 const evidenceDir=path.resolve(process.argv[3]||'data/application-evidence');
 await mkdir(evidenceDir,{recursive:true,mode:0o700});await chmod(evidenceDir,0o700);
 let pw;
 if(process.env.HUNT_PLAYWRIGHT_MODULE)pw=await import(pathToFileURL(path.resolve(process.env.HUNT_PLAYWRIGHT_MODULE)).href);
 else try{pw=await import('playwright')}catch{throw new Error('Install Playwright and its Chromium browser, or set HUNT_PLAYWRIGHT_MODULE to the installed Playwright index.mjs')}
 const browser=await pw.chromium.launch({headless:true,...(process.env.HUNT_CHROME_EXECUTABLE?{executablePath:process.env.HUNT_CHROME_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update']});
 const context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false});
 let stage='inspect',loaded=false,observedForm=null;
 await context.route('**/*',route=>requestAllowed(route.request().url(),route.request().method(),stage,initial.origin,route.request().resourceType())?route.continue():route.abort('blockedbyclient'));
 const page=await context.newPage();page.setDefaultTimeout(12000);
 async function saveEvidence(prefix,ident){const safe=String(ident||'inspection').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,80)||'inspection';const file=path.join(evidenceDir,prefix+'-'+safe+'.png');await page.screenshot({path:file,fullPage:true});await chmod(file,0o600);return file}
 async function inspect(){
  stage='inspect';
  if(!loaded){await page.goto(initial.href,{waitUntil:'domcontentloaded',timeout:30000});loaded=true}
  const current=employerURL(page.url());if(current.origin!==initial.origin||current.pathname.replace(/\/apply\/?$/,'')!==initial.pathname.replace(/\/apply\/?$/,''))throw new Error('Employer navigation changed the selected job');
  if(!/\/apply\/?$/.test(current.pathname)){
   const apply=page.locator('a[href]').filter({hasText:/^Apply for this job$/i});
   if(await apply.count()!==1)throw new Error('A unique employer application link is not available');
   const href=new URL(await apply.getAttribute('href'),page.url());employerURL(href.href);
   if(href.origin!==initial.origin||href.pathname.replace(/\/apply\/?$/,'')!==initial.pathname.replace(/\/apply\/?$/,''))throw new Error('Application link points to a different job');
   await apply.click();await page.waitForLoadState('domcontentloaded');
  }
  observedForm=await page.evaluate(()=>{
   const forms=[...document.querySelectorAll('form')].filter(f=>f.querySelector('input[type="file"]')&&f.querySelector('input[name="email"]'));
   if(forms.length!==1)throw new Error('A unique Lever application form could not be inspected');
   const form=forms[0];
   const visible=e=>!!(e.getClientRects().length)&&getComputedStyle(e).visibility!=='hidden';
   const controls=[...form.querySelectorAll('input,textarea,select')].filter(e=>!['hidden','submit','button','reset'].includes(e.type)&&visible(e));
   const counts=new Map();for(const e of controls)counts.set(e.name,(counts.get(e.name)||0)+1);
   const seen=new Set(),questions=[];
   for(const e of controls){
    if(!e.name&&!e.id)throw new Error('An employer control has no stable identity');
    const group=e.closest('.application-question,.application-additional,.application-field,fieldset')||e.parentElement;
    const explicit=e.id?[...document.querySelectorAll('label')].find(l=>l.htmlFor===e.id):null;
    const title=group?.querySelector('.application-label,.application-question-label,legend,label');
    const label=(e.getAttribute('aria-label')||title?.innerText||explicit?.innerText||e.getAttribute('placeholder')||'').trim().replace(/\s+/g,' ');
    if(!label)throw new Error('An employer question has no readable label');
    if(e.type==='checkbox'&&counts.get(e.name)>1)throw new Error('Multiple-choice checkbox groups need an explicitly supported adapter');
    const key=e.type==='radio'?'name:'+e.name:e.id?'id:'+e.id:'name:'+e.name;
    if(seen.has(key))continue;seen.add(key);
    const type=e.tagName==='TEXTAREA'?'textarea':e.tagName==='SELECT'?'select':e.type;
    if(!['text','email','tel','url','textarea','select','radio','checkbox','file','date','number'].includes(type))throw new Error('Unsupported employer field type: '+type);
    const item={id:key,label,type:['date','number'].includes(type)?'text':type,input_type:type,required:e.required||e.getAttribute('aria-required')==='true'||/\*\s*$/.test(title?.innerText||'')};
    if(type==='select')item.options=[...e.options].filter(x=>!x.disabled&&x.value!=='').map(x=>x.value);
    if(type==='radio')item.options=controls.filter(x=>x.type==='radio'&&x.name===e.name).map(x=>x.value);
    questions.push(item);
   }
   const submit=[...form.querySelectorAll('button,input[type="submit"]')].filter(e=>e.type==='submit');
   if(submit.length!==1)throw new Error('A unique final submit control could not be inspected');
   const challenge=[...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],.g-recaptcha,.h-captcha')].some(visible);
   const securityFailure=/(?:security check (?:did not|failed to) load|verify you are human|complete the captcha|access denied)/i.test(form.innerText);
   return {url:location.href,action_url:form.action||location.href,questions,captcha:challenge||securityFailure,platform_restriction:false,provider:'lever',submit_label:(submit[0].innerText||submit[0].value||'Submit').trim()};
  });
  const action=new URL(observedForm.action_url);if(action.protocol!=='https:'||!LEVER_HOSTS.has(action.hostname))throw new Error('Form action is outside the selected ATS');
  await saveEvidence('inspected',createHash('sha256').update(observedForm.url).digest('hex').slice(0,20));
  return observedForm;
 }
 function control(id){if(id.startsWith('id:'))return page.locator('[id='+JSON.stringify(id.slice(3))+']');if(id.startsWith('name:'))return page.locator('[name='+JSON.stringify(id.slice(5))+']');throw new Error('Uninspected field identity')}
 async function fill(payload){
  if(!observedForm||payload.form.url!==observedForm.url||payload.form.provider!=='lever')throw new Error('Inspect this exact employer form before filling');
  stage='fill';
  for(const f of payload.form.questions){const loc=control(f.id);const answer=payload.answers[f.id];if(f.type==='file'){const upload=payload.uploads[f.id];if(upload)await loc.setInputFiles(upload.path)}else if(answer){if(f.type==='select')await loc.selectOption(answer.value);else if(f.type==='radio')await loc.filter({visible:true}).locator('xpath=.',{}).count()&&await page.locator('[name='+JSON.stringify(f.id.slice(5))+'][value='+JSON.stringify(answer.value)+']').check();else if(f.type==='checkbox')await loc.setChecked(answer.value);else await loc.fill(answer.value)}}
  const answers={};for(const [id,a] of Object.entries(payload.answers)){const loc=control(id);const field=payload.form.questions.find(f=>f.id===id);answers[id]=field.type==='radio'?await page.locator('[name='+JSON.stringify(id.slice(5))+']:checked').inputValue():typeof a.value==='boolean'?await loc.isChecked():await loc.inputValue()}
  const uploads={};for(const [id,file] of Object.entries(payload.uploads))uploads[id]=await control(id).evaluate(async e=>{if(!e.files?.length)return null;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',await e.files[0].arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('')});
  await saveEvidence('filled',payload.package_hash);return {answers,uploads};
 }
 async function submit(payload,ident){
  if(stage!=='fill')throw new Error('A filled and verified exact plan is required');
  const form=page.locator('form').filter({has:page.locator('input[name="email"]')});
  const button=form.locator('button[type="submit"],input[type="submit"]');
  if(await button.count()!==1||!await button.isEnabled())throw new Error('Employer submit control is unavailable or security-blocked');
  if(await page.locator('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"]').filter({visible:true}).count())throw new Error('Employer security challenge requires owner interaction');
  stage='submit';await saveEvidence('before-submit',ident);await button.click();
  const positive=page.getByText(/(?:your application (?:has been|was) (?:successfully )?(?:submitted|received)|application submitted|thanks for applying|thank you for applying)/i).first();await positive.waitFor({state:'visible',timeout:20000});
  const text=await positive.innerText();const result=confirmationEvidence({text,url:page.url(),applicationURL:payload.application_url,idempotencyKey:ident});
  if(!result)throw new Error('No positive employer confirmation was observed');
  result.screenshot=await saveEvidence('submitted',ident);return result;
 }
 const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 try{for await(const line of lines){try{const r=JSON.parse(line);if(r.command==='close')break;const result=r.command==='inspect'?await inspect():r.command==='fill'?await fill(r.payload):r.command==='submit'?await submit(r.payload,r.idempotency_key):(()=>{throw new Error('Unsupported browser command')})();process.stdout.write(JSON.stringify({ok:true,result})+'\n')}catch(error){process.stdout.write(JSON.stringify({ok:false,error_type:error.name,error:String(error.message).slice(0,300)})+'\n')}}}finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(error=>{process.stderr.write('HUNT browser runtime unavailable: '+error.message+'\n');process.exitCode=1});
