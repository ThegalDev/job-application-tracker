import http.cookiejar,json,os,secrets,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
import hunt

@unittest.skipUnless(os.environ.get('HUNT_HTTP_TESTS')=='1','Enable local HTTP integration checks explicitly')
class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old=(hunt.DATA,hunt.DB);hunt.DATA=Path(self.tmp.name);hunt.DB=hunt.DATA/'test.sqlite3';hunt.init()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),hunt.Handler)
        self.server.session=secrets.token_urlsafe();self.server.bootstrap=secrets.token_urlsafe();self.server.csrf=secrets.token_urlsafe()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def tearDown(self):
        self.server.shutdown();self.server.server_close();hunt.DATA,hunt.DB=self.old;self.tmp.cleanup()
    def request(self,path,body=None,origin=None,csrf=None,host=None):
        headers={}
        if body is not None:headers.update({'Origin':origin or self.url,'Content-Type':'application/json'})
        if csrf:headers['X-CSRF-Token']=csrf
        if host:headers['Host']=host
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:r=self.client.open(req);return r.status,r.read(),r.headers
        except urllib.error.HTTPError as e:return e.code,e.read(),e.headers
    def login(self):return self.request('/api/login',{'token':self.server.bootstrap})
    def test_login_and_authenticated_state(self):
        self.assertEqual(self.request('/api/state')[0],401)
        status,_,headers=self.login();self.assertEqual(status,200);self.assertIn('HttpOnly',headers['Set-Cookie']);self.assertIn('SameSite=Strict',headers['Set-Cookie'])
        self.assertEqual(self.request('/api/state')[0],200)
    def test_cross_origin_denied(self):self.assertEqual(self.request('/api/login',{'token':self.server.bootstrap},origin='https://evil.test')[0],403)
    def test_host_rebinding_denied(self):self.assertEqual(self.request('/',host='evil.test')[0],403)
    def test_csrf_denied(self):
        self.login();self.assertEqual(self.request('/api/pause',{'paused':True})[0],403)
    def test_pause_roundtrip(self):
        self.login();self.assertEqual(self.request('/api/pause',{'paused':True},csrf=self.server.csrf)[0],200)
        self.assertTrue(json.loads(self.request('/api/state')[1])['paused'])
    def test_external_send_denied(self):
        self.login();self.assertEqual(self.request('/api/send',{'recipient':'nobody@example.test'},csrf=self.server.csrf)[0],403)
    def test_secret_paths_never_served(self):
        self.login()
        for path in ['/.env.local','/data/hunt.sqlite3','/../.env.local']:
            self.assertEqual(self.request(path)[0],404)
    def test_security_headers(self):
        _,_,h=self.request('/');self.assertEqual(h['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",h['Content-Security-Policy'])
    def test_invalid_session_denied(self):self.assertEqual(self.request('/api/login',{'token':'invalid'})[0],403)

if __name__=='__main__':unittest.main(verbosity=2)
