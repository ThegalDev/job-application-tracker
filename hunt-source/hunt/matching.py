"""Evidence-linked PRD matching. Hard restrictions override numerical fit."""
import re

WEIGHTS = {'skills':30, 'eligibility':25, 'compensation':15, 'progression':15, 'company':10, 'preferences':5}
HARD_MONTHLY_USD = 2500
SKILLS = {
    'employee lifecycle':['onboarding','offboarding','employee lifecycle'],
    'recruitment':['recruitment','recruiting','hiring'],
    'people systems':['hris','workable','people systems','hr systems'],
    'automation':['automation','automate','workflow'],
    'employee relations':['employee relations','grievance'],
    'performance':['performance management','performance review'],
    'policy':['policy','policies','compliance'],
    'reporting':['reporting','analytics','data accuracy'],
}
FOREIGN = r'united states|united kingdom|european union|europe|americas?|asia|canada|poland|portugal|spain|kenya|nairobi|bangalore|san francisco|london|germany|australia|tokyo|singapore|usa|uk|u\.s\.|us|eu|france|netherlands|india|south africa|brazil|mexico|austria|switzerland|ireland|estonia|finland|sweden|denmark|norway|romania|belgium|new zealand|japan|italy|china|chile|argentina|colombia|philippines|indonesia|thailand|vietnam|malaysia|pakistan|bangladesh|egypt|morocco|israel|uae|united arab emirates|saudi arabia|greece|czech republic|czechia|hungary|bulgaria|croatia|lithuania|latvia|ukraine|turkey|taiwan|south korea|korea|hong kong'

def norm(s):
    s=re.sub(r'\bops\b','operations',str(s).lower().replace('&',' and '))
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def _quote(text, match):
    return text[max(0,match.start()-35):min(len(text),match.end()+100)] if match else ''

def compensation(job, floor=HARD_MONTHLY_USD):
    text=job.get('description','')
    number=r'([\d,]+(?:\.\d+)?\s*[kK]?)'
    period=r'(month(?:ly)?|year(?:ly)?|annum|annual(?:ly)?)'
    patterns=[r'(?:USD|US\$)\s*'+number+r'(?:\s*[-–—]\s*(?:USD|US\$|\$)?\s*'+number+r')?\s*(?:/|per\s+)?\s*'+period,
              r'\$\s*'+number+r'(?:\s*[-–—]\s*\$?\s*'+number+r')?\s*USD\s*(?:/|per\s+)?\s*'+period]
    candidates=[]
    for pattern in patterns:
        for match in re.finditer(pattern,text,re.I):
            # Recurring benefits and bonuses are not base salary. Use the nearest clause.
            preceding=re.split(r'[.\n;]',text[max(0,match.start()-130):match.start()])[-1].lower()
            benefit=re.search(r'allowance|stipend|equipment|home office|insurance|bonus|reimbursement|wellness|learning budget',preceding)
            if benefit:continue
            candidates.append(match)
    m=min(candidates,key=lambda x:x.start()) if candidates else None
    if not m:return {'status':'unknown','label':'Unknown','monthly_min':None,'monthly_max':None,'source_quote':None,'floor_usd':floor}
    def amount(v):
        v=v.replace(',','').replace(' ','').lower()
        return float(v[:-1])*1000 if v.endswith('k') else float(v)
    low=amount(m[1]);high=amount(m[2] or m[1]);period=m[3].lower()
    if not period.startswith('month'):low/=12;high/=12
    if low>high:return {'status':'unknown','label':'Unknown','monthly_min':None,'monthly_max':None,'source_quote':m[0],'floor_usd':floor}
    return {'status':'below_floor' if high<floor else 'meets_floor' if low>=floor else 'range_crosses_floor',
            'label':f'USD {low:,.0f}–{high:,.0f}/month (posting)', 'monthly_min':low,'monthly_max':high,'source_quote':m[0],'floor_usd':floor}

