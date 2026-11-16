import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');
function client(extra={}){const context=vm.createContext({crypto:webcrypto,AbortSignal,console,...extra});vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick")),context);return context;}
test('saved discovery result remains distinguishable from subsequent dashboard reload failure',async()=>{
 const notices=[],button={disabled:false,dataset:{}},context=client({button,document:{querySelectorAll:()=>[button]},record:(m,e)=>notices.push({m,e})});
 vm.runInContext("state={hosted:true};notify=(m,e)=>record(m,e);refresh=async()=>{throw Error('storage unavailable')};globalThis.run=()=>action(button,async()=>({status:'partial',message:'Discovery completed and saved.'}));",context);
 await context.run();assert.match(notices.at(-1).m,/Discovery completed and saved/);assert.match(notices.at(-1).m,/dashboard reload failed/);assert.equal(button.disabled,false);
});
test('only an explicitly rejected CSRF request is retried, using the same run identity',async()=>{
 const requests=[],context=client({fetch:async(url,options)=>{requests.push(options);return requests.length===1?Response.json({error:'Origin or CSRF denied',code:'CSRF_TOKEN_MISMATCH'},{status:403}):Response.json({queued:true})}});
 vm.runInContext("state={csrf:'old'};refresh=async()=>{state.csrf='new'};globalThis.run=()=>api('run',{trigger:'discovery'});",context);
 await context.run();assert.equal(requests.length,2);assert.equal(requests[0].body,requests[1].body);assert.equal(requests[1].headers['X-CSRF-Token'],'new');
});
test('background acknowledgement is followed until a saved completion, not called complete at 202',async()=>{
 const statuses=['queued','running','completed'],context=client({setTimeout:resolve=>resolve()});
 vm.runInContext("notify=()=>{};globalThis.statuses=['queued','running','completed'];api=async()=>({status:statuses.shift(),result:{status:'partial',message:'Saved completed scan'}});globalThis.run=()=>waitForDiscovery({background:true,run_id:'fixture-manual-run'});",context);
 const result=await context.run();assert.equal(result.message,'Saved completed scan');assert.equal(context.statuses.length,0);
});
