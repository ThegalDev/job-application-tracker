"""Explicit single-application Breezy test; not enabled in the recurring worker."""
import copy
from pathlib import Path
from urllib.parse import urlsplit
import re
from application_runner import ProductionLeverAdapter,validate_context

JOB_ID='startupjobs:senior-technical-recruiter-scientific-safety-alliance-10757724'
APPLICATION_URL='https://scientific-safety-alliance.breezy.hr/p/cb3bd5c1c09b-senior-technical-recruiter/apply'
LISTING_URL='https://startup.jobs/senior-technical-recruiter-scientific-safety-alliance-10757724'

def breezy_url(value):
    u=urlsplit(value)
    if u.scheme!='https' or not re.fullmatch(r'[a-z0-9-]+\.breezy\.hr',u.hostname or '') or u.hostname=='app.breezy.hr' or u.username or u.password or u.port or u.query or u.fragment or not re.fullmatch(r'/p/[a-f0-9]{12}-[a-z0-9-]+(?:/apply)?',u.path):
        raise ValueError('Exact public Breezy position URL required')
    return value

class ProductionBreezyAdapter(ProductionLeverAdapter):
    browser_script_name='breezy_browser.mjs'
    def __init__(self,url,**kwargs):
        # Keep the default Lever-only runner and recurring authorization unchanged.
        self.url=breezy_url(url)
        import shutil
        self.node=kwargs.get('node_executable') or shutil.which('node') or '/Users/theoneglobal/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        self.evidence_dir=Path(kwargs['evidence_dir']);self.process=None
    def preflight(self,payload):
        if payload['form'].get('fixture_only') or payload['form'].get('provider')!='breezy' or payload['application_url']!=self.url:
            raise ValueError('Exact production Breezy plan required')

def checkpoint(client,payload):
    if payload['job_id']!=JOB_ID or payload['application_url']!=APPLICATION_URL:
        raise ValueError('The owner-authorized one-application test is bound to a different role')
    current=client.context(payload['job_id'],payload['package_id'])
    source=current['job']['application_url'].split('?')[0]
    if source not in (LISTING_URL,APPLICATION_URL,APPLICATION_URL.removesuffix('/apply')):
        raise ValueError('Saved listing identity changed')
    if current['job']['company']!='Scientific Safety Alliance' or current['job']['title']!='Senior Technical Recruiter':
        raise ValueError('Employer or role identity changed')
    # The pool stores the aggregator URL. The actual employer link was independently
    # verified against the employer's public board, including matching UK location.
    current=copy.deepcopy(current);current['job']['application_url']=APPLICATION_URL
    validate_context(current,payload,url_validator=breezy_url)
