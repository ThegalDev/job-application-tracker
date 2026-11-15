import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
test('apply and immediate undo update in place without modal, navigation or full reload',async()=>{
 const button={dataset:{markApplied:'j'},setAttribute(){}};let release;const gate=new Promise(r=>release=r),calls=[];
 const context=vm.createContext({console,Date,Map,Promise,document:{querySelectorAll:()=>[button]}});
 const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8');vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+`\nstate={jobs:[{id:'j',company:'Acme',title:'HR',assessment:{duplicate_applications:[]}}],applications:[]};view='opportunities';globalThis.click=()=>toggleApplied('j');globalThis.inspect=()=>({view,applications:state.applications.length});globalThis.finish=()=>inlineQueues.get('application:j');`,context);
 context.stub=async(path,body)=>{calls.push([path,body]);if(calls.length===1)await gate;return path==='applications/applied'?(body.applied?{application:{id:'manual-a',...body}}:{application_id:'manual-a'}):{};};
 vm.runInContext('api=stub;notify=()=>{throw Error("Unexpected notice")};refresh=()=>{throw Error("Unexpected reload")}',context);
 context.click();assert.equal(button.textContent,'✓ Applied');assert.equal(context.inspect().view,'opportunities');context.click();assert.equal(button.textContent,'Mark as applied');assert.equal(context.inspect().applications,0);
 release();await context.finish();assert.deepEqual(calls.filter(x=>x[0]==='applications/applied').map(x=>x[1].applied),[true,false]);
});
