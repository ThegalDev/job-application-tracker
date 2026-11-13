import base64
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from unittest.mock import patch
import hunt
import email_pipeline as ep
from google_provider import GoogleProvider

def encoded(text):return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')
def raw_message(ident='new',company='Serval',role='Emerging Talent Recruiter',body=None):
    body=body or f'Thank you for applying. We have decided to move forward with candidates whose experience more closely matches our needs. {role} at {company}.'
    return {'id':ident,'threadId':'thread','internalDate':str(int(dt.datetime(2026,11,12,8,tzinfo=ep.UTC).timestamp()*1000)),
            'payload':{'mimeType':'text/plain','headers':[{'name':'Subject','value':f'Thank you for applying to {company}'},
             {'name':'From','value':f'{company} Talent Team <no-reply@ashbyhq.com>'},
             {'name':'Authentication-Results','value':'mx.google.com; dkim=pass header.i=@ashbyhq.com; dmarc=pass header.from=ashbyhq.com'}],
             'body':{'data':encoded(body)}}}

class EmailPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.old=hunt.DATA,hunt.DB
        hunt.DATA=Path(self.temp.name);hunt.DB=hunt.DATA/'test.db';hunt.init()
        with hunt.db() as c:
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('email',hunt.dump('owner@example.test')))
            c.execute('INSERT OR REPLACE INTO kv VALUES(?,?)',('sheet_id',hunt.dump('sheet')))
            c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('a','Serval','Emerging Talent Recruiter','2026-11-05','Application acknowledged','2026-11-05','https://mail.google.com/#all/original','',2,'{}'))
    def tearDown(self):hunt.DATA,hunt.DB=self.old;self.temp.cleanup()
    def apps(self):
        with hunt.db() as c:return [dict(r) for r in c.execute('SELECT * FROM applications')]
    def normalized(self,**kw):return ep.normalize_message(hunt,raw_message(**kw),self.apps(),'owner@example.test')
    def status(self):
        with hunt.db() as c:return c.execute("SELECT status FROM applications WHERE id='a'").fetchone()[0]
    def test_realistic_decision_subject_does_not_turn_rejection_into_ack(self):
        message=self.normalized()
        self.assertTrue(message['association_verified'])
        self.assertEqual(ep.classify_message(message['body'])['status'],'Rejected')
        hunt.reconcile_messages([message]);self.assertEqual(self.status(),'Rejected')
    def test_employer_role_without_authenticated_sender_is_quarantined(self):
        raw=raw_message();raw['payload']['headers']=[x for x in raw['payload']['headers'] if x['name']!='Authentication-Results']
        m=ep.normalize_message(hunt,raw,self.apps(),'owner@example.test')
        self.assertFalse(m['association_verified']);hunt.reconcile_messages([m]);self.assertEqual(self.status(),'Application acknowledged')
    def test_multiple_roles_at_same_company_need_role_evidence(self):
        with hunt.db() as c:c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('b','Serval','People Partner','2026-11-05','Application acknowledged','2026-11-05','','',3,'{}'))
        m=self.normalized(body='Thank you for applying to Serval. We decided to move forward with other candidates.')
        self.assertFalse(m['association_verified'])
    def test_company_named_move_does_not_capture_other_employer_rejection(self):
        with hunt.db() as c:c.execute('INSERT INTO applications VALUES(?,?,?,?,?,?,?,?,?,?)',('move','Move','Senior Talent Partner','2026-10-12','Application acknowledged','2026-10-12','','',3,'{}'))
        message=self.normalized(body='Thank you for your interest. We have decided to move forward with candidates whose backgrounds match our priorities.')
        self.assertTrue(message['association_verified']);self.assertEqual(message['application_id'],'a')
    def test_html_only_and_plain_preference(self):
        part={'mimeType':'text/html','body':{'data':encoded('<p>We decided to move forward with other candidates.</p><script>ignored</script>')}}
        self.assertIn('other candidates',ep.mail_text(part));self.assertNotIn('ignored',ep.mail_text(part))
        alternative={'mimeType':'multipart/alternative','parts':[part,{'mimeType':'text/plain','body':{'data':encoded('Preferred plain')}}]}
        self.assertEqual(ep.mail_text(alternative),'Preferred plain')
    def test_text_attachments_are_excluded(self):
        self.assertEqual(ep.mail_text({'mimeType':'text/plain','filename':'private.txt','body':{'data':encoded('secret')}}),'')
    def test_previously_imported_ack_is_reclassified_then_deduplicated(self):
        with hunt.db() as c:c.execute('INSERT INTO mail_events VALUES(?,?,?,?,?,?,?)',('new','2026-11-12','Serval','Emerging Talent Recruiter','Application acknowledged','link','old classifier'))
        message=self.normalized();hunt.reconcile_messages([message]);self.assertEqual(self.status(),'Rejected')
        self.assertEqual(hunt.reconcile_messages([message])[0]['result'],'duplicate')
    def test_older_same_day_message_cannot_regress_newer_rejection(self):
        newer=self.normalized();hunt.reconcile_messages([newer])
        older={**newer,'id':'older','at':'2026-11-12T07:00:00+00:00','body':'We received your application.'}
        hunt.reconcile_messages([older]);self.assertEqual(self.status(),'Rejected')
    def test_stale_sheet_snapshot_cannot_erase_local_decision(self):
        hunt.reconcile_messages([self.normalized()])
        headers=['S/N','Company','Role','Applied / first email','Latest email','Current status','Response type','Follow-up priority','Email evidence','Notes']
        snapshot={'sheet_id':'sheet','email':'owner@example.test','verified_at':hunt.now(),'rows':[headers,['1','Serval','Emerging Talent Recruiter','2026-11-05','2026-11-05','Application acknowledged','','','https://mail.google.com/#all/original','changed note']]}
        hunt.sync_tracker_snapshot(snapshot);self.assertEqual(self.status(),'Rejected')
        hunt.sync_tracker_snapshot(snapshot);self.assertEqual(self.status(),'Rejected')
    def test_wrong_account_never_changes_application(self):
        message={**self.normalized(),'account':'other@example.test'}
        with self.assertRaisesRegex(ValueError,'account mismatch'):hunt.reconcile_messages([message])
        self.assertEqual(self.status(),'Application acknowledged')
    def test_quarantine_cannot_erase_previously_verified_event(self):
        message=self.normalized();hunt.reconcile_messages([message])
        untrusted={**message,'association_verified':False,'application_id':None,'company':'','role':''}
        hunt.reconcile_messages([untrusted])
        with hunt.db() as c:
            row=c.execute("SELECT * FROM recruiting_message_links WHERE message_id='new'").fetchone()
            self.assertEqual(row['association'],'applied');self.assertEqual(row['application_id'],'a')
    def test_raw_message_bodies_are_not_persisted(self):
        message=self.normalized(body='We decided to move forward with other candidates. Emerging Talent Recruiter at Serval. PRIVATE-AUDIT-SENTINEL')
        hunt.reconcile_messages([message])
        with hunt.db() as c:
            for table in ('mail_events','events','recruiting_message_links'):
                self.assertNotIn('PRIVATE-AUDIT-SENTINEL',str([tuple(r) for r in c.execute('SELECT * FROM '+table)]))
    def test_partial_scan_resumes_frozen_window_and_advances_only_when_complete(self):
        now=dt.datetime(2026,11,12,10,tzinfo=ep.UTC);state=ep.scan_state(hunt,self.apps(),now)
        self.assertLessEqual(state['after'],int(dt.datetime(2026,11,3,tzinfo=ep.UTC).timestamp()))
        ep.save_scan(hunt,state,{'complete':False,'next_page_token':'page-two'})
        resumed=ep.scan_state(hunt,self.apps(),now+dt.timedelta(days=1))
        self.assertEqual(resumed['page_token'],'page-two');self.assertEqual(resumed['before'],state['before'])
        ep.save_scan(hunt,resumed,{'complete':True})
        following=ep.scan_state(hunt,self.apps(),now+dt.timedelta(days=1))
        self.assertEqual(following['page_token'],None)
        self.assertEqual(following['after'],state['before']-2*86400)
    def test_actual_pipeline_route_preserves_decision_and_counts_repeat_as_duplicate(self):
        import services
        from orchestrator import ToolContext
        headers=['S/N','Company','Role','Applied / first email','Latest email','Current status','Response type','Follow-up priority','Email evidence','Notes']
        stale=[headers,['1','Serval','Emerging Talent Recruiter','2026-11-05','2026-11-05','Application acknowledged','','','https://mail.google.com/#all/original','']]
        engine=services.runtime(hunt);context=ToolContext('r','t','pipeline_intelligence','k',lambda:None,{})
        with patch('google_provider.GoogleProvider') as provider:
            provider.return_value.configured.return_value=True
            provider.return_value.tracker.return_value={'values':stale}
            provider.return_value.recruiting_messages_by_id.return_value={'messages':[raw_message()],'complete':True,'account':'owner@example.test','mode':'targeted_evidence_repair'}
            handler=engine.tools['reconcile_pipeline'].handler
            first=handler(context,{'repair_message_ids':['new']})
            second=handler(context,{'repair_message_ids':['new']})
        self.assertEqual(self.status(),'Rejected')
        self.assertEqual(first['events_imported'],1);self.assertEqual(second['events_imported'],0)
        self.assertEqual(second['events_already_recorded'],1)
        self.assertEqual(second['tracker']['newer_local_mail_preserved'],1)
        self.assertEqual(provider.return_value.tracker.call_count,2)
        provider.return_value.compare_and_swap_row.assert_not_called()

