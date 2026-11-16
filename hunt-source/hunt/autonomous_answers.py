"""Grounded autonomous answers; unresolved factual questions become per-job outcomes."""
import json,re
from pathlib import Path

def complete_answers(form,context,root,contacts):
    answers=dict(contacts);source=(Path(root)/'data/master-cv.txt').read_text()
    summary=source.split('PROFESSIONAL SUMMARY\n',1)[-1].split('\nCORE COMPETENCIES',1)[0].strip()
    owner_file=Path(root)/'data/application-answer-profile.json';owner=json.loads(owner_file.read_text()) if owner_file.exists() else {}
    for q in form['questions']:
        if q['id'] in answers or q['type']=='file':continue
        label=q['label'].lower();value=None;origin='approved_package'
        if 'authorized to work in the united states' in label or 'authorized to work in the us' in label:
            value=owner.get('us_work_authorized');origin='owner_answer'
        elif 'sponsorship' in label and (' us' in label or 'united states' in label or re.search(r'United States|\bUSA\b|\bU\.S\.|\bRemote US\b',context.get('job',{}).get('location',''),re.I)):
            value=owner.get('us_visa_sponsorship');origin='owner_answer'
        elif q['type'] in ('select','radio'):
            # A decline choice discloses no demographic attribute.
            value=next((x for x in q.get('options',[]) if re.search(r'^(?:prefer|refer) not to (?:answer|disclose|self.identify)$',x,re.I)),None)
            if value is None and 'self-identification' in label:value=next((x for x in q.get('options',[]) if x.startswith('General Opt-Out:')),None)
            if value is None and re.search(r'country.*(?:resid|live|based)|(?:current|home).*country',label):value=next((x for x in q.get('options',[]) if x.lower() in ('nigeria','nga','ng')),None)
        elif q['type']=='checkbox' and re.search(r'(?:read|understand).*(?:privacy|disclaimer)|privacy (?:policy|notice)',label) and not re.search(r'marketing|future opportunit|third.part',label):value=True
        elif q['type']=='text' and q.get('input_type') not in ('number','date') and re.search(r'notice period|when.*(?:start|available)',label):value='To be discussed.'
        elif q['type']=='text' and q.get('input_type') not in ('number','date') and re.search(r'(?:expected|desired|expectations).*salary|salary.*expect',label):value='Open to discussing compensation based on the role and total package.'
        elif q['type']=='textarea' and re.search(r'experience|background|about yourself|why.*(?:role|company|apply)|cover letter|additional information|summary|describe|tell us|tools.*used|systems.*used',label) and not re.search(r'citizen|authorized|sponsor|criminal|disabilit|medical|passport',label):
            value=summary+' I am based in '+str(owner.get('current_location','Lagos, Nigeria'))+'.'
        if value is not None:
            if q['type']=='checkbox' and not isinstance(value,bool):continue
            if q['type'] in ('radio','select') and value not in q.get('options',[]):continue
            answers[q['id']]={'value':value,'source':origin,'verified':True}
    return answers
