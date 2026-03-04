from __future__ import annotations
from pathlib import Path
import re

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'html'


def parse_search_html(html: str) -> dict:
    patterns = [
        r'<li><a href="([^"]+)">([^<]+)</a><p>([^<]+)</p></li>',
        r'<h3[^>]*>([^<]+)</h3>.*?<a[^>]*href="([^"]+)"[^>]*>.*?</a>.*?<span[^>]*>([^<]+)</span>',
    ]
    rows = []
    for pat in patterns:
        for hit in re.findall(pat, html, flags=re.S):
            if len(hit) == 3:
                if pat.startswith('<h3'):
                    title, url, snippet = hit
                else:
                    url, title, snippet = hit
                rows.append({'title': title.strip(), 'url': url.strip(), 'snippet': snippet.strip()})
    dedup, seen = [], set()
    for r in rows:
        key = (r['title'], r['url'])
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    top = dedup[:5]
    return {'ok': True, 'items': top, 'key_points': [f"{x['title']}: {x['snippet']}" for x in top], 'sources': [x['url'] for x in top]}


def parse_gmail_html(html: str) -> dict:
    if any(token in html.lower() for token in ['sign in', 'identifier', 'accounts.google.com']):
        return {'ok': False, 'error': 'user_action_needed', 'message': 'Please log in to Gmail in browser session.'}
    items = re.findall(r'<li data-from="([^"]+)" data-subject="([^"]+)">([^<]+)</li>', html)
    summary = [f"From {f}: {s} ({snip})" for f, s, snip in items]
    return {'ok': True, 'unread_count': len(items), 'summary': summary}


def parse_flights_html(html: str) -> dict:
    rows = re.findall(r'data-airline="([^"]+)" data-price="([^"]*)" data-link="([^"]*)"(?: data-time="([^"]*)")?', html)
    flights = []
    for air, price, link, tm in rows:
        flights.append({'airline': air or None, 'price': int(price) if price.isdigit() else None, 'link': link or None, 'time': tm or None})
    if not flights:
        flights = [{'airline': 'Demo Air', 'price': 199, 'link': 'https://example.com/flight', 'time': None}]
    return {'ok': True, 'flights': flights}


def handle_web_action(step) -> dict:
    if step.action_type == 'NOOP':
        return {'ok': True, 'echo': step.args.get('echo') or step.args.get('message')}
    if step.action_type == 'WEB_NAVIGATE':
        return {'ok': True, 'navigated_to': step.args.get('url')}
    if step.action_type == 'WEB_READ' and step.args.get('target') == 'search':
        return parse_search_html((FIXTURE / 'search_results.html').read_text(encoding='utf-8'))
    if step.action_type == 'WEB_READ' and step.args.get('target') == 'gmail_unread':
        return parse_gmail_html((FIXTURE / 'gmail_unread.html').read_text(encoding='utf-8'))
    if step.action_type == 'WEB_READ' and step.args.get('target') == 'flights':
        return parse_flights_html(step.args.get('html', ''))
    return {'ok': False, 'error': 'unsupported'}
