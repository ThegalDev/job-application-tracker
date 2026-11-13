import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from orchestrator import Orchestrator, ToolSpec, RetryableError, ROLE_TOOLS, install

class OrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db';self.calls=[]
        with self.db() as c:c.execute('CREATE TABLE kv(key TEXT PRIMARY KEY,value TEXT)');c.execute("INSERT INTO kv VALUES('paused','false')")
    def tearDown(self):self.tmp.cleanup()
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path);c.row_factory=sqlite3.Row
        try:
            with c:yield c
        finally:c.close()
    def tool(self,ctx,payload):
        ctx.checkpoint();self.calls.append((ctx.role,ctx.idempotency_key));return {'status':'success','record_ids':['one']}
    def engine(self,tools=None):return Orchestrator(self.db,tools if tools is not None else {names[0]:self.tool for names in ROLE_TOOLS.values()})
    def test_six_roles_run_real_tools_once(self):
        o=self.engine();rid=o.enqueue();s=o.run(rid)
        self.assertEqual(s['status'],'success');self.assertEqual(len(self.calls),6);self.assertEqual(len(s['tool_calls']),6)
        o.run(rid);self.assertEqual(len(self.calls),6)
    def test_idempotent_enqueue(self):
        o=self.engine();rid=o.enqueue(idempotency_key='same')
        self.assertEqual(o.enqueue(idempotency_key='same'),rid)
        with self.assertRaises(ValueError):o.enqueue('discovery',idempotency_key='same')
    def test_missing_tool_blocks_only_dependents(self):
        o=self.engine({'reconcile_pipeline':self.tool});s=o.run(o.enqueue())
        self.assertEqual(s['status'],'blocked');self.assertEqual([x[0] for x in self.calls],['pipeline_intelligence'])
        self.assertEqual(next(t for t in s['tasks'] if t['role']=='match_intelligence')['status'],'queued')
    def test_connected_tool_resumes_workflow(self):
        o=self.engine({});rid=o.enqueue('discovery');o.run(rid)
        o=self.engine();s=o.resume(rid);self.assertEqual(s['status'],'success');self.assertEqual(len(self.calls),2)
    def test_dependencies_pass_results(self):
        def match(ctx,payload):
            self.assertEqual(ctx.dependencies['discovery']['record_ids'],['one']);return self.tool(ctx,payload)
        o=self.engine({'discover_jobs':self.tool,'match_jobs':match});self.assertEqual(o.run(o.enqueue('discovery'))['status'],'success')
    def test_no_outbound_capabilities(self):
        with self.assertRaises(ValueError):self.engine({'send_email':self.tool})
    def test_retry_is_bounded_and_action_id_stable(self):
        def flaky(ctx,payload):
            self.calls.append((ctx.role,ctx.idempotency_key));raise RetryableError('secret must not be logged')
        o=self.engine({'discover_jobs':flaky});s=o.run(o.enqueue('discovery'))
        self.assertEqual(len(self.calls),3);self.assertEqual(len({x[1] for x in self.calls}),1);self.assertEqual(s['status'],'blocked')
        with self.db() as c:self.assertNotIn('secret',str([dict(x) for x in c.execute('SELECT * FROM agent_events')]))
    def test_call_budget(self):
        o=self.engine();s=o.run(o.enqueue(max_calls=1));self.assertEqual(s['status'],'budget_exceeded');self.assertEqual(len(self.calls),1)
    def test_reserved_cost_budget(self):
        o=self.engine({'discover_jobs':ToolSpec(self.tool,cost_upper_bound_usd=.5)})
        s=o.run(o.enqueue('discovery',max_cost_usd=.1));self.assertEqual(s['status'],'budget_exceeded');self.assertEqual(self.calls,[])
    def test_pause_kills_before_next_role(self):
        def pause(ctx,payload):
            result=self.tool(ctx,payload)
            with self.db() as c:c.execute("UPDATE kv SET value='true' WHERE key='paused'")
            return result
        o=self.engine({'discover_jobs':pause,'match_jobs':self.tool});rid=o.enqueue('discovery');s=o.run(rid)
        self.assertEqual(s['status'],'paused');self.assertEqual(len(self.calls),1)
        with self.db() as c:c.execute("UPDATE kv SET value='false' WHERE key='paused'")
        self.assertEqual(o.resume(rid)['status'],'success');self.assertEqual(len(self.calls),2)
    def test_no_paid_retry_after_unknown_failure(self):
        def bad(ctx,payload):self.calls.append(ctx.idempotency_key);raise TimeoutError()
        o=self.engine({'prepare_applications':bad,'match_jobs':self.tool,'research_companies':self.tool,'prepare_outreach':self.tool})
        s=o.run(o.enqueue('shortlist'));self.assertEqual(s['status'],'blocked')
        task=next(t for t in s['tasks'] if t['role']=='application_studio');self.assertEqual(task['attempts'],1)
    def test_sensitive_payload_rejected_before_persistence(self):
        o=self.engine()
        with self.assertRaises(ValueError):o.enqueue('pipeline',{'password':'sentinel'})
        with self.db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM agent_workflows').fetchone()[0],0)
    def test_stolen_lease_keeps_new_owner_state(self):
        def takeover(ctx,payload):
            with self.db() as c:c.execute("UPDATE agent_workflows SET lease_owner='new-owner',lease_until='2999-01-01T00:00:00+00:00' WHERE id=?",(ctx.run_id,))
            return {'status':'success'}
        o=self.engine({'discover_jobs':takeover});rid=o.enqueue('discovery');s=o.run(rid)
        self.assertEqual(s['status'],'running')
        with self.db() as c:self.assertEqual(c.execute('SELECT lease_owner FROM agent_workflows').fetchone()[0],'new-owner')
        self.assertEqual(s['tasks'][0]['status'],'running')
    def test_sensitive_tool_results_are_rejected(self):
        o=self.engine({'discover_jobs':lambda c,p:{'status':'success','api_key':'credential'}})
        s=o.run(o.enqueue('discovery'));self.assertEqual(s['tasks'][0]['status'],'failed');self.assertIsNone(s['tasks'][0]['result'])
    def test_invalid_result_cannot_advance(self):
        o=self.engine({'discover_jobs':lambda c,p:{'sent':True}});s=o.run(o.enqueue('discovery'))
        self.assertEqual(s['tasks'][0]['status'],'failed');self.assertEqual(len(s['tool_calls']),1)
    def test_live_lease_cannot_be_stolen(self):
        o=self.engine();rid=o.enqueue()
        with self.db() as c:c.execute("UPDATE agent_workflows SET lease_until='2999-01-01T00:00:00+00:00',lease_owner='another' WHERE id=?",(rid,))
        with self.assertRaises(ValueError):o.run(rid)
    def test_stale_running_safe_task_restored(self):
        o=self.engine();rid=o.enqueue('discovery')
        with self.db() as c:c.execute("UPDATE agent_tasks SET status='running' WHERE run_id=? AND role='discovery'",(rid,))
        self.assertEqual(o.run(rid)['status'],'success')
    def test_stale_paid_task_requires_review(self):
        o=self.engine();rid=o.enqueue('shortlist')
        with self.db() as c:c.execute("UPDATE agent_tasks SET status='running' WHERE run_id=? AND role='application_studio'",(rid,))
        s=o.run(rid);self.assertEqual(next(t for t in s['tasks'] if t['role']=='application_studio')['status'],'uncertain')
        self.assertNotIn('application_studio',[x[0] for x in self.calls])

if __name__=='__main__':unittest.main()
