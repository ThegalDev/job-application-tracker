import {timingSafeEqual} from 'node:crypto';
import {environment} from '../../runtime/environment.mjs';
import {runNativeCVTask} from '../../runtime/worker.mjs';
export default async function(request){
 const expected=process.env.HUNT_SERVICE_KEY||'',provided=request.headers.get('X-HUNT-Background-Key')||'';
 if(!expected||provided.length!==expected.length||!timingSafeEqual(Buffer.from(provided),Buffer.from(expected))||request.method!=='POST')return;
 const {id}=await request.json();if(!/^[a-f0-9]{64}$/.test(id||''))return;
 await runNativeCVTask(await environment(),id);
}
export const config={background:true};
