from __future__ import annotations

import re
from urllib.parse import urlparse

from .learning import list_reflection_records, list_workflow_memory, resolve_assist_profile

ACTION_META = {
    'summarize': {'label': 'Summarize', 'command': 'Summarize this'},
    'reply': {'label': 'Reply', 'command': 'Draft a reply to this'},
    'rewrite': {'label': 'Rewrite', 'command': 'Rewrite this better'},
    'explain': {'label': 'Explain', 'command': 'Explain this'},
    'answer': {'label': 'Answer', 'command': 'Answer this question'},
}
SUGGESTION_THRESHOLD = 0.58
MAX_SUGGESTIONS = 3


def _domain(context: dict) -> str | None:
    browser_url = context.get('browser_url') or ((context.get('target_fingerprint') or {}).get('browser_url'))
    if browser_url:
        return urlparse(browser_url).netloc or None
    return (context.get('target_fingerprint') or {}).get('browser_domain')


def _normalized_app(app_name: str | None) -> str:
    return ''.join(ch.lower() for ch in str(app_name or '') if ch.isalnum())


def _context_features(context: dict) -> dict:
    text = (context.get('input_text') or '').strip()
    words = re.findall(r"\b[\w']+\b", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    lower = text.lower()
    domain = _domain(context)
    app_name = context.get('active_app') or ((context.get('target_fingerprint') or {}).get('app_name')) or ''
    normalized_app = _normalized_app(app_name)
    question_words = ('why', 'how', 'what', 'when', 'where', 'who', 'which', 'can you', 'could you')
    email_greeting = bool(re.search(r'^(hi|hello|hey)\b', lower))
    email_signoff = bool(re.search(r'(thanks|best|regards|sincerely)[\s,!.\-]*$', lower))
    email_headers = any(line.startswith(('From:', 'Subject:', 'To:', 'Cc:')) for line in lines)
    email_like = email_headers or (
        len(lines) >= 3
        and (email_greeting or email_signoff or '@' in text)
    ) or ('mail' in normalized_app) or bool(domain and 'mail' in domain)
    document_like = any(token in normalized_app for token in ['notes', 'docs', 'word', 'pages', 'notion', 'obsidian', 'editor', 'cursor'])
    browser_like = bool(domain) and 'mail' not in (domain or '')
    question_detected = '?' in text or any(lower.startswith(token) or f' {token} ' in lower for token in question_words)
    explain_keywords = any(token in lower for token in ['explain', 'why', 'how', 'what does', 'walk me through'])
    return {
        'text': text,
        'word_count': len(words),
        'line_count': len(lines),
        'has_text': bool(text),
        'question_detected': question_detected,
        'email_like': email_like,
        'document_like': document_like,
        'browser_like': browser_like,
        'normalized_app': normalized_app,
        'domain': domain,
        'explain_keywords': explain_keywords,
        'has_long_text': len(words) >= 80,
        'has_medium_text': 20 <= len(words) <= 180,
    }


def _matching_recent_history(*, action: str, active_app: str | None, domain: str | None) -> tuple[int, int]:
    support = 0
    rejection = 0
    for reflection in list_reflection_records(limit=25):
        context = reflection.get('normalized_context') or {}
        match_strength = 0
        if active_app and _normalized_app(context.get('active_app')) == _normalized_app(active_app):
            match_strength += 1
        if domain and context.get('domain') == domain:
            match_strength += 1
        if match_strength <= 0:
            continue
        patterns = reflection.get('candidate_workflow_patterns') or []
        selected = any((item.get('pattern_key') or '') == f'task_kind:{action}' for item in patterns)
        if not selected:
            continue
        if reflection.get('outcome') == 'rejected' or any((item.get('pattern_key') or '') == 'approval:rejected' for item in patterns):
            rejection += match_strength
        else:
            support += match_strength
    return support, rejection


def _workflow_bias(action: str) -> tuple[float, float]:
    positive = 0.0
    negative = 0.0
    for row in list_workflow_memory():
        if row.get('task_type') != 'assist:writing':
            continue
        pattern_key = row.get('pattern_key') or ''
        if pattern_key == f'task_kind:{action}':
            delta = row.get('success_count', 0) - row.get('failure_count', 0)
            if delta > 0:
                positive += min(0.16, 0.03 * delta)
            elif delta < 0:
                negative += min(0.18, 0.04 * abs(delta))
        if pattern_key == f'proactive:{action}:selected':
            delta = row.get('success_count', 0) - row.get('failure_count', 0)
            if delta > 0:
                positive += min(0.18, 0.05 * delta)
            elif delta < 0:
                negative += min(0.2, 0.06 * abs(delta))
        if pattern_key == f'proactive:{action}:rejected':
            negative += min(0.22, 0.05 * (row.get('success_count', 0) + row.get('failure_count', 0)))
    return positive, negative


def _add_signal(signals: list[dict], name: str, weight: float, detail: str):
    signals.append({'name': name, 'weight': round(weight, 2), 'detail': detail})


def _score_action(action: str, features: dict, profile: dict) -> dict:
    signals: list[dict] = []
    if not features['has_text']:
        return {'action': action, 'confidence': 0.0, 'reason': 'No captured text is available.', 'signals_used': []}

    if action == 'reply':
        if features['email_like']:
            _add_signal(signals, 'email_context', 0.34, 'The captured text looks like a message or email thread.')
        if 'mail' in features['normalized_app'] or (features['domain'] and 'mail' in features['domain']):
            _add_signal(signals, 'mail_surface', 0.28, 'The current app/domain looks like mail or messaging.')
        if 8 <= features['word_count'] <= 220:
            _add_signal(signals, 'reply_length_fit', 0.08, 'The text length fits a reply workflow.')
    elif action == 'summarize':
        if features['has_long_text']:
            _add_signal(signals, 'long_text', 0.34, 'There is enough text here to benefit from summarization.')
        if features['document_like'] or features['browser_like']:
            _add_signal(signals, 'document_surface', 0.16, 'The current surface looks like reading or note-taking.')
        if not features['question_detected']:
            _add_signal(signals, 'non_question_text', 0.06, 'The text reads more like content than a direct question.')
    elif action == 'rewrite':
        if features['document_like']:
            _add_signal(signals, 'editing_surface', 0.24, 'The current app looks like a writing or editing surface.')
        if features['has_medium_text']:
            _add_signal(signals, 'editable_length', 0.18, 'The text length fits a rewrite request.')
        if not features['question_detected']:
            _add_signal(signals, 'statement_text', 0.08, 'The captured text reads like prose that can be polished.')
    elif action == 'explain':
        if features['question_detected']:
            _add_signal(signals, 'question_detected', 0.2, 'The captured text includes a question or prompt.')
        if features['explain_keywords']:
            _add_signal(signals, 'explain_keywords', 0.22, 'The text contains explain/why/how cues.')
        if features['browser_like']:
            _add_signal(signals, 'browser_context', 0.12, 'The current browser context suggests reading or research.')
    elif action == 'answer':
        if features['question_detected']:
            _add_signal(signals, 'question_detected', 0.28, 'The captured text looks like a question to answer.')
        if features['browser_like']:
            _add_signal(signals, 'browser_context', 0.18, 'The browser context suggests Q&A or lookup work.')
        if profile['style_profile']['research_tendency']['value'] == 'prefer':
            _add_signal(signals, 'research_preferred', 0.11, 'Past behavior suggests source-backed answers are preferred.')

    positive, negative = _workflow_bias(action)
    if positive:
        _add_signal(signals, 'history_support', positive, f'Past successful runs in similar contexts lean toward {action}.')
    if negative:
        _add_signal(signals, 'history_penalty', -negative, f'Past feedback suggests caution when proposing {action}.')

    recent_support, recent_reject = _matching_recent_history(action=action, active_app=features['normalized_app'] or None, domain=features['domain'])
    if recent_support:
        _add_signal(signals, 'recent_context_support', min(0.14, 0.05 * recent_support), f'Recent similar contexts used {action} successfully.')
    if recent_reject:
        _add_signal(signals, 'recent_context_penalty', -min(0.16, 0.06 * recent_reject), f'Recent similar contexts rejected {action}.')

    positive_weight = sum(item['weight'] for item in signals if item['weight'] > 0)
    negative_weight = abs(sum(item['weight'] for item in signals if item['weight'] < 0))
    raw_score = positive_weight - negative_weight
    confidence = round(max(0.0, min(0.99, raw_score / 0.95)), 2)
    positive_signals = [item for item in signals if item['weight'] > 0]
    reason_parts = [item['detail'] for item in sorted(positive_signals, key=lambda item: item['weight'], reverse=True)[:2]]
    reason = ' '.join(reason_parts) if reason_parts else 'Not enough evidence for a confident suggestion.'
    return {
        'action': action,
        'label': ACTION_META[action]['label'],
        'command': ACTION_META[action]['command'],
        'confidence': confidence,
        'reason': reason,
        'signals_used': sorted(signals, key=lambda item: abs(item['weight']), reverse=True),
    }


def proactive_suggestions_for_context(captured_context: dict) -> dict:
    context = captured_context or {}
    features = _context_features(context)
    profile = resolve_assist_profile(
        task_kind='summarize',
        active_app=features['normalized_app'] or None,
        domain=features['domain'],
    )
    scored = [_score_action(action, features, profile) for action in ACTION_META]
    ranked = [
        suggestion for suggestion in sorted(scored, key=lambda item: item['confidence'], reverse=True)
        if suggestion['confidence'] >= SUGGESTION_THRESHOLD and len([signal for signal in suggestion['signals_used'] if signal['weight'] > 0]) >= 2
    ][:MAX_SUGGESTIONS]
    return {
        'captured_context': context,
        'profile': profile,
        'suggestions': ranked,
        'features': {
            'word_count': features['word_count'],
            'question_detected': features['question_detected'],
            'email_like': features['email_like'],
            'document_like': features['document_like'],
            'domain': features['domain'],
            'active_app': context.get('active_app'),
        },
    }
