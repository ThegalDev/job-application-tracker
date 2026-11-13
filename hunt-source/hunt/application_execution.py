"""Exact-approval application execution ledger.

This module executes an injected, real application adapter; it does not pretend
that a browser is installed or that filling a form confirms submission. No
network/browser capability is provided by the state machine itself. Persisted
plans contain private application answers and must use the private HUNT DB.
"""
import datetime as dt
import hashlib
import importlib.util
import json
import subprocess
import shutil
from pathlib import Path
from urllib.parse import urlsplit

UTC = dt.timezone.utc
ANSWER_SOURCES = frozenset(('verified_profile', 'owner_answer', 'approved_package'))
FIELD_TYPES = frozenset(('text', 'textarea', 'email', 'tel', 'url', 'select', 'radio', 'checkbox', 'file'))


def stamp():
    return dt.datetime.now(UTC).isoformat()


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encode(value).encode('utf-8')).hexdigest()


def browser_capability():
    """A diagnostic, never evidence that any browser job has run."""
    available = importlib.util.find_spec('playwright') is not None
    return {'adapter_installed': False, 'python_playwright_installed': available,
            'can_submit': False,
            'blockers': ['No production employer-form adapter is connected.'] +
                        ([] if available else ['The Python Playwright package is not installed.']),
            'browser_binary_verified': False}


def https_url(value):
    try:
        parsed = urlsplit(value)
        return parsed.scheme == 'https' and bool(parsed.hostname) and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def permitted_url(value, fixture_only=False):
    if https_url(value):
        return True
    try:
        parsed = urlsplit(value)
        return fixture_only is True and parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1') and not parsed.username and not parsed.password
    except (TypeError, ValueError):
        return False


def form_version(form):
    if not isinstance(form, dict) or not permitted_url(form.get('url'), form.get('fixture_only')) or not permitted_url(form.get('action_url'), form.get('fixture_only')):
        raise ValueError('Verified HTTPS form and action URLs are required')
    fields = form.get('questions')
    if not isinstance(fields, list) or len(fields) > 150:
        raise ValueError('A bounded inspected form schema is required')
    seen = set()
    for field in fields:
        if not isinstance(field, dict) or not isinstance(field.get('id'), str) or not field['id'] or field['id'] in seen:
            raise ValueError('Every inspected question needs a unique identity')
        seen.add(field['id'])
        if field.get('type') not in FIELD_TYPES or not isinstance(field.get('label'), str):
            raise ValueError('Unsupported or unidentified employer question')
        if field.get('type') in ('select', 'radio') and not isinstance(field.get('options'), list):
            raise ValueError('Choice question options must be inspected')
    return fingerprint(form)


def upload_record(question_id, filename):
    path = Path(filename).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in ('.pdf', '.docx'):
        raise ValueError('Application uploads must be explicit PDF or DOCX files')
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('Application upload exceeds the 10 MB bound')
    return {'question_id': question_id, 'path': str(path), 'name': path.name,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'size': path.stat().st_size}


def unresolved_questions(form, answers, uploads):
    questions = {x['id']: x for x in form['questions']}
    if set(answers) - set(questions) or set(uploads) - set(questions):
        raise ValueError('Answers or uploads refer to questions outside the inspected form')
    issues = []
    for ident, field in questions.items():
        if field['type'] == 'file':
            if field.get('required') and ident not in uploads:
                issues.append({'question_id': ident, 'reason': 'Required file has not been selected'})
            continue
        answer = answers.get(ident)
        if answer is None:
            if field.get('required'):
                issues.append({'question_id': ident, 'reason': 'Required question needs a verified answer'})
            continue
        if not isinstance(answer, dict) or answer.get('source') not in ANSWER_SOURCES or answer.get('verified') is not True:
            issues.append({'question_id': ident, 'reason': 'Answer requires owner or verified profile evidence'})
            continue
        value = answer.get('value')
        if value is None or value == '' or (field.get('required') and field['type'] == 'checkbox' and value is not True):
            issues.append({'question_id': ident, 'reason': 'Required answer or consent is incomplete'})
        elif field['type'] in ('select', 'radio') and value not in field['options']:
            issues.append({'question_id': ident, 'reason': 'Answer is outside the inspected choices'})
        elif field['type'] == 'checkbox' and not isinstance(value, bool):
            issues.append({'question_id': ident, 'reason': 'Checkbox needs an explicit boolean answer'})
        elif field['type'] != 'checkbox' and not isinstance(value, str):
            issues.append({'question_id': ident, 'reason': 'Question requires an explicit text answer'})
    return issues


