/** Production Lever application adapter. Public HTTPS forms only.
 * The JSON-line interface never invents answers or approves a plan. Inspect is
 * read-only; fill/submit require an exact payload supplied by the Python ledger.
 * No employer interaction was performed by writing this module.
 */
import readline from 'node:readline';
import {createHash} from 'node:crypto';
import {mkdir,chmod,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

export const LEVER_HOSTS=new Set(['jobs.lever.co','jobs.eu.lever.co']);
export function employerControl(page,id){
  if(id.startsWith('id:'))return page.locator('[id='+JSON.stringify(id.slice(3))+']');
  if(id.startsWith('name:')){
    const name='[name='+JSON.stringify(id.slice(5))+']';
    // Lever pairs consent checkboxes with hidden inputs of the same name.
    // Match the inspected visible control, retaining hidden resume inputs.
    return page.locator(name+':not([type="hidden"]):visible,'+name+'[type="file"]');
  }
  throw new Error('Uninspected field identity');
}
export function employerURL(value){
  const u=new URL(value);
  if(u.protocol!=='https:'||!LEVER_HOSTS.has(u.hostname)||u.username||u.password||u.port||u.search||u.hash||!/^\/[a-zA-Z0-9_-]+\/[a-f0-9-]{36}(?:\/apply)?\/?$/.test(u.pathname))throw new Error('An exact public Lever application URL is required');
  return u;
}
const ASSET_HOSTS=new Set([...LEVER_HOSTS,'hire.lever.co','cdn.lever.co','uploads.lever.co','api.lever.co','api.eu.lever.co','cdnjs.cloudflare.com','cdn.jsdelivr.net','fonts.googleapis.com','fonts.gstatic.com','www.google.com','www.gstatic.com','challenges.cloudflare.com']);
export function requestAllowed(target,method,stage,origin,resourceType,isMainFrame=true){
  let u;try{u=new URL(target)}catch{return false}
  const captchaHost=u.hostname==='hcaptcha.com'||u.hostname.endsWith('.hcaptcha.com');
  if(u.protocol!=='https:'||u.username||u.password||u.port||!ASSET_HOSTS.has(u.hostname)&&!captchaHost)return false;
  if(['GET','HEAD'].includes(method))return u.origin===origin||resourceType!=='document'||!isMainFrame&&(captchaHost||['www.google.com','challenges.cloudflare.com'].includes(u.hostname));
  if(captchaHost&&method==='POST')return true;
  if(u.origin===origin&&method==='POST'&&u.pathname.startsWith('/cdn-cgi/challenge-platform/'))return true;
  // Inspection never discloses application answers. File parsing/uploads can
  // happen during an already approved fill, but only to the ATS itself.
  if(!['POST','PUT'].includes(method))return false;
  if(stage==='fill')return u.hostname==='uploads.lever.co'||(u.origin===origin&&/\/(?:parseResume|resume|upload)(?:\/|$)/i.test(u.pathname));
  return stage==='submit'&&[...LEVER_HOSTS,'uploads.lever.co','api.lever.co','api.eu.lever.co'].includes(u.hostname);
}
export function confirmationEvidence({text,url,applicationURL,idempotencyKey}){
  const target=employerURL(applicationURL),u=new URL(url);
  if(u.origin!==target.origin||!/(?:your application (?:has been|was) (?:successfully )?(?:submitted|received)|application submitted|thanks for applying|thank you for applying)/i.test(text))return null;
  return {submitted:true,confirmation_id:'lever-dom-'+createHash('sha256').update(applicationURL+'\n'+idempotencyKey+'\n'+text).digest('hex').slice(0,32),evidence_kind:'confirmation_page',evidence_url:u.href,confirmation_text:text.slice(0,2000),provider_reference:null,confirmation_basis:'Observed employer confirmation text; no ATS reference number was exposed.'};
}

export function inspectLeverDocument(){
   const forms=[...document.querySelectorAll('form')].filter(f=>f.querySelector('input[type="file"]')&&f.querySelector('input[name="email"]'));
   if(forms.length!==1)throw new Error('A unique Lever application form could not be inspected');
   const form=forms[0];
   const visible=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!=='hidden'};
   const controls=[...form.querySelectorAll('input,textarea,select')].filter(e=>!['hidden','submit','button','reset'].includes(e.type)&&(visible(e)||e.type==='file'));
   const counts=new Map();for(const e of controls)counts.set(e.name,(counts.get(e.name)||0)+1);
   const seen=new Set(),questions=[];
   for(const e of controls){
    if(!e.name&&!e.id)throw new Error('An employer control has no stable identity');
    const group=e.closest('.application-question,fieldset')||e.closest('.application-additional')||e.closest('.application-field')||e.parentElement;
    const explicit=e.id?[...document.querySelectorAll('label')].find(l=>l.htmlFor===e.id):null;
    const title=group?.querySelector('.application-label,.application-question-label,legend,label');
    let label=(e.getAttribute('aria-label')||title?.textContent||explicit?.textContent||e.getAttribute('placeholder')||(e.type==='file'&&e.name==='resume'?'Resume/CV':'')).trim().replace(/\s+/g,' ');
    const standardLabels={resume:'Resume/CV',name:'Full name',email:'Email',phone:'Phone',location:'Current location',org:'Current company','urls[LinkedIn]':'LinkedIn URL','urls[Other]':'Other website',comments:'Additional information'};if(standardLabels[e.name])label=standardLabels[e.name];
    const optionalGroup=e.type==='checkbox'&&counts.get(e.name)>1&&!controls.some(x=>x.name===e.name&&(x.required||x.getAttribute('aria-required')==='true'));
    if(optionalGroup)continue;
    if(!label&&!e.required&&e.getAttribute('aria-required')!=='true'&&e.type!=='file')continue;
    if(!label&&e.type!=='file')throw new Error('An employer question has no readable label');
    if(e.type==='checkbox'&&counts.get(e.name)>1)throw new Error('Required multiple-choice checkbox groups need an explicitly supported adapter');
    const key=e.type==='radio'?'name:'+e.name:e.id?'id:'+e.id:'name:'+e.name;
    if(seen.has(key))continue;seen.add(key);
    const type=e.tagName==='TEXTAREA'?'textarea':e.tagName==='SELECT'?'select':e.type;
    if(!['text','email','tel','url','textarea','select','radio','checkbox','file','date','number'].includes(type))throw new Error('Unsupported employer field type: '+type);
    const item={id:key,label,type:['date','number'].includes(type)?'text':type,input_type:type,required:e.required||e.getAttribute('aria-required')==='true'||/[*✱]/.test(title?.textContent||'')};
    if(type==='select')item.options=[...e.options].filter(x=>!x.disabled&&x.value!=='').map(x=>x.value);
    if(type==='radio')item.options=controls.filter(x=>x.type==='radio'&&x.name===e.name).map(x=>x.value);
    questions.push(item);
   }
   const submit=[...form.querySelectorAll('button,input[type="submit"],input[type="button"]')].filter(e=>visible(e)&&(e.type==='submit'||/^(?:submit(?: application)?|apply(?: now)?|send application)$/i.test((e.textContent||e.value||'').trim())));
   if(submit.length!==1)throw new Error('A unique final submit control could not be inspected');
   const captchaSolved=[...document.querySelectorAll('textarea[name="h-captcha-response"],textarea[name="g-recaptcha-response"]')].some(e=>e.value?.trim());
   const challenge=!captchaSolved&&[...document.querySelectorAll('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],iframe[src*="challenges.cloudflare.com"],.g-recaptcha,.h-captcha')].some(visible);
   const securityFailure=/(?:security check (?:did not|failed to) load|verify you are human|complete the captcha|access denied)/i.test(form.innerText);
   return {url:location.href,action_url:form.action||location.href,questions,captcha:challenge||securityFailure,platform_restriction:false,provider:'lever',submit_control_id:submit[0].id?'id:'+submit[0].id:null,submit_label:(submit[0].textContent||submit[0].value||'Submit').trim()};
}

