"""Personal writing rules, bounded approved evidence and reviewable draft provenance."""
import json,re
from pathlib import Path

APPROVED={'lifecycle','recruitment','notion','make','records','onboarding','policies','performance'}

def generate(hunt,job,facts):
    facts=[f for f in facts if f['id'] in APPROVED]
    if not facts:raise ValueError('No API-approved career evidence')
    profile=json.loads((Path(__file__).parent/'writing-profile.json').read_text())
    fields={name:{'type':'string'} for name in ('cover_letter','cold_email_subject','cold_email','cv_summary')}
    fields['fact_ids']={'type':'array','items':{'type':'string','enum':[f['id'] for f in facts]}}
    schema={'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}
    body={'model':'gpt-4.1-mini','store':False,'max_output_tokens':3000,
          'instructions':(Path(__file__).parent/'drafting-instructions.txt').read_text(),
          'input':hunt.dump({'writing_style':{k:profile[k] for k in ('cover_letter','cold_email','cv','evidence_rules')},'public_job':{'company':job['company'],'title':job['title'],'description':job['description'][:24000]},'approved_facts':[{'id':f['id'],'text':f['text']} for f in facts]}),
          'text':{'format':{'type':'json_schema','name':'personal_application_drafts','strict':True,'schema':schema}}}
    r=hunt.fetch_json('https://api.openai.com/v1/responses',body,hunt.load_key())
    if r.get('status')!='completed':raise ValueError('Draft response incomplete; no package saved')
    raw=''.join(x.get('text','') for o in r.get('output',[]) if o.get('type')=='message' for x in o.get('content',[]) if x.get('type')=='output_text')
    result=json.loads(raw)
    ids=result.get('fact_ids',[])
    if not ids or any(i not in {f['id'] for f in facts} for i in ids):raise ValueError('Draft cites unapproved evidence')
    evidence=' '.join(f['text'] for f in facts if f['id'] in ids)
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
    if re.search(ownership,result['cover_letter']+' '+result['cold_email']+' '+result['cv_summary'],re.I) and not any(re.search(ownership,f['text'],re.I) for f in facts if f['id'] in ids):raise ValueError('Draft inflates documented onboarding coordination into programme ownership')
    result['cover_letter']='Dear '+job['company']+' hiring team,\n\n'+result['cover_letter'].strip()+'\n\nPortfolio: '+(hunt.value_for('portfolio') or 'https://aminatmajekadegbe.netlify.app/')+'\n\nAminat Majekadegbe'
    result['cold_email']=result['cold_email'].strip()+'\n\nPortfolio: '+(hunt.value_for('portfolio') or 'https://aminatmajekadegbe.netlify.app/')+'\n\nAminat Majekadegbe'
    result['writing_profile_version']=profile['version']
    result['claim_review']='Fact references and numbers validated; prose relevance requires owner review.'
    return result,r.get('usage',{}),r.get('id')

def preserve_resume(source,summary=None):
    """Replace only the summary. Preserve every other character of the CV."""
    if not summary:return source
    pattern=r'(PROFESSIONAL SUMMARY[^\n]*\n)(.*?)(?=CORE COMPETENCIES)'
    if not re.search(pattern,source,re.S):raise ValueError('Master CV summary boundary could not be verified')
    return re.sub(pattern,lambda m:m.group(1)+summary.strip()+'\n\n',source,count=1,flags=re.S)
