// One-time migration. Once the snapshot exists, no source-host request is made.
const SOURCE='https://hunt-aminat-career-workspace.youremowriter.chatgpt.site';
async function sourceJSON(path){
  const response=await fetch(SOURCE+path,{headers:{'User-Agent':'Mozilla/5.0 HUNT-Netlify-Migration'},redirect:'error',signal:AbortSignal.timeout(20000)});
  if(!response.ok)throw Error('Initial data migration unavailable ('+response.status+').');
  return response.json();
}
export async function bootstrap(bucket){
  if(await bucket.get('hunt/snapshot.json'))return;
  const snapshot=await sourceJSON('/api/state');
  for(const field of ['jobs','applications','facts','packages','sources','events'])if(!Array.isArray(snapshot[field]))throw Error('Incomplete migration snapshot.');
  if(snapshot.jobs.length>10000||snapshot.applications.length>5000)throw Error('Migration bounds exceeded.');
  const packages=[];
  for(const row of snapshot.packages){
    const full=await sourceJSON('/api/package?id='+encodeURIComponent(row.id));
    if(full.id!==row.id)throw Error('Migration package identity mismatch.');
    packages.push(full);
  }
  snapshot.packages=packages;
  delete snapshot.csrf;delete snapshot.public_view;delete snapshot.bridge;
  const put=async(key,value)=>{await bucket.put(key,JSON.stringify(value),{onlyIf:{etagDoesNotMatch:'*'}})};
  await put('hunt/owner.json',{id:'netlify-owner'});
  await put('hunt/runtime/runs.json',snapshot.cloud_runs||[]);
  await put('hunt/runtime/reports.json',[]);
  await put('hunt/control.json',{paused:snapshot.paused===true});
  await put('hunt/snapshot.json',{snapshot,stored_at:new Date().toISOString(),migration:{from:SOURCE,one_time:true}});
}