class GmailDiscoveryTests(unittest.TestCase):
    def test_body_query_epoch_window_and_page_continuation(self):
        provider=GoogleProvider('owner@example.test')
        with patch.object(provider,'profile'),patch.object(provider,'request',return_value={'messages':[],'nextPageToken':'third'}) as request:
            result=provider.recruiting_messages(100000,max_pages=1,page_token='second',before=200000,companies=['Serval'])
        query=parse_qs(urlsplit(request.call_args.args[0]).query)
        self.assertEqual(query['pageToken'],['second']);self.assertIn('after:100000',query['q'][0]);self.assertIn('before:200000',query['q'][0])
        self.assertIn('candidacy',query['q'][0]);self.assertIn('subject:"Serval"',query['q'][0]);self.assertFalse(result['complete'])
    def test_newsletter_metadata_is_filtered_before_body_read(self):
        provider=GoogleProvider('owner@example.test')
        metadata={'payload':{'headers':[{'name':'From','value':'newsletter@news.test'},{'name':'Subject','value':'Business news'}]}}
        with patch.object(provider,'profile'),patch.object(provider,'request',side_effect=[{'messages':[{'id':'m'}]},metadata]) as request:
            result=provider.recruiting_messages(100000,max_pages=1)
        self.assertEqual(request.call_count,2);self.assertEqual(result['messages'],[]);self.assertEqual(result['bulk_messages_skipped'],1)

if __name__=='__main__':unittest.main(verbosity=2)
