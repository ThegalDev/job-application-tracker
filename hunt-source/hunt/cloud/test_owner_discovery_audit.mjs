import assert from 'node:assert/strict';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
globalThis.crypto ??= webcrypto;
const app = await import('./server.mjs');
const role = (title, extra = {}) => ({id:title,title,company:'True Talent Solutions Partners',location:'Remote worldwide',remote:true,open:1,description:'Own hiring workflows. USD 4000 per month.',...extra});

test('WWR agency and university names cannot qualify unrelated job titles', async () => {
  const item = (company,title) => `<item><title>${company}: ${title}</title><link>https://weworkremotely.com/remote-jobs/${title.toLowerCase().replaceAll(' ','-')}</link><pubDate>${new Date().toUTCString()}</pubDate><description>Remote worldwide.</description></item>`;
  const rows = await app.normalizeBroadFeed({kind:'wwr'},'<rss><channel>'+item('True Talent Solutions Partners','Engineering Manager')+item('True Talent Solutions Partners','Senior Software Engineer')+item('University of the People','Adjunct Instructor')+item('True Talent Solutions Partners','Recruitment Partner')+'</channel></rss>');
  assert.deepEqual(rows.map(j=>j.title),['Recruitment Partner']);
});

test('saved irrelevant roles and explicit foreign-only regions are excluded on assessment', () => {
  for(const title of ['Engineering Manager','Senior Software Engineer','Founding Enterprise Account Executive']) {
    const a=app.assess(role(title),{facts:[]});
    assert.equal(a.tier,'D');assert.equal(a.role_relevant,false);assert.equal(a.status,'Excluded');
  }
  for(const location of ['European Union','Remote (Central & South America)']) assert.equal(app.assess(role('People Operations Partner',{location}),{facts:[]}).tier,'D');
  assert.equal(app.assess(role('Talent Acquisition Partner'),{facts:[]}).role_relevant,true);
});

test('scan reconciliation partitions every observed record once and preserves inspectable IDs', () => {
  const now=Date.now(),recent=new Date(now-3600000).toISOString();
  const rows=[role('Engineering Manager'),role('Recruiter',{id:'old',source_posted_at:new Date(now-72*3600000).toISOString()}),role('People Partner',{id:'research',source_posted_at:recent,description:'Own employee lifecycle.'}),role('HR Manager',{id:'unknown'}),role('Recruiting Lead',{id:'excluded',location:'US only'})];
  for(const j of rows)j.assessment=app.assess(j,{facts:[]});
  const funnel=app.discoveryFunnel(rows,new Set(rows.map(j=>j.id)),now);
  assert.equal(Object.values(funnel.record_breakdown).reduce((a,b)=>a+b,0),rows.length);
  assert.equal(funnel.record_breakdown.unrelated_role,1);assert.equal(funnel.record_breakdown.older_than_48_hours,1);
  assert.equal(funnel.record_breakdown.eligibility_or_pay_excluded,1);
  assert.equal(funnel.record_breakdown.needs_verification,2);
});

test('owner filters expose the whole scan while keeping unrelated saved roles out of leads', () => {
  const source=readFileSync(new URL('../web/app.js',import.meta.url),'utf8'),context=vm.createContext({});
  vm.runInContext(source.slice(0,source.indexOf("$('#close').onclick"))+'\nglobalThis.inspect=(v,f)=>{state=v;filter=f;return opportunities()};',context);
  const jobs=['Engineering Manager','Recruiter'].map((title,i)=>{const j=role(title,{id:'record-'+i,source_posted_at:new Date().toISOString(),within_discovery_window:true,global_remote:true,freshness:'within_48_hours'});j.assessment=app.assess(j,{facts:[]});return j});
  const state={hosted:true,jobs,cloud_runs:[{kind:'hosted_discovery',id:'scan',discovery_version:'current',started:new Date().toISOString(),sources_verified:1,sources_checked:1}],discovery_audit:{observed_job_ids:jobs.map(j=>j.id),...app.discoveryFunnel(jobs,new Set(jobs.map(j=>j.id)))}};
  const recent=context.inspect(state,'recent');assert.doesNotMatch(recent,/data-job="record-0"/);assert.match(recent,/data-job="record-1"/);
  const scan=context.inspect(state,'scan');assert.match(scan,/data-job="record-0"/);assert.match(scan,/data-job="record-1"/);assert.match(scan,/2 posting records/);assert.match(scan,/2 records in this filter/);assert.match(scan,/Unrelated job titles/);assert.match(scan,/Source checked/);assert.doesNotMatch(scan,/<small>Verified /);
});
