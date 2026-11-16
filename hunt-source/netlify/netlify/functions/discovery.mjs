import {hostedDiscover} from '../../runtime/worker.mjs';
import {environment} from '../../runtime/environment.mjs';
export default async function(){
  const env=await environment();
  const slot=new Date().toISOString().slice(0,13);
  const result=await hostedDiscover(env,{idempotency_key:'netlify-scheduled-'+slot});
  return Response.json({id:result.id,status:result.status,sources_checked:result.sources_checked,sources_verified:result.sources_verified});
}
// UTC 06/11/17 corresponds to Lagos 07/12/18. No drafting or sending scheduled.
export const config={schedule:'0 6,11,17 * * *'};
