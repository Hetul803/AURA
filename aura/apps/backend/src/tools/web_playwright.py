from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import quote_plus
import re
from tools.browser_runtime import browser_manager
from aura import observer

FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'html'


def parse_search_html(html: str) -> dict:
    patterns = [
        r'<li><a href="([^"]+)">([^<]+)</a><p>([^<]+)</p></li>',
        r'<a[^>]+href="([^"]+)"[^>]*><h3[^>]*>([^<]+)</h3></a>.*?<[^>]*>([^<]{10,300})<',
    ]
    rows = []
    for pat in patterns:
        for hit in re.findall(pat, html, flags=re.S):
            url, title, snippet = hit
            rows.append({'title': title.strip(), 'url': url.strip(), 'snippet': snippet.strip()})
    dedup, seen = [], set()
    for r in rows:
        k = (r['title'], r['url'])
        if k in seen:
            continue
        seen.add(k)
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
        flights = [{'airline': None, 'price': None, 'link': None, 'time': None}]
    return {'ok': True, 'flights': flights}


def _real_search(query: str) -> dict:
    page = browser_manager.page_for('search')
    page.goto(f'https://duckduckgo.com/?q={quote_plus(query)}', wait_until='domcontentloaded', timeout=15000)
    html = page.content()
    out = parse_search_html(html)
    browser_manager.save_state('search')
    out['observation'] = observer.snapshot(page)
    return out


def _real_gmail_unread() -> dict:
    domain = 'mail_google_com'
    page = browser_manager.page_for(domain)
    page.goto('https://mail.google.com', wait_until='domcontentloaded', timeout=20000)
    snap = observer.snapshot(page)
    if snap['login_required']:
        browser_manager.save_state(domain)
        return {'ok': False, 'error': 'user_action_needed', 'message': 'Login required for Gmail', 'observation': snap}

    unread = observer.gmail_unread_count(page)
    summaries = []
    try:
        rows = page.locator('tr.zE').all()[:5]
        for r in rows:
            text = r.inner_text(timeout=500).strip().replace('\n', ' ')
            summaries.append(text)
    except Exception:
        pass
    browser_manager.save_state(domain)
    return {'ok': True, 'unread_count': unread, 'summary': summaries, 'observation': snap}


def _real_flights(query: str) -> dict:
    page = browser_manager.page_for('flights')
    page.goto(f'https://duckduckgo.com/?q={quote_plus(query)}', wait_until='domcontentloaded', timeout=15000)
    html = page.content()
    search = parse_search_html(html)
    flights = []
    for item in search.get('items', [])[:5]:
        flights.append({
            'airline': None,
            'price': None,
            'link': item.get('url'),
            'time': None,
            'title': item.get('title')
        })
    if not flights:
        flights = [{'airline': None, 'price': None, 'link': None, 'time': None, 'title': None}]
    browser_manager.save_state('flights')
    return {'ok': True, 'flights': flights, 'observation': observer.snapshot(page)}


def handle_web_action(step) -> dict:
    if step.action_type == 'NOOP':
        return {'ok': True, 'echo': step.args.get('echo') or step.args.get('message')}

    if step.action_type == 'WEB_NAVIGATE':
        url = step.args.get('url')
        domain = browser_manager.domain_for_url(url)
        page = browser_manager.page_for(domain)
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        browser_manager.save_state(domain)
        return {'ok': True, 'navigated_to': url, 'observation': observer.snapshot(page)}

    target = step.args.get('target')
    use_fixture = bool(step.args.get('use_fixture')) or os.getenv('AURA_FORCE_FIXTURES') == '1'

    if step.action_type == 'WEB_READ' and target == 'search':
        if use_fixture:
            return parse_search_html((FIXTURE / 'search_results.html').read_text(encoding='utf-8'))
        return _real_search(step.args.get('query', ''))

    if step.action_type == 'WEB_READ' and target == 'gmail_unread':
        if use_fixture:
            return parse_gmail_html((FIXTURE / 'gmail_unread.html').read_text(encoding='utf-8'))
        return _real_gmail_unread()

    if step.action_type == 'WEB_READ' and target == 'flights':
        if use_fixture:
            return parse_flights_html(step.args.get('html', ''))
        return _real_flights(step.args.get('query', 'flights'))

    return {'ok': False, 'error': 'unsupported'}