def eligibility(job,prefs):
    loc=job.get('location','');desc=job.get('description','');text=loc+'\n'+desc
    lower=text.lower();reasons=[];evidence=[];tier='C'
    floor=max(HARD_MONTHLY_USD,float(prefs.get('monthly_usd',HARD_MONTHLY_USD)))
    salary=compensation(job,floor)
    # Every explicit restriction wins over permissive labels and promotional text.
    nigeria_deny=re.search(r'(?:except|excluding|not eligible (?:in|from)|cannot (?:hire|employ) (?:in|from)|can\x27t hire (?:in|from)|not (?:available|open) (?:in|to)|not accepting (?:applicants|applications) from)\s+nigeria',lower)
    authorization=re.search(r'(?:must (?:already )?(?:have|hold)|require[sd]?)\s+(?:valid\s+)?(?:us|u\.s\.|uk|eu|canadian|german|australian)\s+(?:work authorization|work authorisation|work permit|citizenship)',lower)
    required=re.search(r'(?:must (?:be (?:based|located|resident)|reside)|(?:applicants|candidates) (?:must|need to) (?:be (?:based|located)|reside)|(?:only (?:hire|hiring|accept|consider)(?:ing)?(?:\s+(?:applicants|candidates|people))?))\s+(?:in|from)\s+(?:the\s+)?(?:'+FOREIGN+r')\b',lower)
    only=re.search(r'\b(?:'+FOREIGN+r')[ -]+only\b|\bonly (?:available|open) (?:in|to) (?:the )?(?:'+FOREIGN+r')\b',lower)
    suffix_deny=re.search(r'\bnigeria(?:n)?\b[^.\n]{0,65}\b(?:not eligible|ineligible|cannot apply|not accepted)\b',lower)
    within=re.search(r'(?:must|need to)\s+(?:be (?:based|located)|reside)\s+(?:within|in)\s+(?:the\s+)?(?:'+FOREIGN+r')\b',lower)
    legally=re.search(r'(?:must|need to)\s+be\s+(?:legally\s+)?authori[sz]ed to work (?:in|within) (?:the )?(?:'+FOREIGN+r')\b',lower)
    citizen_only=re.search(r'(?:only (?:for|to)|restricted to|limited to)\s+(?:the )?(?:'+FOREIGN+r')\s+(?:citizens|residents|nationals)',lower)
    country_list=re.search(r'(?:eligible countries|hiring countries|countries (?:we hire in|eligible))\s*:[^\n.]+',lower)
    excluded_list=country_list if country_list and re.search(r'\b(?:'+FOREIGN+r')\b',country_list[0]) and not re.search(r'\b(?:nigeria|worldwide|global|anywhere)\b',country_list[0]) else None
    deny=nigeria_deny or authorization or required or only or suffix_deny or within or legally or citizen_only or excluded_list
    sponsor_no=re.search(r'(?:no\s+(?:visa )?sponsorship|(?:not|cannot|can\x27t|unable to)\s+(?:(?:offer|provide|support|sponsor)\s+)?(?:visa )?sponsorship|not (?:able|eligible) to sponsor)',lower)
    sponsor_no=sponsor_no or re.search(r"(?:\bnot(?! only)\b|don't|doesn't|cannot|can't|unable)\b[^.\n;]{0,65}\b(?:sponsor|sponsorship)\b",lower)
    sponsor_yes=re.search(r'(?:visa sponsorship (?:is )?(?:available|provided)|(?:offer|provide|support) visa sponsorship|relocation (?:and|with) (?:visa )?sponsorship)',lower)
    nigeria=re.search(r'\b(?:nigeria|lagos|abuja)\b',loc,re.I)
    worldwide=re.search(r'remote worldwide|worldwide remote|work from anywhere|remote[^\n.]*\b(?:anywhere|global)\b',loc,re.I)
    regional=re.search(r'\b(?:africa|emea)\b',loc,re.I)
    regional_confirm=re.search(r'(?:eligible (?:in|from)|(?:hire|hiring|accepting (?:applicants|applications)) (?:in|from)|including|open to (?:applicants (?:in|from) )?)\s+nigeria',desc,re.I)
    foreign=re.search(r'\b(?:'+FOREIGN+r')\b',loc,re.I)
    if deny:
        tier='D';reasons.append('Explicit country or work-authorization restriction overrides remote labels.');evidence.append(_quote(text,deny))
    elif nigeria:
        tier='A';reasons.append('Employer explicitly lists Nigeria as the role location.');evidence.append(nigeria[0])
    elif sponsor_yes and not sponsor_no:
        tier='A';reasons.append('Employer explicitly offers visa sponsorship; individual visa qualification still needs review.');evidence.append(_quote(text,sponsor_yes))
    elif regional and regional_confirm:
        tier='B';reasons.append('Regional remote role explicitly includes applicants based in Nigeria.');evidence.append(_quote(desc,regional_confirm))
    elif foreign:
        tier='D';reasons.append('Foreign location without explicit relocation sponsorship or Nigeria eligibility.');evidence.append(foreign[0])
    elif worldwide and re.search(r'(?:restricted to|countries only|following countries|eligible countries|supported employment countries|(?:must|required to) (?:live|reside)|not support hiring|nigeria[^.\n]{0,35}(?:excluded|not eligible))',lower):
        reasons.append('Worldwide label conflicts with unresolved geographic restrictions; employer confirmation required.')
    elif worldwide:
        tier='A';reasons.append('Role location explicitly permits worldwide remote work.');evidence.append(worldwide[0])
    elif regional:
        reasons.append('Regional remote label lacks confirmed Nigeria eligibility.')
    else:reasons.append('Remote alone does not establish Nigeria eligibility; employer confirmation needed.')
    if salary['status']=='below_floor':
        tier='D';reasons.append(f'Confirmed salary upper bound is below the hard USD {floor:,.0f}/month minimum.');evidence.append(salary['source_quote'])
    elif salary['status']=='unknown':reasons.append('Compensation unverified; unknown pay is never treated as meeting the hard floor.')
    elif salary['status']=='range_crosses_floor':reasons.append('Published range crosses the hard floor; confirm an offer at or above the minimum.')
    return {'tier':tier,'reasons':reasons,'salary':salary['label'],'compensation':salary,'eligibility_evidence':evidence,'hard_floor_usd':floor}

