"""Personal writing rules, bounded approved evidence and reviewable draft provenance."""
import json,re
from pathlib import Path

APPROVED={'lifecycle','recruitment','notion','make','records','onboarding','policies','performance'}

def generate(hunt,job,facts,master_cv=None):
    facts=[f for f in facts if f['id'] in APPROVED]
    if not facts:raise ValueError('No API-approved career evidence')
    projects=select_project_evidence(master_cv or '',job['description'])
    profile=json.loads((Path(__file__).parent/'writing-profile.json').read_text())
    fields={name:{'type':'string'} for name in ('cover_letter','cold_email_subject','cold_email','cv_summary')}
    fields['fact_ids']={'type':'array','items':{'type':'string','enum':[f['id'] for f in facts]+[p['id'] for p in projects]}}
    schema={'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
    body={'model':'gpt-4.1-mini','store':False,'max_output_tokens':3000,
          'instructions':(Path(__file__).parent/'drafting-instructions.txt').read_text(),
          'input':hunt.dump({'writing_style':{k:profile[k] for k in ('cover_letter','cold_email','cv','evidence_rules')},'public_job':{'company':job['company'],'title':job['title'],'description':job['description'][:24000]},'approved_facts':[{'id':f['id'],'text':f['text']} for f in facts],'approved_project_excerpts':projects}),
          'text':{'format':{'type':'json_schema','name':'personal_application_drafts','strict':True,'schema':schema}}}
    r=hunt.fetch_json('https://api.openai.com/v1/responses',body,hunt.load_key())
    if r.get('status')!='completed':raise ValueError('Draft response incomplete; no package saved')
    raw=''.join(x.get('text','') for o in r.get('output',[]) if o.get('type')=='message' for x in o.get('content',[]) if x.get('type')=='output_text')
    result=json.loads(raw)
    ids=result.get('fact_ids',[])
    allowed={f['id'] for f in facts}|{p['id'] for p in projects}
    if not ids or any(i not in allowed for i in ids):raise ValueError('Draft cites unapproved evidence')
    ids=list(dict.fromkeys(ids+[p['id'] for p in projects]));result['fact_ids']=ids
    evidence=' '.join([f['text'] for f in facts if f['id'] in ids]+[p['text'] for p in projects if p['id'] in ids])
    def numbers(value):
        return {n.replace(',', '') for n in re.findall(r'(?<![\w.])\d+(?:,\d{3})*(?:\.\d+)?%?(?![\w.])',value)}
    verified_numbers=numbers(evidence)
    for field in ('cover_letter','cold_email_subject','cold_email','cv_summary'):
        text=result[field]
        if isinstance(text,str) and re.search(r'\bday\s*1\b',job['description'],re.I):
            text=re.sub(r'\bday\s*1\b','first day',text,flags=re.I);result[field]=text
        if not isinstance(text,str) or not text.strip() or len(text)>14000:raise ValueError('Invalid draft field')
        if any(p in text.lower() for p in ('i hope this email finds you well','i am excited to apply')):raise ValueError('Draft violates owner writing rules')
        if not numbers(text).issubset(verified_numbers):raise ValueError('Draft introduces an unsupported number')
    if result['cover_letter'].strip()==result['cold_email'].strip():raise ValueError('Cover letter and outreach must be separate drafts')
    if re.search(r'\[[^\]]*(?:placeholder|portfolio|link)[^\]]*\]',result['cover_letter']+' '+result['cold_email'],re.I):raise ValueError('Draft contains a placeholder instead of a real application link')
    ownership=r'\b(?:built|designed|developed|created|implemented|launched|established|led|owned)\b[^.!?\n]{0,60}\bonboarding\b[^.!?\n]{0,35}\b(?:program(?:me)?s?|cohorts?|frameworks?|systems?)\b|\b(?:led|owned) onboarding\b'
    evidence_text=[f['text'] for f in facts if f['id'] in ids]+[p['text'] for p in projects if p['id'] in ids]
    if re.search(ownership,result['cover_letter']+' '+result['cold_email']+' '+result['cv_summary'],re.I) and not any(re.search(ownership,text,re.I) for text in evidence_text):raise ValueError('Draft inflates documented onboarding coordination into programme ownership')
    if projects:result['cover_letter']=result['cover_letter'].strip()+'\n\nProjects I have built:\n'+'\n'.join('- '+p['title']+': '+p['text'] for p in projects)
    result['cover_letter']='Dear '+job['company']+' hiring team,\n\n'+result['cover_letter'].strip()+'\n\nPortfolio: '+(hunt.value_for('portfolio') or 'https://aminatmajekadegbe.netlify.app/')+'\n\nAminat Majekadegbe'
    result['cold_email']=result['cold_email'].strip()+'\n\nPortfolio: '+(hunt.value_for('portfolio') or 'https://aminatmajekadegbe.netlify.app/')+'\n\nAminat Majekadegbe'
    result['writing_profile_version']=profile['version']
    result['claim_review']='Fact references and numbers validated; prose relevance requires owner review.'
    return result,r.get('usage',{}),r.get('id')

def select_project_evidence(source,job_description,limit=3):
    match=re.search(r'(?im)^PROJECTS\b[^\r\n]*(?:\r?\n)',source)
    if not match:return []
    job_terms={x for x in re.findall(r'[a-z0-9]+',job_description.lower()) if len(x)>3}
    ignored={'about','across','after','also','based','build','built','company','create','data','develop','experience','from','have','into','lead','more','need','role','team','that','their','these','this','through','using','what','where','which','with','work','years'}
    job_terms-=ignored
    projects=[];title=None;claims=[]
    def finish():
        if not title or not claims:return
        unique=[]
        for claim in claims:
            if claim and claim not in unique:unique.append(claim)
        for index,claim in enumerate(unique):
            terms={x for x in re.findall(r'[a-z0-9]+',claim.lower()) if len(x)>3}-ignored
            score=3*len(terms&job_terms)+8*len({x for x in re.findall(r'[a-z0-9]+',title.lower()) if len(x)>3}&job_terms)
            projects.append({'title':title,'text':claim[:900],'score':score,'id':'project-'+str(len(projects)+1)})
    for raw in source[match.end():].splitlines():
        line=raw.strip()
        if not line:continue
        if line.startswith('* '):
            claims.append(line[2:].strip());continue
        label=re.match(r'^(Problem|System|Impact|Stack):\s*(.*)$',line,re.I)
        if label:
            if label[1].lower() in ('system','impact'):claims.append(label[2].strip())
            continue
        if line.lower().startswith('tech stack:'):continue
        if len(line)<=150 and not line.endswith(('.', '!', '?')):
            finish();title=re.split(r'\s{2,}|\s+\|\s+',line)[0].strip();claims=[]
        elif title:
            claims.append(line)
    finish()
    if not projects:return []
    ranked=sorted(projects,key=lambda item:(item['score'],len(item['text'])),reverse=True)
    selected=[];seen=set()
    for item in ranked:
        if item['title'] in seen:continue
        selected.append({key:item[key] for key in ('id','title','text')});seen.add(item['title'])
        if len(selected)>=limit:break
    return selected

def preserve_resume(source,summary=None,target_title=None,project_highlights=None):
    """Tailor the opening and add highlights without deleting original CV content."""
    newline='\r\n' if '\r\n' in source else '\n'
    if target_title:
        pattern=r'^([^\r\n]*\r?\n)[^\r\n]*(\r?\n)'
        if not re.search(pattern,source,re.M):raise ValueError('Master CV name/title boundary could not be verified')
        source=re.sub(pattern,lambda m:m.group(1)+'Target role: '+target_title.strip()+m.group(2),source,count=1,flags=re.M)
    if summary:
        pattern=r'(PROFESSIONAL SUMMARY[^\r\n]*\r?\n)([\s\S]*?)(?=CORE COMPETENCIES)'
        if not re.search(pattern,source,re.I):raise ValueError('Master CV summary boundary could not be verified')
        source=re.sub(pattern,lambda m:m.group(1)+summary.strip()+'\n\n',source,count=1,flags=re.I)
    if project_highlights:
        marker=re.search(r'(?m)^CORE COMPETENCIES',source)
        if not marker:raise ValueError('Master CV competency boundary could not be verified')
        bullets=[f"* {item['title']}: {item['text']}" for item in project_highlights]
        section='SELECTED PROJECT HIGHLIGHTS'+newline+'\n'.join(bullets)+newline*2
        source=source[:marker.start()]+section+source[marker.start():]
    return source
