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
const server=await readFile(new URL('cloud/server.mjs',source),'utf8');
await writeFile(new URL('runtime/worker.mjs',root),'const ASSETS='+JSON.stringify(assets)+';\nconst WRITING_PROFILE='+JSON.stringify(profile)+';\nconst DRAFTING_INSTRUCTIONS='+JSON.stringify(instructions)+';\n'+server);
console.log('Built Netlify assets and backend; no keys, CV files or local database bundled.');
