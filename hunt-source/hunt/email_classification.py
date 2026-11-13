"""Conservative recruiting-message classification, with no actions or writes.

This identifies possible events; account/sender/application association and event
ordering must be checked by the caller before a status transition is applied.
"""
import re

CLASSIFIER_VERSION = 'recruiting-events-2026-11-12-v3'

_RULES = [
    ('Rejected', [
        r'(?:we (?:are|will) not|not be) moving forward with your (?:candidacy|application)',
        r'decided not to (?:progress|proceed)(?: with your (?:candidacy|application))?',
        r'(?:we (?:have |will )?)move forward with other candidates',
        r'will not be progressing(?: with your (?:candidacy|application))?',
        r'your application (?:was|has been) unsuccessful',
        r'(?:decided|decision) to (?:move|proceed|progress|continue|go)(?:\s+forward|\s+ahead)? with (?:other |different |another |a |the )?(?:candidates?|applicants?|profiles?)\b',
        r'(?:will|have|are|we.re|we are)\s+(?:be\s+)?(?:moving|proceeding|progressing|continuing) (?:forward |ahead )?with (?:other|different|another) (?:candidates?|applicants?)',
        r'(?:will not|won.t|not to|unable to) (?:be )?(?:move|moving|proceed|proceeding|progress|progressing|continue|continuing|advance|advancing)(?: forward| ahead)? (?:with )?(?:your|this) (?:application|candidacy)',
        r'(?:decided|decision) (?:to )?(?:pass on|not to advance|not to continue with) your (?:application|candidacy)',
        r'your (?:application|candidacy) (?:has not been|was not|is not) (?:selected|successful)',
    ]),
    ('Offer received', [r'pleased to offer you', r'formal offer of employment',
                        r'(?:attached|enclosed) (?:is )?your (?:employment |job )?offer']),
    ('Assessment / next step', [r'completed the ai interview',
        r'invite you to (?:complete|take) (?:an? )?assessment',
        r'please complete (?:the|this|an?) (?:skills )?assessment']),
    ('Interview invitation', [r'invite you to (?:an? )?interview',
                              r'(?:please )?schedule an interview',
                              r'(?:arrange|schedule) (?:a |an? )?(?:first |next )?interview with you']),
    ('Follow-up request', [r'please (?:share|send|provide) (?:us )?(?:your )?(?:availability|updated (?:cv|resume)|portfolio|additional information)',
                           r'following up on your application']),
    ('Recruiter response', [r'(?:i|we) would like to (?:speak|chat) with you',
                            r'(?:i|we)(?: am| are) (?:the )?recruiter (?:for|at)']),
    ('Application acknowledged', [r'received your application', r'thank you for applying']),
]
_CONTEXT = re.compile(r'\b(?:previously|in error|mistakenly|example|sample|hypothetical|quoted|disregard|ignore the (?:previous|earlier))\b', re.I)
_NEGATED_PREFIX = re.compile(r'\b(?:not|never|haven.t|hasn.t|didn.t|wouldn.t|cannot|can.t)\b[^.!?\n]{0,45}$', re.I)


def classify_message(body):
    if not isinstance(body, str) or not body.strip() or len(body) > 250000:
        return {'status': 'Needs review', 'quote': '', 'requires_review': True}
    # Reply history is evidence requiring interpretation, not a new event.
    quoted = bool(re.search(r'(?m)^\s*>|^On .{1,200}wrote:\s*$|^-{2,}\s*Original Message', body))
    findings = []
    for status, patterns in _RULES:
        for pattern in patterns:
            match = re.search(pattern, body, re.I)
            if match:
                prefix = body[max(0, match.start()-65):match.start()]
                findings.append((status, match, bool(_NEGATED_PREFIX.search(prefix))))
                break
    if not findings:
        return {'status': 'Needs review', 'quote': '', 'requires_review': True}
    # An acknowledgment commonly introduces the actual decision; it is not a
    # contradictory outcome. All competing substantive outcomes are ambiguous.
    substantive = [x for x in findings if x[0] != 'Application acknowledged']
    relevant = substantive or findings
    ambiguous = len(relevant) != 1 or quoted or bool(_CONTEXT.search(body)) or any(x[2] for x in relevant)
    quote = ' | '.join(body[m.start():m.end()] for _, m, _ in relevant)[:300]
    if ambiguous:
        return {'status': 'Needs review', 'quote': quote, 'requires_review': True}
    status = relevant[0][0]
    # An acknowledgment in the subject is not a decision. Unsupported decision
    # wording must surface for review instead of silently becoming an ack.
    if status == 'Application acknowledged' and re.search(
            r'\b(?:decided|decision|regret|unfortunately|unsuccessful|not selected|other candidates|other applicants)\b', body, re.I):
        return {'status': 'Needs review', 'quote': quote, 'requires_review': True}
    # Scheduling, offers, recruiter responses and requests need human review;
    # classifying them never grants permission to reply or accept an invitation.
    return {'status': status, 'quote': quote,
            'requires_review': status not in ('Rejected', 'Application acknowledged', 'Assessment / next step')}