def score_job(job,facts,prefs,applications):
    e=eligibility(job,prefs);description=job.get('description','');desc=description.lower();matches=[];required=[]
    for group,words in SKILLS.items():
        token=next((w for w in words if re.search(r'\b'+re.escape(w)+r'\b',desc)),None)
        if not token:continue
        required.append(group)
        fact=next((f for f in facts if any(re.search(r'\b'+re.escape(w)+r'\b',f['text'].lower()) for w in words)),None)
        if not fact:continue
        m=re.search(re.escape(token),desc)
        matches.append({'criterion':group,'job_quote':_quote(description,m),'fact_id':fact['id'],'candidate_evidence':fact['text'],'source':fact['source']})
    skill_rating=round(100*len(matches)/len(required),2) if required else 0
    progression=re.search(r'\b(?:build|design|lead|own|develop|manage|strategic|scale)\w*\b',desc)
    primary=re.search(r'people operations|people ops|hr operations|people systems',job.get('title',''),re.I)
    # Progression is a declared inference from role scope, not invented candidate seniority.
    progression_rating=85 if progression and primary else 65 if progression else 35 if primary else 0
    employment=str(job.get('employment_type',''))+' '+description
    preferred=re.search(r'\b(?:full[ -]time|contract|fractional)\b',employment,re.I)
    # Employer quality cannot be inferred from a brand name or unverified news.
    company_rating=0
    company_evidence=job.get('company_evidence',[])
    verified_company=[x for x in company_evidence if isinstance(x,dict) and x.get('authoritative_employer_verified') is True and x.get('source') and x.get('quote')]
    if verified_company:company_rating=50 # Evidence confirms operation; financial stability remains unverified.
    salary=e['compensation'];salary_rating=100 if salary['status']=='meets_floor' else 50 if salary['status']=='range_crosses_floor' else 0
    ratings={'skills':skill_rating,'eligibility':100 if e['tier'] in ('A','B') else 0,'compensation':salary_rating,'progression':progression_rating,'company':company_rating,'preferences':100 if preferred else 0}
    components={k:round(WEIGHTS[k]*ratings[k]/100,3) for k in WEIGHTS};total=round(sum(components.values()),2)
    duplicate=[]
    for a in applications:
        if norm(a.get('company','')).replace(' thanksben','')==norm(job.get('company','')) and norm(a.get('role',''))==norm(job.get('title','')):duplicate.append(a['id'])
    band=decision_band(total)
    status='Excluded' if e['tier']=='D' else 'Already applied' if duplicate else band
    if (e['tier']=='C' or salary['status']!='meets_floor') and total>=55 and status not in ('Excluded','Already applied'):status='Research needed'
    evidence={
        'skills':{'matched':len(matches),'required_groups':required,'fact_ids':[m['fact_id'] for m in matches]},
        'eligibility':{'tier':e['tier'],'quotes':e['eligibility_evidence']},
        'compensation':{'status':salary['status'],'quote':salary['source_quote']},
        'progression':{'quote':_quote(description,progression),'inference':'Scope proxy based on advertised ownership; career progression requires personal review.'},
        'company':{'sources':verified_company,'limitation':'Employer quality and stability remain unverified.'},
        'preferences':{'quote':preferred[0] if preferred else None,'limitation':'Only explicitly advertised employment type is counted.'},
    }
    confidence='High' if e['tier'] in ('A','B') and salary['status']=='meets_floor' and len(matches)>=4 and verified_company else 'Medium' if e['tier'] in ('A','B') and matches and salary['status']!='unknown' else 'Low'
    return {**e,'score':total,'weights':dict(WEIGHTS),'ratings':ratings,'components':components,'criteria_evidence':evidence,'matches':matches,'duplicate_applications':duplicate,'status':status,'decision_band':band,'confidence':confidence,'scoring_version':'prd-1.0',
            'gaps':['Unmatched required skill clusters: '+(', '.join(x for x in required if x not in {m['criterion'] for m in matches}) or 'none detected by keyword rules'), 'Employer stability, exact seniority, visa qualification and employment terms need evidence.','Evidence-based weighted fit is not a probability of an interview.']}


def decision_band(score):
    return 'Priority' if score>=85 else 'Review' if score>=70 else 'Explore' if score>=55 else 'Archive'
