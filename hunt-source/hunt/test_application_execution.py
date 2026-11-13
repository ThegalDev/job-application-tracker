"""State-machine fixtures only: no browser, employer or network is exercised."""
import contextlib
import copy
import datetime as dt
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sqlite3
import tempfile
import unittest
from pathlib import Path

import application_execution as app


class FixtureAdapter:
    """In-memory test double, deliberately not a production browser adapter."""
    def __init__(self):
        self.submissions = 0
        self.fills = 0
        self.change = None
        self.preview_change = False
        self.no_receipt = False
        self.fail_submit = False
        self.on_fill = None

    def preflight(self, payload):
        pass

    def inspect(self, payload):
        form = copy.deepcopy(payload['form'])
        if self.change:
            self.change(form)
        return form

    def fill(self, payload):
        self.fills += 1
        if self.on_fill:
            self.on_fill()
        result = {'answers': {k: v['value'] for k, v in payload['answers'].items()},
                  'uploads': {k: v['sha256'] for k, v in payload['uploads'].items()}}
        if self.preview_change:
            result['answers']['name'] = 'Incorrect candidate'
        return result

    def submit(self, payload, idempotency_key):
        self.submissions += 1
        if self.fail_submit:
            raise TimeoutError('Unknown provider outcome')
        if self.no_receipt:
            return {'status': 200, 'clicked': True}
        return {'submitted': True, 'confirmation_id': 'fixture-'+idempotency_key,
                'evidence_kind': 'confirmation_page', 'evidence_url': 'https://employer.test/thanks',
                'confirmation_text': 'Fixture application received'}


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'private.sqlite'
        self.allowed = True
        self.checkpoints = 0
        @contextlib.contextmanager
        def db():
            c = sqlite3.connect(str(self.path))
            c.row_factory = sqlite3.Row
            try:
                with c:
                    yield c
            finally:
                c.close()
        self.db = db
        def checkpoint(payload):
            self.checkpoints += 1
            if not self.allowed:
                raise ValueError('Paused or current job/package/eligibility changed')
        self.engine = app.ApplicationExecution(db, checkpoint)
        self.form = {'url': 'https://employer.test/jobs/one', 'action_url': 'https://employer.test/apply',
                     'questions': [{'id': 'name', 'label': 'Full name', 'type': 'text', 'required': True},
                                   {'id': 'authorization', 'label': 'Can you work from Nigeria?', 'type': 'radio',
                                    'required': True, 'options': ['Yes', 'No']}]}
        self.answers = {'name': {'value': 'Fixture Candidate', 'source': 'verified_profile', 'verified': True},
                        'authorization': {'value': 'Yes', 'source': 'owner_answer', 'verified': True}}

    def tearDown(self):
        self.temp.cleanup()

    def plan(self, **changes):
        args = dict(job_id='job-one', job_version='job-v1', package_id='package-one', package_hash='package-v1',
                    form=self.form, answers=self.answers)
        args.update(changes)
        return self.engine.plan(**args)

    def approved(self, **changes):
        p = self.plan(**changes)
        return self.engine.approve(p['id'], p['payload_hash'], 'fixture-owner')

    def test_unknown_required_answer_pauses_without_guessing(self):
        answers = copy.deepcopy(self.answers)
        del answers['authorization']
        p = self.plan(answers=answers)
        self.assertEqual(p['status'], 'needs_input')
        self.assertEqual(p['payload']['unresolved_questions'][0]['question_id'], 'authorization')
        with self.assertRaises(ValueError):
            self.engine.approve(p['id'], p['payload_hash'], 'owner')

    def test_unverified_or_invalid_choice_never_enters_review(self):
        for answer in [{'value': 'Yes', 'source': 'model_guess', 'verified': True},
                       {'value': 'Maybe', 'source': 'owner_answer', 'verified': True}]:
            answers = copy.deepcopy(self.answers)
            answers['authorization'] = answer
            self.assertEqual(self.plan(answers=answers)['status'], 'needs_input')

    def test_exact_hash_approval_and_idempotent_plan(self):
        p = self.plan()
        self.assertEqual(self.plan()['id'], p['id'])
        with self.assertRaises(ValueError):
            self.engine.approve(p['id'], 'wrong-hash', 'owner')
        changed = copy.deepcopy(self.answers)
        changed['name']['value'] = 'Different Candidate'
        p2 = self.plan(answers=changed)
        self.assertNotEqual(p2['payload_hash'], p['payload_hash'])
        with self.assertRaises(ValueError):
            self.engine.approve(p2['id'], p['payload_hash'], 'owner')

    def test_no_adapter_is_honest_blocker_and_does_not_claim(self):
        p = self.approved()
        with self.assertRaisesRegex(RuntimeError, 'No real employer-form'):
            self.engine.execute(p['id'], None)
        self.assertEqual(self.engine.get(p['id'])['status'], 'approved')
        capability = app.browser_capability()
        self.assertFalse(capability['adapter_installed'])
        self.assertFalse(capability['can_submit'])
        self.assertFalse(capability['browser_binary_verified'])

    def test_paused_or_stale_checkpoint_prevents_external_work(self):
        p = self.approved()
        adapter = FixtureAdapter()
        self.allowed = False
        with self.assertRaises(ValueError):
            self.engine.execute(p['id'], adapter)
        self.assertEqual(adapter.fills, 0)
        self.assertEqual(adapter.submissions, 0)

    def test_changed_required_form_requires_new_review_before_fill(self):
        p = self.approved()
        adapter = FixtureAdapter()
        adapter.change = lambda form: form['questions'].append({'id': 'salary', 'label': 'Expected salary', 'type': 'text', 'required': True})
        self.assertEqual(self.engine.execute(p['id'], adapter)['status'], 'needs_review')
        self.assertEqual(adapter.fills, 0)
        self.assertEqual(adapter.submissions, 0)

    def test_captcha_or_platform_restriction_cannot_be_approved(self):
        form = copy.deepcopy(self.form)
        form['captcha'] = True
        p = self.plan(form=form)
        self.assertEqual(p['status'], 'blocked')
        with self.assertRaises(ValueError):
            self.engine.approve(p['id'], p['payload_hash'], 'owner')

    def test_preview_mismatch_never_submits(self):
        p = self.approved()
        adapter = FixtureAdapter()
        adapter.preview_change = True
        self.assertEqual(self.engine.execute(p['id'], adapter)['status'], 'needs_review')
        self.assertEqual(adapter.submissions, 0)

    def test_upload_content_is_bound_to_exact_plan(self):
        cv = Path(self.temp.name) / 'cv.pdf'
        cv.write_bytes(b'%PDF-fixture-version-one')
        form = copy.deepcopy(self.form)
        form['questions'].append({'id': 'resume', 'label': 'Resume', 'type': 'file', 'required': True})
        p = self.approved(form=form, uploads={'resume': str(cv)})
        cv.write_bytes(b'%PDF-fixture-replaced')
        adapter = FixtureAdapter()
        with self.assertRaisesRegex(ValueError, 'file changed'):
            self.engine.execute(p['id'], adapter)
        self.assertEqual(adapter.fills, 0)

    def test_click_or_http_success_is_not_submission_confirmation(self):
        p = self.approved()
        adapter = FixtureAdapter()
        adapter.no_receipt = True
        with self.assertRaisesRegex(RuntimeError, 'reconciliation'):
            self.engine.execute(p['id'], adapter)
        self.assertEqual(self.engine.get(p['id'])['status'], 'uncertain')
        with self.assertRaises(ValueError):
            self.engine.execute(p['id'], adapter)
        self.assertEqual(adapter.submissions, 1)

    def test_timeout_cannot_retry_and_changed_plan_cannot_duplicate(self):
        p = self.approved()
        adapter = FixtureAdapter()
        adapter.fail_submit = True
        with self.assertRaises(RuntimeError):
            self.engine.execute(p['id'], adapter)
        p2 = self.approved(package_hash='changed-package')
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            self.engine.execute(p2['id'], adapter)
        self.assertEqual(adapter.submissions, 1)

    def test_positive_receipt_persists_and_repeat_never_submits_twice(self):
        p = self.approved()
        adapter = FixtureAdapter()
        result = self.engine.execute(p['id'], adapter)
        self.assertEqual(result['status'], 'submitted')
        self.assertEqual(result['receipt']['evidence_kind'], 'confirmation_page')
        self.assertTrue(self.engine.execute(p['id'], adapter)['replayed'])
        self.assertEqual(adapter.submissions, 1)
        with self.db() as c:
            events = '\n'.join(row['details'] for row in c.execute('SELECT details FROM application_execution_events'))
        self.assertNotIn('Fixture Candidate', events)

    def test_approval_expires_and_existing_unapproved_plan_never_executes(self):
        p = self.plan()
        with self.assertRaises(ValueError):
            self.engine.execute(p['id'], FixtureAdapter())
        p = self.engine.approve(p['id'], p['payload_hash'], 'owner')
        with self.db() as c:
            c.execute('UPDATE application_execution_plans SET approval_expires=? WHERE id=?', ('2000-01-01T00:00:00+00:00', p['id']))
        with self.assertRaisesRegex(ValueError, 'expired'):
            self.engine.execute(p['id'], FixtureAdapter())


    def test_approval_change_during_fill_never_submits(self):
        p = self.approved()
        adapter = FixtureAdapter()
        def revoke():
            with self.db() as c:
                c.execute("UPDATE application_execution_plans SET status='rejected' WHERE id=?", (p['id'],))
        adapter.on_fill = revoke
        self.assertEqual(self.engine.execute(p['id'], adapter)['status'], 'needs_review')
        self.assertEqual(adapter.submissions, 0)

    def test_upload_changed_during_fill_never_submits(self):
        cv = Path(self.temp.name) / 'cv.pdf'
        cv.write_bytes(b'%PDF-fixture-one')
        form = copy.deepcopy(self.form)
        form['questions'].append({'id': 'resume', 'label': 'Resume', 'type': 'file', 'required': True})
        p = self.approved(form=form, uploads={'resume': str(cv)})
        adapter = FixtureAdapter()
        adapter.on_fill = lambda: cv.write_bytes(b'%PDF-fixture-changed-during-fill')
        self.assertEqual(self.engine.execute(p['id'], adapter)['status'], 'needs_review')
        self.assertEqual(adapter.submissions, 0)

    def test_fixture_adapter_cannot_open_employer_urls(self):
        with self.assertRaises(ValueError):
            app.LocalFixtureBrowserAdapter('https://employer.test/application')

    @unittest.skipUnless(os.environ.get('HUNT_RUN_BROWSER_FIXTURE') == '1', 'Actual isolated browser fixture is opt-in')
    def test_actual_local_browser_inspect_upload_submit_receipt(self):
        received = []
        class FixtureHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                body = b"""<!doctype html><html><body><form data-hunt-application method="post" action="/apply" enctype="multipart/form-data">
<label for="name">Full name</label><input id="name" name="name" required>
<label for="authorization">Can you work from Nigeria?</label><select id="authorization" name="authorization" required><option value="Yes">Yes</option><option value="No">No</option></select>
<label for="resume">Resume</label><input id="resume" name="resume" type="file" required>
<button type="submit">Submit application</button></form></body></html>"""
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(body)
            def do_POST(self):
                received.append(self.rfile.read(int(self.headers.get('Content-Length', '0'))))
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<html><body><p data-hunt-confirmation-id="FIXTURE-REAL-BROWSER-1">Your fixture application was received.</p></body></html>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        adapter = app.LocalFixtureBrowserAdapter('http://127.0.0.1:%s/application' % server.server_port)
        try:
            form = adapter.inspect()
            self.assertEqual(len(form['questions']), 3)
            self.assertEqual(form['questions'][1]['type'], 'select')
            cv = Path(self.temp.name) / 'cv.pdf'
            cv.write_bytes(b'%PDF-local-fixture-upload-verified')
            p = self.approved(form=form, uploads={'resume': str(cv)})
            result = self.engine.execute(p['id'], adapter)
            self.assertEqual(result['status'], 'submitted')
            self.assertEqual(result['receipt']['confirmation_id'], 'FIXTURE-REAL-BROWSER-1')
            self.assertTrue(result['receipt']['fixture_only'])
            self.assertEqual(len(received), 1)
            self.assertIn(b'%PDF-local-fixture-upload-verified', received[0])
            self.assertIn(b'Fixture Candidate', received[0])
            self.assertTrue(self.engine.execute(p['id'], adapter)['replayed'])
            self.assertEqual(len(received), 1)
        finally:
            adapter.close()
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
