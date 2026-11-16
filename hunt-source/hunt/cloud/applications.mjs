// Owner-reported applications. Recording is distinct from employer submission.
export const TRACKER_ID='1H8Dgplggg8wkuNoK-lIVJ602AzQHjkXzpOVQ3ONgKeo';
const PREFIX='hunt/runtime/manual-applications/',CONNECTION='hunt/private/tracker-google.json';
const ACCOUNT='majekadegbeaminat85@gmail.com',SCOPE='https://www.googleapis.com/auth/spreadsheets';
const HEADERS=['S/N','Company','Role','Applied / first email','Latest email','Current status','Response type','Follow-up priority','Email evidence','Notes'];
const norm=s=>String(s||'').toLowerCase().replace(/&/g,' and ').replace(/\bops\b/g,'operations').replace(/[^a-z0-9]+/g,' ').trim();
const read=async(b,k)=>{const o=await b.get(k);return o?o.json():null};
const write=(b,k,v,o={})=>b.put(k,JSON.stringify(v),o);
async function google(connection,fetcher){
 const r=await fetcher('https://oauth2.googleapis.com/token',{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:connection.client_id,client_secret:connection.client_secret,refresh_token:connection.refresh_token,grant_type:'refresh_token'})});
 if(!r.ok)throw Error('Tracker authorization needs reconnection');const t=await r.json();if(!t.access_token)throw Error('Tracker authorization returned no token');
 return async(path,body)=>{const response=await fetcher('https://sheets.googleapis.com/v4/spreadsheets/'+TRACKER_ID+path,{method:body?'POST':'GET',redirect:'error',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer '+t.access_token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})});if(!response.ok)throw Object.assign(Error('Tracker request failed ('+response.status+')'),{http_status:response.status});return response.json()};
}
export async function trackerStatus(bucket){return {status:await read(bucket,CONNECTION)?'connected':'awaiting_sheet_authorization',spreadsheet_url:'https://docs.google.com/spreadsheets/d/'+TRACKER_ID+'/edit',sheet:'Applications'};}
export async function connectTracker(bucket,connection,fetcher=fetch){
 const allowed=new Set(['openid','email','https://www.googleapis.com/auth/userinfo.email',SCOPE]);
 if(connection.account!==ACCOUNT||!Array.isArray(connection.scopes)||!connection.scopes.includes(SCOPE)||connection.scopes.some(s=>!allowed.has(s)))throw Error('A dedicated Sheets connection for the owner account is required');
 for(const k of ['client_id','client_secret','refresh_token'])if(typeof connection[k]!=='string'||!connection[k]||connection[k].length>4096)throw Error('Incomplete tracker authorization');
 const refresh=await fetcher('https://oauth2.googleapis.com/token',{method:'POST',redirect:'error',signal:AbortSignal.timeout(10000),headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({client_id:connection.client_id,client_secret:connection.client_secret,refresh_token:connection.refresh_token,grant_type:'refresh_token'})});if(!refresh.ok)throw Error('Tracker authorization failed');const token=await refresh.json();
 const profile=await fetcher('https://openidconnect.googleapis.com/v1/userinfo',{redirect:'error',signal:AbortSignal.timeout(10000),headers:{Authorization:'Bearer '+token.access_token}});if(!profile.ok)throw Error('Tracker account could not be checked');const account=await profile.json();if(account.email!==ACCOUNT||account.email_verified!==true)throw Error('Tracker account does not match the owner');
 const api=await google(connection,fetcher),meta=await api('?fields=spreadsheetId,sheets(properties)');if(meta.spreadsheetId!==TRACKER_ID||!meta.sheets.some(s=>s.properties.title==='Applications'))throw Error('Authorized tracker tab was not found');
 await write(bucket,CONNECTION,Object.fromEntries(['account','scopes','client_id','client_secret','refresh_token'].map(k=>[k,connection[k]])));return trackerStatus(bucket);
}
export async function manualApplications(bucket,includeRemoved=false){const list=await bucket.list({prefix:PREFIX,limit:1000});if(list.truncated)throw Error('Application history needs pagination before continuing');const rows=await Promise.all((list.objects||[]).map(x=>read(bucket,x.key)));return rows.filter(row=>row&&(includeRemoved||!row.removed_at));}
async function appId(job){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(norm(job.company)+'|'+norm(job.title)));return 'manual-'+Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('').slice(0,32)}
export async function recordApplied(bucket,body,snapshot,fetcher=fetch){
 const job=snapshot.jobs.find(j=>j.id===body.job_id);if(!job)throw Error('Job not found');if(body.applied===false){const id=await appId(job),key=PREFIX+id+'.json',row=await read(bucket,key);if(!row)return {applied:false};await write(bucket,key,{...row,removed_at:new Date().toISOString(),tracker_sync:{...row.tracker_sync,status:'pending'}});return {applied:false,application_id:id};}if(body.confirmed!==true)throw Error('Confirm that you already submitted this application');
 const date=String(body.applied_date||''),today=new Date().toLocaleDateString('en-CA',{timeZone:'Africa/Lagos'});
 if(!/^20\d{2}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||new Date(date).toISOString().slice(0,10)!==date||date>today)throw Error('Choose a valid application date that is not in the future');
 const notes=String(body.notes||'').trim();if(notes.length>2000)throw Error('Application notes are too long');let evidence=null;if(body.evidence_url){const u=new URL(body.evidence_url);if(u.protocol!=='https:'||u.username||u.password||u.href.length>2000)throw Error('Evidence must be an HTTPS link');evidence=u.href;}
 const existing=snapshot.applications.find(a=>norm(a.company)===norm(job.company)&&norm(a.role)===norm(job.title));
 if(existing)return {application:existing,replayed:true,message:'This role is already in Applications. Its existing status was preserved.'};
 const id=await appId(job),key=PREFIX+id+'.json';let row=await read(bucket,key);
 if(row?.removed_at){row={...row,removed_at:null,tracker_sync:{status:'pending'}};await write(bucket,key,row);}
 if(!row){row={id,job_id:job.id,company:job.company,role:job.title,applied:date,status:'Application reported',latest:new Date().toISOString(),evidence,notes,posting_url:job.original_application_url||job.url,recorded_by:'owner',employer_acknowledged:false,employer_form_submitted_by_hunt:false,tracker_sync:{status:'pending'}};const saved=await write(bucket,key,row,{onlyIf:{etagDoesNotMatch:'*'}});if(!saved)row=await read(bucket,key);}
 if(body.defer_sync)return {application:row,applied:true};
 const sync=await syncTracker(bucket,id,fetcher);return {application:{...row,tracker_sync:sync},message:sync.status==='synced'?'Applied recorded in Applications and verified in your Google tracker.':'Applied recorded in Applications. Google tracker: '+(sync.reason||sync.status)};
}
export async function syncTracker(bucket,id,fetcher=fetch){
 if(!/^manual-[a-f0-9]{32}$/.test(id||''))throw Error('Unknown manual application');const key=PREFIX+id+'.json',row=await read(bucket,key);if(!row)throw Error('Application not found');if(row.tracker_sync?.status==='synced')return row.tracker_sync;
 const save=async sync=>{await write(bucket,key,{...row,tracker_sync:sync});return sync},connection=await read(bucket,CONNECTION);
 if(!connection)return save({status:'blocked',reason:'Connect Google tracker to sync this application'});
 const lockKey='hunt/private/tracker-write-lock.json',owner=crypto.randomUUID(),old=await bucket.get(lockKey),lease=old?await old.json():null;
 if(lease&&Date.parse(lease.expires_at)>Date.now())return save({status:'pending',reason:'Another tracker update is in progress; retry sync shortly'});
 const locked=await write(bucket,lockKey,{owner,expires_at:new Date(Date.now()+120000).toISOString()},{onlyIf:old?{etagMatches:old.etag}:{etagDoesNotMatch:'*'}});if(!locked)return save({status:'pending',reason:'Another tracker update is in progress; retry sync shortly'});
 let attempted=false;
 try{
  const api=await google(connection,fetcher),meta=await api('?fields=spreadsheetId,sheets(properties,tables)');const tab=meta.sheets.find(s=>s.properties.title==='Applications');if(meta.spreadsheetId!==TRACKER_ID||!tab)throw Error('Tracker identity changed');if(tab.tables?.length)throw Error('Tracker now contains a native table; its append mapping needs review');
  const limit=Math.min(tab.properties.gridProperties.rowCount,1000),range=encodeURIComponent("'Applications'!A1:J"+limit),data=await api('/values/'+range+'?valueRenderOption=FORMATTED_VALUE'),rows=data.values||[];
  if(JSON.stringify(rows[0])!==JSON.stringify(HEADERS))throw Error('Tracker columns changed; no row was written');if(rows.length>=limit)throw Error('Tracker read bound reached; no row was written');
  const marker='HUNT-ID:'+id,found=rows.findIndex((r,i)=>i>0&&(String(r[9]||'').includes(marker)||norm(r[1])===norm(row.company)&&norm(r[2])===norm(row.role)));
  if(row.removed_at){
   if(found<1)return save({status:'removed',verified_at:new Date().toISOString()});
   const observed=rows[found];if(!String(observed[9]||'').includes(marker)||observed[5]!=='Application reported')return save({status:'preserved',reason:'Existing employer history was preserved; only the HUNT checkmark was undone'});
   await api('/values/'+encodeURIComponent("'Applications'!A"+(found+1)+':J'+(found+1))+':clear',{});
   const checked=await api('/values/'+range+'?valueRenderOption=FORMATTED_VALUE');if((checked.values||[]).some(r=>String(r[9]||'').includes(marker)))throw Error('Tracker undo readback did not match');
   return save({status:'removed',verified_at:new Date().toISOString()});
  }
  if(found>0)return save({status:'synced',range:'Applications!A'+(found+1)+':J'+(found+1),existing:true,verified_at:new Date().toISOString()});
  if(['uncertain','sending'].includes(row.tracker_sync?.status))return save({status:'uncertain',reason:'Earlier write is unconfirmed; no duplicate append was attempted'});
  const sheetStatus=row.submission_receipt?'Application acknowledged':'Application reported';
  const probe=await api('?includeGridData=true&ranges='+encodeURIComponent("'Applications'!A2:J2")+'&fields=sheets(data(rowData(values(userEnteredFormat,dataValidation))))');
  const template=probe.sheets?.[0]?.data?.[0]?.rowData?.[0]?.values||[];
  for(const [index,value]of [[5,sheetStatus],[7,'Monitor']]){const rule=template[index]?.dataValidation;if(rule&&(rule.condition?.type!=='ONE_OF_LIST'||!rule.condition.values?.some(x=>x.userEnteredValue===value)))throw Error('Tracker dropdown changed; no row was written');}
  const serial=Math.max(0,...rows.slice(1).map(r=>Number(r[0])||0))+1,values=[serial,row.company,row.role,row.applied,'',sheetStatus,row.submission_receipt?'Employer form confirmation observed; no email verified':'Owner-reported submission; no employer reply verified','Monitor',row.evidence&&new URL(row.evidence).hostname==='mail.google.com'?row.evidence:'',marker+(row.submission_receipt?' | HUNT observed employer form confirmation; no email verified. Posting: ':' | Owner confirmed an application submitted outside HUNT. Employer acknowledgement not verified. Posting: ')+row.posting_url+(row.evidence?' | Evidence: '+row.evidence:'')+(row.notes?' | '+row.notes:'')];
  const cells=values.map((value,i)=>{const cell={userEnteredValue:typeof value==='number'?{numberValue:value}:{stringValue:String(value)}};if(template[i]?.userEnteredFormat){cell.userEnteredFormat=structuredClone(template[i].userEnteredFormat);if(cell.userEnteredFormat.textFormat)delete cell.userEnteredFormat.textFormat.link;}if(template[i]?.dataValidation)cell.dataValidation=template[i].dataValidation;return cell;});
  await save({status:'sending',started_at:new Date().toISOString()});attempted=true;
  await api(':batchUpdate',{requests:[{appendCells:{sheetId:tab.properties.sheetId,rows:[{values:cells}],fields:'userEnteredValue,userEnteredFormat,dataValidation'}}]});
  const verify=await api('/values/'+range+'?valueRenderOption=FORMATTED_VALUE'),index=(verify.values||[]).findIndex(r=>String(r[9]||'').includes(marker));
  if(index<1)throw Error('Tracker write readback was not found');const observed=verify.values[index];if(observed[1]!==row.company||observed[2]!==row.role||observed[3]!==row.applied||observed[5]!==sheetStatus)throw Error('Tracker write readback did not match');
  return save({status:'synced',range:'Applications!A'+(index+1)+':J'+(index+1),verified_at:new Date().toISOString()});
 }catch(error){const uncertain=attempted&&!(error.http_status>=400&&error.http_status<500);return save({status:uncertain?'uncertain':'failed',reason:uncertain?'Tracker write outcome is unconfirmed; retry checks for the existing row before any further write':'Tracker update was not accepted. Check the connection and tracker schema.'});}
 finally{const lock=await read(bucket,lockKey);if(lock?.owner===owner)await bucket.delete(lockKey);}
}
// Only an authenticated runner may attest the employer link resolved from a
// saved aggregator listing. Retain that provenance with the actual receipt.
export function confirmedEmployerURL(job,body){
 const listing=new URL(job.original_application_url||job.url);let original=listing;
 const resolution=body.application_resolution;
 if(resolution){
  if(listing.hostname!=='startup.jobs'||resolution.listing_url!==listing.href||resolution.company!==job.company||resolution.role!==job.title||resolution.verified_by!=='owner_desktop_employer_board')throw Error('Employer-link resolution does not match the saved listing');
  original=new URL(resolution.employer_url);
  if(original.hostname!==norm(job.company).replaceAll(' ','-')+'.breezy.hr')throw Error('Resolved employer does not match the selected company');
 }
 const evidence=new URL(body.receipt.evidence_url);
 if(original.protocol!=='https:'||original.username||original.password||original.port||evidence.origin!==original.origin||evidence.username||evidence.password||evidence.port)throw Error('Confirmation evidence is outside the selected employer provider');
 if(['jobs.lever.co','jobs.eu.lever.co'].includes(original.hostname))return original;
 if(!/^[-a-z0-9]+\.breezy\.hr$/.test(original.hostname)||original.hostname==='app.breezy.hr'||original.search||original.hash||!/^\/p\/[a-f0-9]{12}-[-a-z0-9]+(?:\/apply)?$/.test(original.pathname))throw Error('Unsupported employer confirmation provider');
 const position=original.pathname.replace(/\/apply$/,'');
 if(evidence.pathname!==position+'/apply/submitted'||evidence.search||evidence.hash)throw Error('Confirmation is for a different employer position');
 return original;
}
// Private desktop-observed receipt, distinct from an employer email.
export async function recordConfirmedApplication(bucket,body,snapshot,fetcher=fetch){
 const job=snapshot.jobs.find(j=>j.id===body.job_id),p=snapshot.packages.find(p=>p.id===body.package_id),r=body.receipt;
 if(!job||!p||p.job_id!==job.id||p.payload_hash!==body.package_hash)throw Error('Application receipt does not match the job and package');
 if(!r||r.fixture_only||r.submitted!==true||typeof r.confirmation_id!=='string'||r.confirmation_id.length>150||r.evidence_kind!=='confirmation_page'||typeof r.confirmation_text!=='string'||r.confirmation_text.length>2000||!/(?:application (?:has been|was) (?:successfully )?(?:submitted|received)|application submitted|thanks for applying|thank you for applying)/i.test(r.confirmation_text))throw Error('Positive production employer confirmation is required');
 const original=confirmedEmployerURL(job,body),evidence=new URL(r.evidence_url);
 const id=await appId(job),key=PREFIX+id+'.json',prior=await read(bucket,key);if(prior?.submission_receipt&&prior.submission_receipt.confirmation_id!==r.confirmation_id)throw Error('A different submission receipt already exists; reconcile before replacing it');
 const row={...prior,id,job_id:job.id,company:job.company,role:job.title,applied:prior?.applied||new Date().toLocaleDateString('en-CA',{timeZone:'Africa/Lagos'}),status:'Application acknowledged',latest:new Date().toISOString(),evidence:evidence.href,posting_url:original.href,recorded_by:'hunt_runner',employer_acknowledged:true,employer_form_submitted_by_hunt:true,removed_at:null,submission_receipt:{confirmation_id:r.confirmation_id,evidence_kind:r.evidence_kind,evidence_url:evidence.href,confirmation_text:r.confirmation_text,verification_mode:'owner_desktop_observed_confirmation',email_verified:false,package_id:p.id,package_hash:p.payload_hash,cv_sha256:body.cv_sha256},notes:'HUNT observed an employer form confirmation. This is not a verified employer email.',tracker_sync:prior?.tracker_sync||{status:'pending'}};
 if(body.application_resolution)row.application_resolution=body.application_resolution;
 await write(bucket,key,row);return {application:row,tracker_sync:await syncTracker(bucket,id,fetcher)};
}
