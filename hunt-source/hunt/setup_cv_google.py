"""Interactive, dedicated Google Docs/Drive consent; credentials never enter chat or Git.

Run only after the owner approves storing this new tracker grant in the
private HUNT Mac worker. Existing inbox/Sheets credentials are untouched.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT=Path(__file__).resolve().parent
ACCOUNT='majekadegbeaminat85@gmail.com'
BASE='https://hunt-aminat.netlify.app'
REDIRECT='http://127.0.0.1:8765/oauth/google/callback'
SCOPES=['openid','email','https://www.googleapis.com/auth/documents','https://www.googleapis.com/auth/drive']

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise ValueError('Unexpected credential-bearing redirect')

def request(url,body=None,headers=None,form=False):
    data=(urlencode(body).encode() if form else json.dumps(body).encode()) if body is not None else None
    h={'Content-Type':'application/x-www-form-urlencoded' if form else 'application/json',**(headers or {})}
    with build_opener(NoRedirect).open(Request(url,data=data,headers=h),timeout=30) as response:
        return json.load(response)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):
        pass
    def page(self,status,text):
        raw=('<!doctype html><meta charset=utf-8><title>HUNT native CV connection</title><h1>HUNT native CV</h1><p>'+text+'</p>').encode()
        self.send_response(status)
        for key,value in {'Content-Type':'text/html; charset=utf-8','Content-Length':str(len(raw)),'Cache-Control':'no-store','Referrer-Policy':'no-referrer'}.items():self.send_header(key,value)
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.headers.get('Host')!='127.0.0.1:8765':return self.page(403,'Host denied.')
        path=urlparse(self.path)
        if path.path=='/start':
            params={'client_id':self.server.client['client_id'],'redirect_uri':REDIRECT,'response_type':'code','scope':' '.join(SCOPES),'state':self.server.state,'access_type':'offline','prompt':'consent','include_granted_scopes':'false','login_hint':ACCOUNT,'code_challenge':self.server.challenge,'code_challenge_method':'S256'}
            self.send_response(302);self.send_header('Location','https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params));self.send_header('Cache-Control','no-store');self.end_headers();return
        if path.path!='/oauth/google/callback':return self.page(404,'Not found.')
        q=parse_qs(path.query)
        if self.server.consumed or time.monotonic()-self.server.started>900 or not hmac.compare_digest(q.get('state',[''])[0],self.server.state):return self.page(403,'Consent session expired or mismatched.')
        self.server.consumed=True
        try:
            if q.get('error') or not q.get('code'):raise ValueError('Consent declined')
            tokens=request('https://oauth2.googleapis.com/token',{'client_id':self.server.client['client_id'],'client_secret':self.server.client['client_secret'],'redirect_uri':REDIRECT,'code':q['code'][0],'grant_type':'authorization_code','code_verifier':self.server.verifier},form=True)
            profile=request('https://openidconnect.googleapis.com/v1/userinfo',headers={'Authorization':'Bearer '+tokens['access_token']})
            if profile.get('email')!=ACCOUNT or profile.get('email_verified') is not True:raise ValueError('Wrong account')
            scopes=tokens.get('scope','').split()
            allowed=set(SCOPES+['https://www.googleapis.com/auth/userinfo.email'])
            if not {'https://www.googleapis.com/auth/documents','https://www.googleapis.com/auth/drive'}.issubset(scopes) or set(scopes)-allowed or not tokens.get('refresh_token'):raise ValueError('Dedicated Docs and Drive grant was not returned')
            grant={'account':ACCOUNT,'scopes':scopes,'client_id':self.server.client['client_id'],'client_secret':self.server.client['client_secret'],'refresh_token':tokens['refresh_token']}
            private=Path.home()/'Library/Application Support/HUNT/application-worker/data/cv-google.json'
            private.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd=os.open(private,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
            with os.fdopen(fd,'w') as file:json.dump(grant,file)
            self.page(200,'Your HUNT native CV connection is saved privately on this Mac. It can copy your master CV, edit only new copies, and export PDFs. The original CV will remain unchanged. You may close this tab.')
            print('Native CV Google connection saved privately on this Mac. No credential values printed.',flush=True)
        except Exception as error:
            self.page(502,'Native CV setup was not confirmed. No credentials are shown here. Retry setup after checking the private runtime connection.')
            print('Native CV setup stopped: '+type(error).__name__+'. No credential values logged.',flush=True)
        self.server.done=True

if __name__=='__main__':
    client=json.loads((ROOT.parent.parent/'work/google-client.json').read_text())['web']
    server=HTTPServer(('127.0.0.1',8765),Handler);server.timeout=1;server.client=client
    server.state=secrets.token_urlsafe(32);server.verifier=secrets.token_urlsafe(64)
    server.challenge=base64.urlsafe_b64encode(hashlib.sha256(server.verifier.encode()).digest()).decode().rstrip('=')
    server.started=time.monotonic();server.consumed=False;server.done=False
    print('Approve the dedicated Google Docs/Drive connection at http://127.0.0.1:8765/start . Consent expires in 15 minutes.',flush=True)
    try:
        while not server.done and time.monotonic()-server.started<900:server.handle_request()
    finally:server.server_close()