def install(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS application_execution_plans(
      id TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT UNIQUE NOT NULL,
      job_id TEXT NOT NULL,status TEXT NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL,
      approved_by TEXT,approved_at TEXT,approval_expires TEXT,receipt TEXT,error TEXT);
    CREATE TABLE IF NOT EXISTS application_execution_events(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,plan_id TEXT NOT NULL,at TEXT NOT NULL,
      kind TEXT NOT NULL,details TEXT NOT NULL);
    ''')


class ApplicationExecution:
    """checkpoint(plan) must re-read pause, live job/package versions, salary,
    Nigeria eligibility and canonical duplicate applications across providers.

    adapter.inspect(plan) returns the current form schema. adapter.fill(plan)
    returns a preview {answers: {question_id: value}, uploads: {question_id: sha256}}.
    adapter.submit(plan, idempotency_key) returns positive confirmation evidence;
    a click, a 200 response, or an absent exception is never sufficient.
    """
    def __init__(self, db_factory, checkpoint):
        if not callable(checkpoint):
            raise ValueError('A current HUNT pause/version/eligibility checkpoint is required')
        self.db, self.checkpoint = db_factory, checkpoint
        with self.db() as c:
            install(c)

    def _event(self, c, ident, kind, details=None):
        # Event logs deliberately exclude answers, contact information and files.
        c.execute('INSERT INTO application_execution_events(plan_id,at,kind,details) VALUES(?,?,?,?)',
                  (ident, stamp(), kind, encode(details or {})))

    def get(self, ident):
        with self.db() as c:
            row = c.execute('SELECT * FROM application_execution_plans WHERE id=?', (ident,)).fetchone()
            if not row:
                raise ValueError('Unknown application plan')
            result = dict(row)
            result['payload'] = json.loads(result['payload'])
            result['receipt'] = json.loads(result['receipt']) if result['receipt'] else None
            return result

    def plan(self, *, job_id, job_version, package_id, package_hash, form, answers, uploads=None):
        if not all(isinstance(v, str) and v for v in (job_id, job_version, package_id, package_hash)):
            raise ValueError('Exact job and package identities and versions are required')
        if not isinstance(answers, dict) or not isinstance(uploads or {}, dict):
            raise ValueError('Explicit question answers and file mappings are required')
        version = form_version(form)
        files = {k: upload_record(k, v) for k, v in (uploads or {}).items()}
        issues = unresolved_questions(form, answers, files)
        blocked = bool(form.get('captcha') or form.get('platform_restriction'))
        payload = {'kind': 'application', 'job_id': job_id, 'job_version': job_version,
                   'package_id': package_id, 'package_hash': package_hash, 'application_url': form['url'],
                   'form': form, 'form_version': version, 'answers': answers, 'uploads': files,
                   'unresolved_questions': issues}
        digest = fingerprint(payload)
        ident = digest[:32]
        status = 'blocked' if blocked else 'needs_input' if issues else 'review'
        with self.db() as c:
            c.execute('INSERT OR IGNORE INTO application_execution_plans(id,payload,payload_hash,job_id,status,created,updated) VALUES(?,?,?,?,?,?,?)',
                      (ident, encode(payload), digest, job_id, status, stamp(), stamp()))
            if c.execute('SELECT changes()').fetchone()[0]:
                self._event(c, ident, 'plan_created', {'status': status, 'payload_hash': digest, 'unresolved_count': len(issues)})
        return self.get(ident)

    def approve(self, ident, expected_hash, actor, valid_minutes=60):
        if not isinstance(actor, str) or not actor.strip() or type(valid_minutes) is not int or not 1 <= valid_minutes <= 1440:
            raise ValueError('Explicit owner identity and bounded approval lifetime are required')
        plan = self.get(ident)
        if plan['status'] != 'review' or plan['payload_hash'] != expected_hash or fingerprint(plan['payload']) != expected_hash:
            raise ValueError('Only the exact reviewed plan can be approved')
        self.checkpoint(plan['payload'])
        expires = (dt.datetime.now(UTC) + dt.timedelta(minutes=valid_minutes)).isoformat()
        with self.db() as c:
            changed = c.execute("UPDATE application_execution_plans SET status='approved',approved_by=?,approved_at=?,approval_expires=?,updated=? WHERE id=? AND status='review' AND payload_hash=?",
                                (actor, stamp(), expires, stamp(), ident, expected_hash)).rowcount
            if changed != 1:
                raise ValueError('Application plan changed during approval')
            self._event(c, ident, 'exact_plan_approved', {'payload_hash': expected_hash, 'expires': expires})
        return self.get(ident)

    def _transition(self, ident, status, event, *, error=None, receipt=None):
        with self.db() as c:
            c.execute('UPDATE application_execution_plans SET status=?,updated=?,error=?,receipt=? WHERE id=?',
                      (status, stamp(), error, encode(receipt) if receipt else None, ident))
            self._event(c, ident, event, {'error_type': error} if error else None)
        return self.get(ident)

    def execute(self, ident, adapter):
        plan = self.get(ident)
        if plan['status'] == 'submitted':
            return {**plan, 'replayed': True}
        if plan['status'] != 'approved':
            raise ValueError('Exact approval is required; interrupted or uncertain actions cannot be retried automatically')
        payload = plan['payload']
        if fingerprint(payload) != plan['payload_hash']:
            raise ValueError('Application payload changed')
        if not plan['approval_expires'] or dt.datetime.fromisoformat(plan['approval_expires']) <= dt.datetime.now(UTC):
            raise ValueError('Application approval expired')
        for item in payload['uploads'].values():
            if upload_record(item['question_id'], item['path']) != item:
                raise ValueError('Approved application file changed')
        if adapter is None or not all(callable(getattr(adapter, n, None)) for n in ('preflight', 'inspect', 'fill', 'submit')):
            raise RuntimeError('No real employer-form execution adapter is connected')
        self.checkpoint(payload)
        adapter.preflight(payload)
        # Claim before external interaction. Any crash leaves a non-replayable
        # preparing/submitting state requiring human reconciliation.
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute("SELECT id FROM application_execution_plans WHERE job_id=? AND id<>? AND status IN ('preparing','submitting','uncertain','submitted')", (payload['job_id'], ident)).fetchone()
            if prior:
                raise ValueError('This role already has an application attempt requiring reconciliation')
            changed = c.execute("UPDATE application_execution_plans SET status='preparing',updated=? WHERE id=? AND status='approved'", (stamp(), ident)).rowcount
            if changed != 1:
                raise ValueError('Application already claimed')
            self._event(c, ident, 'execution_claimed', {'payload_hash': plan['payload_hash']})
        try:
            self.checkpoint(payload)
            current = adapter.inspect(payload)
            if current.get('captcha') or current.get('platform_restriction'):
                return self._transition(ident, 'blocked', 'employer_interaction_blocked')
            if form_version(current) != payload['form_version']:
                return self._transition(ident, 'needs_review', 'form_changed_before_fill')
            preview = adapter.fill(payload)
            expected = {'answers': {k: v['value'] for k, v in payload['answers'].items()},
                        'uploads': {k: v['sha256'] for k, v in payload['uploads'].items()}}
            if preview != expected:
                return self._transition(ident, 'needs_review', 'filled_preview_does_not_match_approval')
            self.checkpoint(payload)
            # Re-read the persisted approval and every attachment after filling,
            # immediately before the irreversible final click.
            current_plan = self.get(ident)
            if current_plan['status'] != 'preparing' or current_plan['payload_hash'] != plan['payload_hash'] or fingerprint(current_plan['payload']) != plan['payload_hash'] or current_plan['approved_by'] != plan['approved_by']:
                return self._transition(ident, 'needs_review', 'approval_changed_before_submit')
            for item in payload['uploads'].values():
                if upload_record(item['question_id'], item['path']) != item:
                    return self._transition(ident, 'needs_review', 'approved_file_changed_before_submit')
            if not current_plan['approval_expires'] or dt.datetime.fromisoformat(current_plan['approval_expires']) <= dt.datetime.now(UTC):
                return self._transition(ident, 'needs_review', 'approval_expired_before_submit')
            self._transition(ident, 'submitting', 'final_submission_started')
            receipt = adapter.submit(payload, ident)
            if not isinstance(receipt, dict) or receipt.get('submitted') is not True or not receipt.get('confirmation_id') or receipt.get('evidence_kind') not in ('confirmation_page', 'provider_receipt', 'confirmation_email') or not permitted_url(receipt.get('evidence_url'), payload['form'].get('fixture_only')) or not receipt.get('confirmation_text'):
                raise RuntimeError('Submission has no positive confirmation evidence')
        except Exception as exc:
            self._transition(ident, 'uncertain', 'attempt_requires_reconciliation', error=type(exc).__name__)
            raise RuntimeError('Application attempt needs reconciliation; automatic retry is disabled') from None
        return self._transition(ident, 'submitted', 'submission_confirmed', receipt=receipt)


class LocalFixtureBrowserAdapter:
    """Actual Playwright/Chrome adapter restricted to controlled loopback fixtures.

    This cannot be passed an employer URL. It is component-verification tooling,
    not a production employer adapter or a claim that HUNT can submit real jobs.
    """
    def __init__(self, url, node_executable=None):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1') or parsed.username or parsed.password:
            raise ValueError('Only controlled loopback fixture URLs are permitted')
        self.url = url
        self.node = node_executable or shutil.which('node') or '/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        self.process = None

    def _call(self, command, **values):
        if self.process is None:
            self.process = subprocess.Popen([self.node, str(Path(__file__).with_name('application_browser.mjs')), self.url], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.process.stdin.write(encode({'command': command, **values}) + '\n')
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Isolated browser runtime failed to start or exited')
        result = json.loads(line)
        if result.get('ok') is not True:
            raise RuntimeError(result.get('error', 'Controlled browser step failed'))
        return result['result']

    def inspect(self, payload=None):
        return self._call('inspect')

    def preflight(self, payload):
        if payload['application_url'] != self.url or payload['form'].get('fixture_only') is not True:
            raise ValueError('This adapter accepts its exact local fixture plan only')
        if not Path(self.node).is_file():
            raise RuntimeError('Node runtime is not available')

    def fill(self, payload):
        return self._call('fill', payload=payload)

    def submit(self, payload, idempotency_key):
        return self._call('submit', payload=payload, idempotency_key=idempotency_key)

    def close(self):
        if self.process is not None:
            try:
                self.process.stdin.write(encode({'command': 'close'}) + '\n')
                self.process.stdin.flush()
                self.process.wait(timeout=10)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                self.process.kill()
                self.process.wait(timeout=5)
            finally:
                self.process.stdin.close()
                self.process.stdout.close()
                self.process = None