async function main(){
 const initial=employerURL(process.argv[2]);
 const evidenceDir=path.resolve(process.argv[3]||'data/application-evidence');
 await mkdir(evidenceDir,{recursive:true,mode:0o700});await chmod(evidenceDir,0o700);
 let pw;
 if(process.env.HUNT_PLAYWRIGHT_MODULE)pw=await import(pathToFileURL(path.resolve(process.env.HUNT_PLAYWRIGHT_MODULE)).href);
 else try{pw=await import('playwright')}catch{throw new Error('Install Playwright and its Chromium browser, or set HUNT_PLAYWRIGHT_MODULE to the installed Playwright index.mjs')}
 const browser=await pw.chromium.launch({headless:process.env.HUNT_BROWSER_VISIBLE!=='1',...(process.env.HUNT_CHROME_EXECUTABLE?{executablePath:process.env.HUNT_CHROME_EXECUTABLE}:{}),args:['--disable-background-networking','--disable-component-update']});
 const context=await browser.newContext({serviceWorkers:'block',acceptDownloads:false});
 let stage='inspect',loaded=false,observedForm=null,submissionJournal=null;
 const persistSubmission=()=>writeFile(path.join(evidenceDir,'submission-network.json'),JSON.stringify(submissionJournal),{mode:0o600});
 await context.route('**/*',async route=>{
  const request=route.request();let isMain=true;try{isMain=request.frame()===page.mainFrame()}catch{isMain=request.resourceType()==='document'}
  const allowed=requestAllowed(request.url(),request.method(),stage,initial.origin,request.resourceType(),isMain);
  if(!allowed&&['xhr','fetch'].includes(request.resourceType())){const url=new URL(request.url());await writeFile(path.join(evidenceDir,'blocked-fetch-request.json'),JSON.stringify({origin:url.origin,path:url.pathname,method:request.method()}),{mode:0o600});}
  if(!allowed&&stage==='fill'&&['POST','PUT','PATCH'].includes(request.method())){const url=new URL(request.url());await writeFile(path.join(evidenceDir,'blocked-fill-request.json'),JSON.stringify({origin:url.origin,path:url.pathname,method:request.method()}),{mode:0o600});}
  if(submissionJournal&&['POST','PUT','PATCH'].includes(request.method())){
   const url=new URL(request.url());submissionJournal.requests.push({at:new Date().toISOString(),origin:url.origin,path:(url.hostname==='hcaptcha.com'||url.hostname.endsWith('.hcaptcha.com'))?'/'+url.pathname.split('/').filter(Boolean)[0]:url.pathname.startsWith('/cdn-cgi/challenge-platform')?'/cdn-cgi/challenge-platform':url.pathname,method:request.method(),allowed});await persistSubmission();
  }
  return allowed?route.continue():route.abort('blockedbyclient');
 });
 const page=await context.newPage();page.setDefaultTimeout(12000);
 async function saveEvidence(prefix,ident){const safe=String(ident||'inspection').replace(/[^a-zA-Z0-9_-]/g,'').slice(0,80)||'inspection';const file=path.join(evidenceDir,prefix+'-'+safe+'.png');try{await page.screenshot({path:file,fullPage:true,animations:'disabled',timeout:10000});await chmod(file,0o600);return file}catch{return null}}
 async function inspect(){
  if(stage!=='fill')stage='inspect';
  if(!loaded){await page.goto(initial.href,{waitUntil:'commit',timeout:30000});await page.locator('input[name="email"],a[href$="/apply"]').first().waitFor({state:'attached',timeout:15000});await page.waitForLoadState('domcontentloaded',{timeout:15000});loaded=true}
  const current=employerURL(page.url());if(current.origin!==initial.origin||current.pathname.replace(/\/apply\/?$/,'')!==initial.pathname.replace(/\/apply\/?$/,''))throw new Error('Employer navigation changed the selected job');
  if(!/\/apply\/?$/.test(current.pathname)){
   const apply=page.locator('a[href]').filter({hasText:/^Apply for this job$/i});
   const count=await apply.count();if(!count)throw new Error('An employer application link is not available');
   const href=new URL(await apply.first().getAttribute('href'),page.url());employerURL(href.href);
   for(let i=1;i<count;i++)if(new URL(await apply.nth(i).getAttribute('href'),page.url()).href!==href.href)throw new Error('Employer application links disagree');
   if(href.origin!==initial.origin||href.pathname.replace(/\/apply\/?$/,'')!==initial.pathname.replace(/\/apply\/?$/,''))throw new Error('Application link points to a different job');
   await apply.first().click();await page.waitForLoadState('domcontentloaded');
  }
  const deny=page.getByRole('button',{name:/^Deny$/i});if(await deny.count()===1&&await deny.isVisible())await deny.click();
  observedForm=await page.evaluate(inspectLeverDocument);
  const action=new URL(observedForm.action_url);if(action.protocol!=='https:'||action.origin!==initial.origin)throw new Error('Form action is outside the selected ATS');
  await saveEvidence('inspected',createHash('sha256').update(observedForm.url).digest('hex').slice(0,20));
  return observedForm;
 }
 const control=id=>employerControl(page,id);
 async function fill(payload){
  if(!observedForm||payload.form.url!==observedForm.url||payload.form.provider!=='lever')throw new Error('Inspect this exact employer form before filling');
  stage='fill';
  for(const f of payload.form.questions){const loc=control(f.id);const answer=payload.answers[f.id];if(f.type==='file'){const upload=payload.uploads[f.id];if(upload){await loc.setInputFiles(upload.path);await page.waitForFunction(()=>{const file=document.querySelector('form input[name="resume"]');const group=file?.closest('.application-question')||file?.parentElement;const visibleText=group?.innerText||'';return /\bSuccess\b/i.test(visibleText)&&!/Analyzing resume/i.test(visibleText)},null,{timeout:30000})}}else if(answer){if(f.id==='id:location-input'){const selected=await resolveLocation(answer.value);if(selected.value!==answer.value)throw new Error('Location must be resolved before planning')}else if(f.type==='select')await loc.selectOption(answer.value);else if(f.type==='radio')await page.locator('[name='+JSON.stringify(f.id.slice(5))+'][value='+JSON.stringify(answer.value)+']').check();else if(f.type==='checkbox')await loc.setChecked(answer.value);else await loc.fill(answer.value)}else if(!f.required){if(f.type==='checkbox')await loc.setChecked(false);else if(f.type==='select'){if(await loc.locator('option[value=""]').count())await loc.selectOption('')}else if(['text','email','tel','url','textarea'].includes(f.type))await loc.fill('')}}
  const preview=await readPreview(payload);
  await saveEvidence('filled',payload.package_hash);return preview;
 }
 async function resolveLocation(value){
  const pieces=String(value).split(',').map(s=>s.trim());const city=pieces[0],country=pieces.at(-1);const countryCode=/^(?:Nigeria|NGA)$/i.test(country)?'NGA':country;
  if(pieces.length<2||!city||!countryCode)throw new Error('A verified city and country are required');
  const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');const expected=new RegExp('^'+escape(city)+',\\s*(?:'+escape(countryCode)+'|'+escape(country)+')$','i');
  const loc=page.locator('input[name="location"]');await loc.fill('');await loc.pressSequentially(city,{delay:50});
  const choice=page.locator('.dropdown-location').filter({hasText:expected});await choice.first().waitFor({state:'visible',timeout:15000});if(await choice.count()!==1)throw new Error('Location choice is ambiguous');await choice.click();await loc.blur();
  const selected=await loc.inputValue();if(!expected.test(selected))throw new Error('Selected location does not match the verified city and country');return {value:selected,verified_city:city,verified_country:country};
 }
 async function inspectLocation(value){const loc=page.locator('input[name="location"]');await loc.fill('');await loc.pressSequentially(value,{delay:50});await page.waitForFunction(()=>{const e=document.querySelector('input[name="location"]');const g=e?.closest('.application-question');return g&&(/Lagos|No location found/i.test(g.innerText)&&!/^Current location\s*$/i.test(g.innerText.trim()))},null,{timeout:10000}).catch(()=>{});return loc.evaluate(e=>({value:e.value,html:e.closest('.application-question')?.outerHTML.slice(0,7000),text:e.closest('.application-question')?.innerText}));}
 async function readiness(){return page.evaluate(()=>{const form=[...document.querySelectorAll('form')].find(f=>f.querySelector('input[name="email"]'));const file=form.querySelector('input[name="resume"]');const group=file?.closest('.application-question')||file?.parentElement;return {valid:form.checkValidity(),invalid:[...form.querySelectorAll('input,select,textarea')].filter(e=>!e.validity.valid).map(e=>({name:e.name,id:e.id,required:e.required,message:e.validationMessage})),resume_files:[...(file?.files||[])].map(f=>({name:f.name,size:f.size,type:f.type})),upload_success:/\bSuccess\b/i.test(group?.innerText||''),resume_state:group?.innerText.replace(/\s+/g,' ').trim().slice(0,500),form_method:form.method,form_enctype:form.enctype,encoded_resume:[...new FormData(form).entries()].filter(([name])=>/resume|upload|file/i.test(name)).map(([name,value])=>({name,file:typeof value!=='string',bytes:typeof value==='string'?value.length:value.size}))}})}
 async function readPreview(payload){
  const answers={};for(const [id,a] of Object.entries(payload.answers)){const loc=control(id);const field=payload.form.questions.find(f=>f.id===id);answers[id]=field.type==='radio'?await page.locator('[name='+JSON.stringify(id.slice(5))+']:checked').inputValue():typeof a.value==='boolean'?await loc.isChecked():await loc.inputValue()}
  const uploads={};for(const [id,file] of Object.entries(payload.uploads))uploads[id]=await control(id).evaluate(async e=>{if(!e.files?.length)return null;return [...new Uint8Array(await crypto.subtle.digest('SHA-256',await e.files[0].arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('')});
  return {answers,uploads};
 }
 function finalSubmitControl(){
  if(observedForm?.submit_control_id)return control(observedForm.submit_control_id);
  const escaped=(observedForm?.submit_label||'').replace(/[.*+?^${}()|[\]\\]/g,'\\$&');return page.getByRole('button',{name:new RegExp('^'+escaped+'$','i')});
 }
 async function submit(payload,ident){
  if(stage!=='fill')throw new Error('A filled and verified exact plan is required');
  const form=page.locator('form').filter({has:page.locator('input[name="email"]')});
  const button=finalSubmitControl();
  if(await button.count()!==1||!await button.isEnabled())throw new Error('Employer submit control is unavailable or security-blocked');
  if((await page.evaluate(inspectLeverDocument)).captcha)throw new Error('Employer security challenge requires owner interaction');
  const expected={answers:Object.fromEntries(Object.entries(payload.answers).map(([id,a])=>[id,a.value])),uploads:Object.fromEntries(Object.entries(payload.uploads).map(([id,u])=>[id,u.sha256]))};
  if(JSON.stringify(await readPreview(payload))!==JSON.stringify(expected))throw new Error('Filled form changed after review; submission blocked');
  const beforeURL=page.url();
  submissionJournal={plan_id:ident,created_at:new Date().toISOString(),click_completed:false,requests:[]};await persistSubmission();
  stage='submit';await saveEvidence('before-submit',ident);await button.click({noWaitAfter:true});submissionJournal.click_completed=true;await persistSubmission();
  const humanWait=Math.min(900000,Number(process.env.HUNT_HUMAN_WAIT_MS)||20000);let humanNotice=false;
  const monitor=process.env.HUNT_BROWSER_VISIBLE==='1'?setInterval(async()=>{try{if(!humanNotice&&(await page.evaluate(inspectLeverDocument)).captcha){humanNotice=true;await import('node:fs/promises').then(fs=>fs.writeFile(path.join(evidenceDir,'human-check-required.json'),JSON.stringify({url:page.url(),message:'Complete the employer security check in the visible browser. The submit button has already been clicked once; do not click it again.'}),{mode:0o600}));}}catch{}},1000):null;
  const positive=page.getByText(/(?:your application (?:has been|was) (?:successfully )?(?:submitted|received)|application submitted|thanks for applying|thank you for applying)/i).first();
  const rejected=page.getByText(/there was an error verifying your application/i).first();let outcome;try{outcome=await Promise.race([positive.waitFor({state:'visible',timeout:humanWait}).then(()=>({confirmed:true})),rejected.waitFor({state:'visible',timeout:humanWait}).then(async()=>({rejected:true,text:await rejected.innerText()}))])}finally{if(monitor)clearInterval(monitor)};
  if(outcome.rejected){submissionJournal.rejected=true;submissionJournal.server_message=outcome.text;await persistSubmission();return {submitted:false,rejected:true,verification_failed:true,evidence_url:page.url(),server_message:outcome.text,screenshot:await saveEvidence('employer-rejected',ident)}}
  if(page.url()===beforeURL&&await form.isVisible())throw new Error('Form remains visible; employer confirmation is not sufficiently distinct');
  const text=await positive.innerText();const result=confirmationEvidence({text,url:page.url(),applicationURL:payload.application_url,idempotencyKey:ident});
  if(!result)throw new Error('No positive employer confirmation was observed');
  result.screenshot=await saveEvidence('submitted',ident);return result;
 }
 const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 try{for await(const line of lines){try{const r=JSON.parse(line);if(r.command==='close')break;const result=r.command==='inspect'?await inspect():r.command==='fill'?await fill(r.payload):r.command==='resolve-location'?await resolveLocation(r.value):r.command==='inspect-location'?await inspectLocation(r.value):r.command==='readiness'?await readiness():r.command==='check-submit-ready'?await (async()=>{await finalSubmitControl().click({trial:true});return {ready:true,clicked:false,stage}})():r.command==='submit'?await submit(r.payload,r.idempotency_key):(()=>{throw new Error('Unsupported browser command')})();process.stdout.write(JSON.stringify({ok:true,result})+'\n')}catch(error){if(submissionJournal){submissionJournal.error=String(error.message).slice(0,1200);submissionJournal.url=page.url();await persistSubmission().catch(()=>{});}await saveEvidence(stage==='submit'?'submission-unconfirmed':'inspection-failed','current');process.stdout.write(JSON.stringify({ok:false,error_type:error.name,error:String(error.message).slice(0,300)})+'\n')}}}finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(error=>{process.stderr.write('HUNT browser runtime unavailable: '+error.message+'\n');process.exitCode=1});
