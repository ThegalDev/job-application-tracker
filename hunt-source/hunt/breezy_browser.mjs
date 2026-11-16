/** Breezy adapter for the explicitly authorized single real application test. */
import readline from 'node:readline';
import {mkdir,writeFile,chmod} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {pathToFileURL} from 'node:url';

export function breezyURL(value){
 const u=new URL(value);
 if(u.protocol!=='https:'||!/^[-a-z0-9]+\.breezy\.hr$/.test(u.hostname)||u.hostname==='app.breezy.hr'||u.username||u.password||u.port||u.search||u.hash||!/^\/p\/[a-f0-9]{12}-[-a-z0-9]+(?:\/apply)?$/.test(u.pathname))throw new Error('An exact public Breezy position URL is required');
 return u;
}
export function requestAllowed(target,method,stage,initial){
 const u=new URL(target),job=breezyURL(initial);if(u.protocol!=='https:'||u.username||u.password||u.port)return false;
 if(['GET','HEAD','OPTIONS'].includes(method))return true;
 if(method!=='POST')return false;
 const company=job.hostname.split('.')[0],position=job.pathname.split('/')[2].split('-')[0];
 if(u.hostname==='app.breezy.hr'&&u.pathname===`/api/portal/${company}/upload`)return stage==='fill';
 return stage==='submit'&&['app.breezy.hr',job.hostname].includes(u.hostname)&&u.pathname===`/api/apply/${position}`;
}
export function inspectBreezyDocument({allowQuestionnaire=false}={}){
 const visible=e=>!!(e.getBoundingClientRect().width&&e.getBoundingClientRect().height)&&getComputedStyle(e).visibility!=='hidden';
 const form=document.querySelector('form[name="form"]');if(!form)throw new Error('A unique application form is required');
 const data=JSON.parse(document.querySelector('#portal-data')?.textContent||'{}');
 const raw=document.querySelector('#questions')?.value;const sections=raw?JSON.parse(raw):data.questions||[];
 if(sections.length&&!allowQuestionnaire)throw new Error('Custom Breezy questionnaires require explicit inspection support');
 const custom=new Map();for(const section of sections)for(const [i,q] of (section.questions||[]).entries())custom.set('section_'+section._id+'_question_'+i,q);
 const known={cName:'Full name',cEmail:'Email',cPhoneNumber:'Phone',cAddress:'Current location',smsConsent:'SMS consent',cSummary:'Experience Summary',cCoverLetter:'Cover Letter',cResume:'Resume/CV'};
 const questions=[],seen=new Set();
 for(const e of form.querySelectorAll('input,textarea,select')){
  if(e.type==='hidden'||e.id==='hp_7f2b'||!visible(e)&&e.type!=='file')continue;
  if(custom.has(e.name)){
   if(seen.has(e.name))continue;seen.add(e.name);const q=custom.get(e.name);
   const controls=[...form.querySelectorAll('input,textarea,select')].filter(x=>x.name===e.name);
   const options=(q.options||[]).map(x=>x.text);let id='name:'+e.name,type=e.tagName==='TEXTAREA'?'textarea':e.type,input_type=type;
   if(e.type==='checkbox'&&controls.length>1){id='group:'+e.name;type='select';input_type='single-selection-checkbox-group';if(options.length!==controls.length)throw new Error('Questionnaire options changed')}
   const item={id,label:q.text+(e.type==='checkbox'&&controls.length===1?' '+(options[0]||''):''),type,input_type,required:q.required===true};
   if(['select','radio'].includes(type))item.options=e.type==='radio'?controls.map(x=>x.value):options;
   questions.push(item);continue;
  }
  if(!known[e.name])throw new Error('Additional employer field requires review: '+(e.name||e.id||e.type));
  const id=e.id?'id:'+e.id:'name:'+e.name;
  questions.push({id,label:known[e.name],type:e.tagName==='TEXTAREA'?'textarea':e.type,required:e.required});
 }
 const captcha=[...document.querySelectorAll('script[src],iframe[src]')].some(e=>/captcha|challenges\.cloudflare/i.test(e.src))||/verify you are human|complete the captcha|access denied/i.test(document.body.innerText);
 return {url:location.href,action_url:location.href,provider:'breezy',questions,captcha,platform_restriction:false};
}
async function main(){
 const initial=breezyURL(process.argv[2]);const evidence=path.resolve(process.argv[3]);await mkdir(evidence,{recursive:true,mode:0o700});await chmod(evidence,0o700);
 const {chromium}=await import(pathToFileURL(process.env.HUNT_PLAYWRIGHT_MODULE).href);
 const browser=await chromium.launch({headless:process.env.HUNT_BROWSER_VISIBLE!=='1',executablePath:process.env.HUNT_CHROME_EXECUTABLE});const context=await browser.newContext({serviceWorkers:'block'});
 let stage='inspect',loaded=false,observed=null,uploadAccepted=false,journal=null;
 const persist=()=>writeFile(path.join(evidence,'submission-network.json'),JSON.stringify(journal),{mode:0o600});
 await context.route('**/*',async route=>{
  const r=route.request(),u=new URL(r.url());let allowed=requestAllowed(r.url(),r.method(),stage,initial.href);
  if(r.isNavigationRequest()&&r.frame()===page.mainFrame())allowed=allowed&&u.origin===initial.origin;
  if(journal&&r.method()==='POST'){journal.requests.push({origin:u.origin,path:u.pathname,allowed});await persist()}
  if(!allowed)await writeFile(path.join(evidence,'blocked-request.json'),JSON.stringify({origin:u.origin,path:u.pathname,method:r.method(),stage}),{mode:0o600});
  return allowed?route.continue():route.abort('blockedbyclient');
 });
 const page=await context.newPage();page.setDefaultTimeout(15000);
 const shot=async name=>{const file=path.join(evidence,name+'.png');await page.screenshot({path:file,fullPage:true,animations:'disabled'});await chmod(file,0o600);return file};
 const control=id=>page.locator(id.startsWith('id:')?'[id='+JSON.stringify(id.slice(3))+']':'[name='+JSON.stringify(id.slice(5))+']:not([type="hidden"])');
 async function inspect(){if(!loaded){await page.goto(initial.href,{waitUntil:'domcontentloaded',timeout:30000});await page.locator('input[name="cEmail"]').waitFor();loaded=true}if(page.url()!==initial.href)throw new Error('Employer position changed');observed=await page.evaluate(inspectBreezyDocument,{allowQuestionnaire:process.env.HUNT_BREEZY_QUESTIONNAIRE==='1'});return observed}
 async function preview(payload){
  const answers={};for(const [id,a] of Object.entries(payload.answers)){
   const f=payload.form.questions.find(x=>x.id===id);
   if(id.startsWith('group:')){const selected=await page.locator('[name='+JSON.stringify(id.slice(6))+'][type="checkbox"]').evaluateAll(es=>es.flatMap((e,i)=>e.checked?[i]:[]));if(selected.length!==1)throw new Error('Exactly one approved group choice must be selected');answers[id]=f.options[selected[0]]}
   else if(f.type==='radio')answers[id]=await page.locator('[name='+JSON.stringify(id.slice(5))+']:checked').inputValue();
   else answers[id]=typeof a.value==='boolean'?await control(id).isChecked():await control(id).inputValue();
  }
  const uploads={};for(const id of Object.keys(payload.uploads))uploads[id]=await control(id).evaluate(async e=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',await e.files[0].arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join(''));
  return {answers,uploads};
 }
 async function fill(payload){
  if(!observed||payload.form.url!==initial.href||payload.form.provider!=='breezy')throw new Error('Exact inspected form required');
  stage='fill';
  for(const [id,file] of Object.entries(payload.uploads)){
   const response=page.waitForResponse(r=>new URL(r.url()).pathname===`/api/portal/${initial.hostname.split('.')[0]}/upload`&&r.request().method()==='POST');
   await control(id).setInputFiles(file.path);const r=await response;const body=await r.json();uploadAccepted=r.ok()&&!!body.url;
   if(!uploadAccepted)throw new Error('CV upload was not accepted');
   await page.getByText(file.name,{exact:true}).waitFor({state:'visible',timeout:30000});
   // Resume parsing can invent end dates (including for a current position).
   // These optional structured entries are omitted through the normal UI;
   // the full source-verified CV remains attached without transcription.
   const remove=page.locator('form[name="form"]').getByText('Delete',{exact:true});
   for(let i=0;i<30&&await remove.count();i++)await remove.first().click();
   if(await remove.count())throw new Error('Parsed history could not be cleared for exact-CV application');
  }
  for(const f of payload.form.questions){if(f.type==='file')continue;const a=payload.answers[f.id];
   if(f.id.startsWith('group:')){const controls=page.locator('[name='+JSON.stringify(f.id.slice(6))+'][type="checkbox"]');for(let i=0;i<await controls.count();i++)await controls.nth(i).setChecked(false);if(a){const i=f.options.indexOf(a.value);if(i<0)throw new Error('Uninspected checkbox choice');await controls.nth(i).setChecked(true)}}
   else if(f.type==='radio'){if(a)await page.locator('[name='+JSON.stringify(f.id.slice(5))+'][type="radio"][value='+JSON.stringify(a.value)+']').check()}
   else if(f.type==='checkbox')await control(f.id).setChecked(a?.value===true);else await control(f.id).fill(a?.value||'');
  }
  await shot('filled');return preview(payload);
 }
 async function readiness(){const r=await page.evaluate(()=>{const form=document.querySelector('form[name="form"]');const file=form.querySelector('#main-attachment');return {valid:form.checkValidity(),invalid:[...form.querySelectorAll('input,textarea,select')].filter(e=>!e.validity.valid).map(e=>({name:e.name,message:e.validationMessage})),resume_files:[...(file?.files||[])].map(f=>({name:f.name,size:f.size,type:f.type}))}});return {...r,upload_success:uploadAccepted}}
 async function submit(payload,ident){
  if(stage!=='fill'||journal)throw new Error('A filled plan and unused submit state are required');
  if((await inspect()).captcha)throw new Error('CAPTCHA is present; no submission attempted');
  const expected={answers:Object.fromEntries(Object.entries(payload.answers).map(([k,a])=>[k,a.value])),uploads:Object.fromEntries(Object.entries(payload.uploads).map(([k,f])=>[k,f.sha256]))};
  if(JSON.stringify(await preview(payload))!==JSON.stringify(expected)||(await readiness()).valid!==true)throw new Error('Application changed or invalid');
  await shot('before-submit');journal={plan_id:ident,click_completed:false,requests:[]};await persist();stage='submit';
  await page.getByRole('button',{name:/^Submit Application$/i}).click({noWaitAfter:true});journal.click_completed=true;await persist();
  const positive=page.getByText('Your application has been submitted successfully. Good luck!',{exact:true});await positive.waitFor({state:'visible',timeout:30000});
  if(new URL(page.url()).origin!==initial.origin||await page.locator('input[name="cEmail"]').isVisible())throw new Error('Employer confirmation is not distinct');
  const confirmation_text=await positive.innerText();const screenshot=await shot('submitted');
  return {submitted:true,confirmation_id:'breezy-dom-'+createHash('sha256').update(initial.href+'\n'+ident+'\n'+confirmation_text).digest('hex').slice(0,32),evidence_kind:'confirmation_page',evidence_url:page.url(),confirmation_text,screenshot,confirmation_basis:'Observed positive employer confirmation after exactly one submit click; no employer reference number exposed.'};
 }
 const lines=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
 try{for await(const line of lines){const r=JSON.parse(line);if(r.command==='close')break;try{const result=r.command==='inspect'?await inspect():r.command==='fill'?await fill(r.payload):r.command==='readiness'?await readiness():r.command==='submit'?await submit(r.payload,r.idempotency_key):(()=>{throw new Error('Unsupported command')})();process.stdout.write(JSON.stringify({ok:true,result})+'\n')}catch(e){await shot('step-failed').catch(()=>{});process.stdout.write(JSON.stringify({ok:false,error_type:e.name,error:e.message.slice(0,700)})+'\n')}}}finally{await browser.close()}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href)main().catch(e=>{process.stderr.write(e.message+'\n');process.exitCode=1});
