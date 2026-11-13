import {getStore} from '@netlify/blobs';
import {NetlifyBucket} from './storage.mjs';
import {bootstrap} from './bootstrap.mjs';
export async function environment(){
  const context=process.env.CONTEXT;
  const name=context==='deploy-preview'||context==='branch-deploy'?'hunt-preview-'+process.env.DEPLOY_ID:'hunt-production';
  const bucket=new NetlifyBucket(getStore({name,consistency:'strong'}));
  await bootstrap(bucket);
  return {BUCKET:bucket,HUNT_PUBLIC_READ:'true',HUNT_BRIDGE_SECRET:process.env.HUNT_SERVICE_KEY||'',OPENAI_API_KEY:process.env.OPENAI_API_KEY||''};
}
