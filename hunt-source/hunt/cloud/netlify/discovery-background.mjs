import {timingSafeEqual} from 'node:crypto';
import {environment} from '../../runtime/environment.mjs';
import {hostedDiscover} from '../../runtime/worker.mjs';
import {executeDiscoveryTask} from '../../runtime/discovery-tasks.mjs';
export default async function(request){
 const expected=process.env.HUNT_SERVICE_KEY||'',provided=request.headers.get('X-HUNT-Background-Key')||'';
 if(!expected||provided.length!==expected.length||!timingSafeEqual(Buffer.from(provided),Buffer.from(expected)))return;
 if(request.method!=='POST')return;
 const {id}=await request.json();await executeDiscoveryTask(await environment(),id,hostedDiscover);
}
export const config={background:true};
