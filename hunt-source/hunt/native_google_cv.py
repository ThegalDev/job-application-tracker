"""Native master-copy CV edits and PDF export using the private Mac grant.

Only fresh copies of MASTER may be edited. No original or existing document is
an edit target. Google credentials stay on this Mac; HUNT receives source text
for drafting and the verified PDF, never the Google grant.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import URLError
from application_runner import NoRedirect

MASTER='1u9NQcSpOF1jRwHUmN-LeKZTWazENUoQjvYV8xzkLsGQ'
ACCOUNT='majekadegbeaminat85@gmail.com'
SCOPES={'https://www.googleapis.com/auth/drive','https://www.googleapis.com/auth/documents'}

def digest(data):return hashlib.sha256(data).hexdigest()

def utf16_length(value):return len(value.encode('utf-16-le'))//2

def private_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as out:json.dump(data,out)

def paragraphs(doc):
    tabs=doc.get('tabs',[])
    if len(tabs)!=1:raise ValueError('Native template tab structure changed')
    tab=tabs[0];body=tab.get('documentTab',tab)
    return tab.get('tabProperties',{}).get('tabId',tab.get('tabId')),body,[x for x in body['body']['content'] if 'paragraph' in x]

def text(p):return ''.join(e.get('textRun',{}).get('content','') for e in p['paragraph']['elements']).rstrip('\n')

def signature(doc):
    _,body,rows=paragraphs(doc)
    return {'paragraphs':len(rows),'bullets':sum('bullet' in r['paragraph'] for r in rows),'links':[e['textRun']['textStyle']['link'] for r in rows for e in r['paragraph']['elements'] if e.get('textRun',{}).get('textStyle',{}).get('link')], 'drawings':len(body.get('positionedObjects',{})),'page_setup':body.get('documentStyle',doc.get('documentStyle',{}))}

def mapping(doc):
    _,_,rows=paragraphs(doc);section='';result=[]
    for i,row in enumerate(rows):
        t=text(row);plain=t.strip()
        if plain in ('PROFESSIONAL SUMMARY','CORE COMPETENCIES','TECHNICAL SKILLS','PROFESSIONAL EXPERIENCE','EDUCATION','TRAININGS & CERTIFICATIONS','PROJECTS'):section=plain
        editable=('bullet' in row['paragraph'] and section!='TRAININGS & CERTIFICATIONS') or (section=='PROFESSIONAL SUMMARY' and bool(plain) and plain!='PROFESSIONAL SUMMARY') or (section=='PROJECTS' and bool(re.match(r'^(Problem|System|Impact):',plain))) or i==128
        kind='bullet' if 'bullet' in row['paragraph'] else 'summary' if section=='PROFESSIONAL SUMMARY' else 'project'
        prefix=''
        if i==0:
            if '\u000b' not in t:raise ValueError('Native name/headline structure changed')
            prefix=t[:t.index('\u000b')+1];suffix=t[len(prefix):];prefix+=suffix[:len(suffix)-len(suffix.lstrip())];editable=True;kind='headline'
        elif editable:
            runs=[e.get('textRun',{}) for e in row['paragraph']['elements']]
            for run in runs:
                if run.get('textStyle',{}).get('bold') and ':' in run.get('content',''):
                    prefix+=run['content']
                else:break
            if prefix==t:prefix=''
        result.append({'id':i,'text':t[len(prefix):] if editable else t,'editable':editable,'kind':kind,'prefix':prefix})
    if len(rows)!=177 or signature(doc)['bullets']!=90:raise ValueError('Master template changed; review mapping before unattended editing')
    return result

def project_tool_versions(plan):
    contexts={};group=[];active=False
    def flush():
        phrases=[phrase for p in group if re.match(r'^(Tech Stack|Stack):',p['text'].strip()) for phrase in re.findall(r'\b[A-Za-z][\w.+-]*\s+\d+(?:\.\d+)*\b',p['text'])]
        for p in group:contexts[p['id']]=phrases
        group.clear()
    for p in plan:
        if p['text'].strip()=='PROJECTS':active=True;continue
        if not active:continue
        if not p['editable'] and p['text'].strip() and not re.match(r'^(Tech Stack|Stack):',p['text'].strip()):flush()
        group.append(p)
    flush();return contexts

class NativeGoogleCV:
    def __init__(self,root):
        self.root=Path(root);grant=json.loads((self.root/'data/cv-google.json').read_text())
        if grant.get('account')!=ACCOUNT or not SCOPES.issubset(grant.get('scopes',[])):raise ValueError('Dedicated native CV grant is required')
        payload=urlencode({k:grant[k] for k in ('client_id','client_secret','refresh_token')}|{'grant_type':'refresh_token'}).encode()
        self.opener=build_opener(NoRedirect)
        for attempt in range(2):
            try:
                with self.opener.open(Request('https://oauth2.googleapis.com/token',data=payload),timeout=30) as response:token=json.load(response)
                break
            except URLError:
                if attempt:raise
                time.sleep(.5)
        self.token=token['access_token']
    def _curl_read(self,url,headers):
        # Read-only fallback for intermittent Python TLS disconnects. Secrets
        # travel through stdin, never argv, environment or diagnostic output.
        quote=lambda s:'"'+s.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')+'"'
        config='url = '+quote(url)+'\n'+''.join('header = '+quote(k+': '+v)+'\n' for k,v in headers.items())
        result=subprocess.run(['/usr/bin/curl','--config','-','--compressed','--silent','--max-time','30','--max-filesize','10485760','--proto','=https','--write-out','\n%{http_code}'],input=config.encode(),capture_output=True,timeout=35)
        if result.returncode:raise ValueError('Google read transport did not complete')
        raw,separator,status=result.stdout.rpartition(b'\n')
        if not separator or status!=b'200' or len(raw)>10*1024*1024:raise ValueError('Google read was not confirmed')
        return raw
    def call(self,url,body=None,binary=False):
        if not url.startswith(('https://docs.googleapis.com/v1/documents/','https://www.googleapis.com/drive/v3/files/')):raise ValueError('Google CV API endpoint denied')
        headers={'Authorization':'Bearer '+self.token}
        if body is not None:headers['Content-Type']='application/json'
        for attempt in range(2 if body is None else 1):
            try:
                with self.opener.open(Request(url,headers=headers,data=json.dumps(body).encode() if body is not None else None),timeout=60) as response:raw=response.read(10*1024*1024+1)
                break
            except URLError:
                if body is not None:raise
                if attempt:
                    raw=self._curl_read(url,headers);break
                time.sleep(.5)
        if len(raw)>10*1024*1024:raise ValueError('Native document exceeds bounded export')
        return raw if binary else json.loads(raw)
    def get(self,id):return self.call('https://docs.googleapis.com/v1/documents/'+id+'?includeTabsContent=true')
    def master(self):return self.get(MASTER)
    def tailor(self,source,replacements,title):
        plan=mapping(source);expected={p['id']:p for p in plan if p['editable']}
        edits={p['id']:p['text'] for p in replacements}
        for i,new in list(edits.items()):
            prefix=expected.get(i,{}).get('prefix','').strip()
            while prefix and new.lstrip().lower().startswith(prefix.lower()):new=new.lstrip()[len(prefix):].lstrip()
            if prefix and not expected[i]['prefix'][-1].isspace() and new and not new[0].isspace():new=' '+new
            edits[i]=new
        if len(edits)!=len(replacements) or edits.keys()!=expected.keys():raise ValueError('All native paragraphs must be reviewed exactly once')
        source_text=' '.join(p['text'] for p in plan)
        unsupported_scopes=[term for term in ['sales','marketing','G&A','go-to-market','GTM'] if not re.search(r'\b'+re.escape(term)+r'\b',source_text,re.I)]
        versions=project_tool_versions(plan)
        for i,new in edits.items():
            old=expected[i]['text']
            if expected[i]['kind']!='headline' and any(re.search(r'\b'+re.escape(term)+r'\b',new,re.I) for term in unsupported_scopes):raise ValueError('Unsourced hiring department in native CV')
            if not isinstance(new,str) or not new.strip() or re.search(r'[\n\r\v]',new):raise ValueError('Paragraph boundaries may not change')
            nums=lambda s:{n.replace(',','') for n in re.findall(r'\b\d+(?:[,.]\d+)*\b',s)}
            allowed=nums(' '.join(p['text'] for p in plan)) if expected[i]['kind']=='summary' else nums(old)
            allowed=set(allowed)
            for phrase in versions.get(i,[]):
                if phrase.lower() in new.lower():allowed.update(nums(phrase))
            if nums(new)-allowed or expected[i]['kind'] not in ('summary','headline') and nums(old)-nums(new):raise ValueError('Source metrics changed')
            if expected[i]['kind']=='bullet' and len(new.split())<len(old.split())*.9:raise ValueError('Source bullet shortened')
        if self.master()['revisionId']!=source['revisionId']:raise ValueError('Master changed during drafting; start from fresh source')
        copied=self.call('https://www.googleapis.com/drive/v3/files/'+MASTER+'/copy?fields=id,webViewLink',{'name':title[:200]});id=copied['id']
        if id==MASTER:raise ValueError('Master cannot be the edit target')
        private_json(self.root/'data/native-cv-in-progress.json',{'document_id':id,'document_url':copied.get('webViewLink'),'source_revision':source['revisionId'],'validation_version':4,'state':'copy_created'})
        doc=self.get(id);tab,_,rows=paragraphs(doc);requests=[]
        for i in sorted(edits,reverse=True):
            p=expected[i];old=p['text'];new=edits[i]
            if old==new:continue
            full=text(rows[i]);start=rows[i]['startIndex']+utf16_length(p['prefix']);end=rows[i]['endIndex']-1
            if full!=p['prefix']+old:raise ValueError('Native copied paragraph changed')
            # Indexed replacement is scoped to this exact paragraph, including duplicate wording.
            requests.extend([{'deleteContentRange':{'range':{'tabId':tab,'startIndex':start,'endIndex':end}}},{'insertText':{'location':{'tabId':tab,'index':start},'text':new}}])
        self.call('https://docs.googleapis.com/v1/documents/'+id+':batchUpdate',{'requests':requests,'writeControl':{'requiredRevisionId':doc['revisionId']}})
        doc=self.get(id);tab,_,rows=paragraphs(doc);_,_,original=paragraphs(source);styles=[]
        for i,p in expected.items():
            if text(rows[i])!=p['prefix']+edits[i]:raise ValueError('Native content readback mismatch')
            if p['kind']=='headline':continue
            runs=[e['textRun'] for e in original[i]['paragraph']['elements'] if e.get('textRun',{}).get('content','').strip()]
            baseline=runs[-1].get('textStyle',{})
            styles.append({'updateTextStyle':{'range':{'tabId':tab,'startIndex':rows[i]['startIndex']+utf16_length(p['prefix']),'endIndex':rows[i]['endIndex']-1},'textStyle':{k:baseline.get(k,False) for k in ('bold','italic','underline')},'fields':'bold,italic,underline'}})
        for i,row in enumerate(rows):
            if i not in expected and text(row)!=text(original[i]):raise ValueError('Protected source paragraph changed')
        # Keep project headings/stacks and short labelled blocks with their
        # following content so rewritten text cannot orphan a project title.
        in_experience=False
        for row in rows:
            plain=text(row).strip()
            if plain=='PROFESSIONAL EXPERIENCE':in_experience=True
            if plain=='EDUCATION':in_experience=False
            if in_experience and 'bullet' not in row['paragraph']:
                styles.append({'updateParagraphStyle':{'range':{'tabId':tab,'startIndex':row['startIndex'],'endIndex':row['endIndex']},'paragraphStyle':{'keepWithNext':True},'fields':'keepWithNext'}})
        in_projects=False
        for i,row in enumerate(rows):
            plain=text(row).strip()
            if plain=='PROJECTS':in_projects=True
            if not in_projects or i>=len(rows)-1:continue
            if i not in expected or plain.startswith(('Problem:','System:')):
                styles.append({'updateParagraphStyle':{'range':{'tabId':tab,'startIndex':row['startIndex'],'endIndex':row['endIndex']},'paragraphStyle':{'keepWithNext':True},'fields':'keepWithNext'}})
        if styles:self.call('https://docs.googleapis.com/v1/documents/'+id+':batchUpdate',{'requests':styles,'writeControl':{'requiredRevisionId':doc['revisionId']}})
        final=self.get(id)
        if signature(final)!=signature(source):raise ValueError('Native layout, list, links or divider structure changed')
        if self.master()['revisionId']!=source['revisionId']:raise ValueError('Master revision changed; document not eligible for upload')
        pdf=self.call('https://www.googleapis.com/drive/v3/files/'+id+'/export?mimeType=application%2Fpdf',binary=True)
        if not pdf.startswith(b'%PDF-'):raise ValueError('Native PDF export failed')
        sha=digest(pdf);path=self.root/'data/application-files'/f'{sha}.pdf';path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as out:out.write(pdf)
        _,_,final_rows=paragraphs(final)
        report={'tailored_text':'\n'.join(text(row) for row in final_rows)+'\n','validation_version':4,'source_doc_id':MASTER,'source_revision':source['revisionId'],'document_id':id,'document_url':copied.get('webViewLink'),'document_revision':final['revisionId'],'sha256':sha,'bytes':len(pdf),'qa':signature(final),'master_unchanged':True,'paragraphs_reviewed':len(expected)}
        private_json(path.with_suffix('.json'),report)
        return path,report

def prepare_native_package(client,package_id,root):
    google=NativeGoogleCV(root);source=google.master();plan=mapping(source)
    package=client.request('/api/package?'+urlencode({'id':package_id}))
    if package.get('native_cv') and package['native_cv'].get('validation_version')==4 and package['native_cv']['source_revision']==source['revisionId']:
        _,_,rows=paragraphs(source);master_text='\n'.join(text(row) for row in rows)+'\n'
        target=Path(root)/'data/master-cv.txt';fd=os.open(target,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as out:out.write(master_text)
        return package
    task=client.request('/api/native-cv-draft',body={'job_id':package['job_id'],'validation_version':4,'source_doc_id':MASTER,'source_revision':source['revisionId'],'paragraphs':plan})
    task=client.request('/api/native-cv-draft?'+urlencode({'id':task['id']}));private_json(Path(root)/'data/native-cv-task.json',task)
    deadline=time.monotonic()+570
    while task['status'] in ('queued','running') and time.monotonic()<deadline:
        time.sleep(3);task=client.request('/api/native-cv-draft?'+urlencode({'id':task['id']}));private_json(Path(root)/'data/native-cv-task.json',task)
    if task['status']!='completed':raise ValueError('Native CV drafting did not complete: '+str(task.get('error') or task['status']))
    path,report=google.tailor(source,task['result']['replacements'],'Majekadegbe Aminat Bamitale — '+str(package.get('company','Employer'))+' — '+str(package.get('role','Role'))+' — Tailored CV')
    _,_,rows=paragraphs(source);master_text='\n'.join(text(row) for row in rows)+'\n'
    result=client.request('/api/native-cv-attach',body={'package_id':package['id'],'expected_payload_hash':package['payload_hash'],'tailored_text':report.pop('tailored_text'),'native_cv':report,'pdf_base64':base64.b64encode(path.read_bytes()).decode(),'master_text':master_text})
    target=Path(root)/'data/master-cv.txt';fd=os.open(target,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as out:out.write(master_text)
    return result
