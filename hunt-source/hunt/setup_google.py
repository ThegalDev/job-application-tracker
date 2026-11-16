"""One-time Google consent with state, PKCE and a private loopback callback.

Client credentials and refresh tokens remain outside source/deliverables. Neither
authorization codes nor credentials are logged or returned to the dashboard.
"""
import base64,hashlib,hmac,json,os,secrets,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from urllib.parse import urlencode,urlparse,parse_qs
from urllib.request import Request,build_opener
from hunt import NoRedirect

WORK=Path(__file__).resolve().parents[2]/'work'
CLIENT=WORK/'google-client.json';DEST=WORK/'google-oauth.json'
REDIRECT='http://127.0.0.1:8765/oauth/google/callback'
SCOPES=['https://www.googleapis.com/auth/gmail.readonly','https://www.googleapis.com/auth/spreadsheets']
EXPECTED='majekadegbeaminat85@gmail.com'

def persist(value):
    temp=DEST.with_suffix('.tmp');fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as file:json.dump(value,file)
    os.replace(temp,DEST);os.chmod(DEST,0o600)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,message):
        raw=('<!doctype html><meta charset=utf-8><script>history.replaceState(null,"","/connected")</script><title>HUNT Google connection</title><h1>HUNT Google connection</h1><p>'+message+'</p>').encode()
        self.send_response(status);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.headers.get('Host')!='127.0.0.1:8765':return self.reply(403,'Host denied.')
        p=urlparse(self.path)
        if p.path=='/start':
            params={'client_id':self.server.client['client_id'],'redirect_uri':REDIRECT,'response_type':'code','scope':' '.join(SCOPES),'state':self.server.state,'access_type':'offline','prompt':'consent','code_challenge':self.server.challenge,'code_challenge_method':'S256'}
            self.send_response(302);self.send_header('Location','https://accounts.google.com/o/oauth2/v2/auth?'+urlencode(params));self.send_header('Cache-Control','no-store');self.end_headers();return
        if p.path!='/oauth/google/callback':return self.reply(404,'Not found.')
        q=parse_qs(p.query)
        if time.monotonic()-self.server.started>900 or self.server.consumed or not hmac.compare_digest(q.get('state',[''])[0],self.server.state):return self.reply(403,'Authorization session expired or did not match. No credentials were saved.')
        if q.get('error'):return self.reply(400,'Google authorization was declined or blocked. No credentials were saved.')
        code=q.get('code',[''])[0]
        if not code:return self.reply(400,'No authorization code returned.')
        self.server.consumed=True
        try:
            data=urlencode({'client_id':self.server.client['client_id'],'client_secret':self.server.client['client_secret'],'redirect_uri':REDIRECT,'grant_type':'authorization_code','code':code,'code_verifier':self.server.verifier}).encode()
            with build_opener(NoRedirect).open(Request('https://oauth2.googleapis.com/token',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=30) as response:tokens=json.load(response)
            if not tokens.get('refresh_token') or not tokens.get('access_token'):raise ValueError('No refresh grant')
            with build_opener(NoRedirect).open(Request('https://gmail.googleapis.com/gmail/v1/users/me/profile',headers={'Authorization':'Bearer '+tokens['access_token']}),timeout=30) as response:profile=json.load(response)
            if profile.get('emailAddress','').lower()!=EXPECTED:raise ValueError('Wrong account')
            granted=set(tokens.get('scope','').split())
            if not set(SCOPES).issubset(granted):raise ValueError('Required scopes not granted')
            persist({'client_id':self.server.client['client_id'],'client_secret':self.server.client['client_secret'],'refresh_token':tokens['refresh_token'],'account':EXPECTED,'scopes':sorted(granted),'created_at':time.time()})
            self.server.connected=True
            self.reply(200,'Connection verified and saved securely. Gmail sending is not enabled. You can close this tab.')
            print('Google connection verified for the recruitment inbox; refresh credential saved privately. Sending disabled.',flush=True)
        except Exception as error:
            self.server.error=type(error).__name__;self.reply(502,'The connection could not be verified. No runtime credential was saved. Check API enablement/account/consent and restart setup.')
            print('Google connection failed safely: '+type(error).__name__+'. No credential values logged.',flush=True)

if __name__=='__main__':
    client=json.loads(CLIENT.read_text())['web'];server=HTTPServer(('127.0.0.1',8765),Handler)
    server.client=client;server.state=secrets.token_urlsafe(32);server.verifier=secrets.token_urlsafe(64);server.challenge=base64.urlsafe_b64encode(hashlib.sha256(server.verifier.encode()).digest()).decode().rstrip('=')
    server.started=time.monotonic();server.consumed=False;server.connected=False;server.error=None;server.timeout=2
    print('HUNT Google consent is ready at http://127.0.0.1:8765/start',flush=True)
    try:
        while time.monotonic()-server.started<900 and not server.connected and not server.error:server.handle_request()
    finally:server.server_close()
