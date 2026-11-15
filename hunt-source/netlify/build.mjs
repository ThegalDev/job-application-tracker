import {readFile,writeFile,mkdir,copyFile} from 'node:fs/promises';
const root=new URL('./',import.meta.url),source=new URL('../hunt/',root);
await mkdir(new URL('runtime/',root),{recursive:true});
await mkdir(new URL('public/',root),{recursive:true});
const assets={};
for(const [path,name] of [['/','index.html'],['/app.js','app.js'],['/style.css','style.css']]){
  let text=await readFile(new URL('web/'+name,source),'utf8');
  text=text.replaceAll('● Private · on this computer','● Public · HUNT on Netlify').replaceAll('Opening your private workspace…','Opening HUNT…');
  assets[path]=text;await writeFile(new URL('public/'+name,root),text);
}
const profile=JSON.parse(await readFile(new URL('writing-profile.json',source),'utf8'));
const instructions=await readFile(new URL('drafting-instructions.txt',source),'utf8');
const notifications=(await readFile(new URL('cloud/notifications.mjs',source),'utf8')).replaceAll('export ','');
const notificationPrelude='const {notificationStatus,connectNotifications,notifyRun}=(()=>{'+notifications+';return {notificationStatus,connectNotifications,notifyRun};})();\n';
const visibility=(await readFile(new URL('cloud/visibility.mjs',source),'utf8')).replaceAll('export ','');
const visibilityPrelude='const {visibilitySettings,jobVisibility,updateVisibility}=(()=>{'+visibility+';return {visibilitySettings,jobVisibility,updateVisibility};})();\n';
const applications=(await readFile(new URL('cloud/applications.mjs',source),'utf8')).replaceAll('export ','');
const applicationPrelude='const {trackerStatus,connectTracker,manualApplications,recordApplied,syncTracker}=(()=>{'+applications+';return {trackerStatus,connectTracker,manualApplications,recordApplied,syncTracker};})();\n';
const server=(await readFile(new URL('cloud/server.mjs',source),'utf8')).replace("import {trackerStatus,connectTracker,manualApplications,recordApplied,syncTracker} from './applications.mjs';\n",'').replace("import {visibilitySettings,jobVisibility,updateVisibility} from './visibility.mjs';\n",'').replace("import {notificationStatus,connectNotifications,notifyRun} from './notifications.mjs';\n",'');
await writeFile(new URL('runtime/worker.mjs',root),applicationPrelude+visibilityPrelude+notificationPrelude+'const ASSETS='+JSON.stringify(assets)+';\nconst WRITING_PROFILE='+JSON.stringify(profile)+';\nconst DRAFTING_INSTRUCTIONS='+JSON.stringify(instructions)+';\n'+server);
console.log('Built Netlify assets and backend; no keys, CV files or local database bundled.');
