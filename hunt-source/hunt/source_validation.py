"""Validate a complete employer ATS snapshot before changing job presence.

Provider responses remain untrusted data. A valid JSON error envelope is not an
empty board, and HTTPS alone does not establish an employer posting's identity.
This module is pure and makes no network calls.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit, unquote

_PROVIDER_HOSTS = {
    'ashby': {'jobs.ashbyhq.com'},
    'greenhouse': {'boards.greenhouse.io', 'job-boards.greenhouse.io',
                   'job-boards.eu.greenhouse.io'},
    'lever': {'jobs.lever.co', 'jobs.eu.lever.co'},
}
_TRACKING = {'source', 'ref', 'referrer', 'gh_src', 'lever-source', 'lever-origin'}


def _config(feed):
    if not isinstance(feed, dict) or feed.get('kind') not in _PROVIDER_HOSTS:
        raise ValueError('Unsupported ATS provider')
    board = feed.get('board')
    if not isinstance(board, str) or not re.fullmatch(r'[a-z0-9-]{1,80}', board):
        raise ValueError('Invalid ATS board')
    return feed['kind'], board


def validate_posting_url(feed, url, posting_id=None):
    """Return a safe canonical URL bound to the configured provider and board.

    A provider feed can intentionally point at a company's custom careers site.
    Such hosts require an explicit ``allowed_posting_hosts`` entry in trusted
    source configuration; a response cannot extend this allowlist itself.
    """
    kind, board = _config(feed)
    if not isinstance(url, str) or len(url) > 4096 or any(ord(c) < 33 for c in url) or '\\' in url:
        raise ValueError('Invalid posting URL')
    try:
        p = urlsplit(url)
        port = p.port
    except ValueError:
        raise ValueError('Invalid posting URL') from None
    if p.scheme != 'https' or not p.hostname or p.username or p.password or port not in (None, 443):
        raise ValueError('Posting URL must use an approved HTTPS origin')
    host = p.hostname.lower()
    allowed = feed.get('allowed_posting_hosts', [])
    if not isinstance(allowed, (list, tuple)) or any(not isinstance(x, str) or not re.fullmatch(r'[a-z0-9.-]+', x) for x in allowed):
        raise ValueError('Invalid configured posting hosts')
    if host in _PROVIDER_HOSTS[kind]:
        parts = [unquote(x) for x in p.path.strip('/').split('/')]
        expected = [board, 'jobs', str(posting_id)] if kind == 'greenhouse' else [board, str(posting_id)]
        # Check full path structure even when a caller has no posting ID.
        required_len = 3 if kind == 'greenhouse' else 2
        if len(parts) != required_len or parts[0] != board or (kind == 'greenhouse' and parts[1] != 'jobs'):
            raise ValueError('Posting URL does not belong to configured ATS board')
        if any(x in ('', '.', '..') or '/' in x or '\\' in x for x in parts):
            raise ValueError('Invalid ATS posting path')
        if posting_id is not None and parts != expected:
            raise ValueError('Posting URL and ATS posting ID disagree')
    elif host not in allowed:
        raise ValueError('Unverified posting host')
    # Keep non-tracking query values: employer links can use job IDs in a query.
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in _TRACKING]
    return urlunsplit(('https', host, p.path.rstrip('/'), urlencode(query), ''))


def validate_feed(feed, data):
    """Validate a complete feed, returning its unmodified list of job records.

    Validation deliberately occurs before relevance filtering: silently dropping
    malformed records would turn an incomplete snapshot into false closures.
    """
    kind, _ = _config(feed)
    if kind == 'lever':
        jobs = data if isinstance(data, list) else None
    else:
        jobs = data.get('jobs') if isinstance(data, dict) else None
    if not isinstance(jobs, list) or len(jobs) > 20000:
        raise ValueError('Invalid or incomplete ATS feed envelope')
    if kind == 'greenhouse' and isinstance(data.get('meta'), dict) and 'total' in data['meta']:
        total = data['meta']['total']
        if type(total) is not int or total != len(jobs):
            raise ValueError('Incomplete Greenhouse board snapshot')
    seen = set()
    for item in jobs:
        if not isinstance(item, dict):
            raise ValueError('Invalid ATS job record')
        ident = item.get('id')
        if isinstance(ident, bool) or not isinstance(ident, (int, str)) or not str(ident).strip() or len(str(ident)) > 200:
            raise ValueError('Missing or invalid ATS posting ID')
        if str(ident) in seen:
            raise ValueError('Duplicate ATS posting ID in board snapshot')
        seen.add(str(ident))
        title = item.get('text') if kind == 'lever' else item.get('title')
        if not isinstance(title, str) or not title.strip() or len(title) > 1000:
            raise ValueError('Missing or invalid ATS job title')
        if kind == 'greenhouse':
            loc = item.get('location')
            if not isinstance(loc, dict) or not isinstance(loc.get('name'), str):
                raise ValueError('Invalid Greenhouse location')
        elif kind == 'ashby':
            if not isinstance(item.get('location'), str):
                raise ValueError('Invalid Ashby location')
        else:
            cats = item.get('categories')
            if not isinstance(cats, dict) or not isinstance(cats.get('location'), str):
                raise ValueError('Invalid Lever location')
        field = {'greenhouse': 'absolute_url', 'ashby': 'jobUrl', 'lever': 'hostedUrl'}[kind]
        validate_posting_url(feed, item.get(field), ident)
    return jobs
