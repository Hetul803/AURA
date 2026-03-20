from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlparse

from .learning import query_relevant_memory
from .prefs import get_pref_value
from tools.os_automation import capture_context, restore_target_and_paste
from tools.tool_result import failure, success
from tools.web_playwright import handle_web_action


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def classify_assist_task(text: str) -> dict:
    original = text.strip()
    lower = original.lower()
    if any(token in lower for token in ['rewrite', 'rewrite this', 'make this better', 'polish this']):
        task_kind = 'rewrite'
    elif any(token in lower for token in ['reply', 'respond', 'draft a reply']):
        task_kind = 'reply'
    elif any(token in lower for token in ['explain', 'what does this mean']):
        task_kind = 'explain'
    elif any(token in lower for token in ['answer', 'research']) or '?' in original:
        task_kind = 'answer'
    else:
        task_kind = 'summarize'

    explicit_research = any(token in lower for token in ['research', 'look up', 'find sources', 'search'])
    needs_research = explicit_research or task_kind == 'answer'
    research_mode = 'web_search' if needs_research else 'page'
    if task_kind in {'rewrite', 'reply', 'summarize'} and not explicit_research:
        research_mode = 'none'

    return {
        'task_kind': task_kind,
        'needs_research': needs_research,
        'research_mode': research_mode,
        'approval_required': True,
        'input_requirement': 'selection_or_clipboard',
        'original_text': original,
    }


def style_hints_for(task_kind: str) -> dict:
    relevant = query_relevant_memory(task_type='assist:writing')

    def _memory_value(memory_key: str) -> str | None:
        for row in relevant.get('preferences', []):
            if row.get('memory_key') == memory_key:
                return str(row.get('value'))
        return None

    length = (
        get_pref_value(f'assist.{task_kind}.length')
        or get_pref_value('assist.writing.length')
        or get_pref_value('writing.length')
        or _memory_value('writing.length')
        or 'concise'
    )
    tone = (
        get_pref_value(f'assist.{task_kind}.tone')
        or get_pref_value('assist.writing.tone')
        or get_pref_value('writing.tone')
        or _memory_value('writing.tone')
        or 'polished'
    )
    return {'length': length, 'tone': tone, 'task_kind': task_kind}


def _clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '')).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+', _clean_text(text))
    return [part.strip() for part in parts if part.strip()]


def _truncate(text: str, limit: int = 220) -> str:
    text = _clean_text(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + '…'


def _top_points(text: str, limit: int = 3) -> list[str]:
    points: list[str] = []
    for sentence in _sentences(text):
        points.append(sentence)
        if len(points) >= limit:
            break
    if not points and _clean_text(text):
        points = [_truncate(text, 180)]
    return points


def _research_summary(research: dict) -> str:
    if not research:
        return ''
    notes = list(research.get('key_points') or [])
    if not notes and research.get('page_context'):
        notes = [research['page_context']]
    return ' '.join(_truncate(note, 160) for note in notes[:2]).strip()


def _polish(sentence: str, tone: str) -> str:
    sentence = sentence.strip()
    if not sentence:
        return sentence
    if tone == 'direct':
        return sentence
    if sentence.endswith('.'):
        return sentence
    return sentence + '.'


def generate_draft(*, task_kind: str, input_text: str, style_hints: dict, research: dict | None = None, feedback: str | None = None) -> dict:
    clean = _clean_text(input_text)
    tone = style_hints.get('tone', 'polished')
    length = style_hints.get('length', 'concise')
    points = _top_points(clean, limit=4 if length == 'detailed' else 2)
    research_note = _research_summary(research or {})
    feedback_note = _clean_text(feedback or '')

    if task_kind == 'summarize':
        lead = 'Here’s the short version:' if length == 'concise' else 'Here’s a clear summary:'
        body = ' '.join(points)
        if length == 'detailed' and len(_sentences(clean)) > len(points):
            remainder = _sentences(clean)[len(points):len(points) + 2]
            if remainder:
                body = f"{body} {' '.join(remainder)}"
        text = f"{lead} {_polish(body, tone)}"
    elif task_kind == 'explain':
        lead = 'In plain terms,' if tone == 'direct' else 'Here’s what this is saying:'
        body = ' '.join(points)
        if research_note:
            body = f"{body} {research_note}"
        text = f"{lead} {_polish(body, tone)}"
    elif task_kind == 'rewrite':
        rewritten = clean
        rewritten = re.sub(r'\bi\b', 'I', rewritten)
        rewritten = rewritten[0].upper() + rewritten[1:] if rewritten else rewritten
        if tone == 'polished':
            rewritten = rewritten.replace('can\'t', 'cannot').replace("don\'t", 'do not')
        if length == 'concise' and len(rewritten) > 220:
            rewritten = _truncate(rewritten, 220)
        text = rewritten
    elif task_kind == 'reply':
        opener = 'Thanks for sending this.' if tone == 'polished' else 'Thanks for this.'
        if clean.endswith('?'):
            response = 'My quick take is that this makes sense, and I can help with the next step.'
        else:
            response = 'I reviewed it and I’m aligned on the next step.' if tone == 'polished' else 'I reviewed it and I’m on it.'
        if points:
            response = f"{response} { _polish('The key point is ' + points[0].rstrip('.'), tone)}"
        if research_note:
            response = f"{response} { _polish('I also checked the relevant context: ' + research_note, tone)}"
        closing = 'I’ll follow up shortly.' if length == 'concise' else 'If you want, I can turn this into a more detailed follow-up as well.'
        text = f"{opener} {response} {closing}".strip()
    else:  # answer
        opener = 'Answer:' if tone == 'direct' else 'Here’s the best answer I can draft:'
        answer_bits = points[:1] or [_truncate(clean, 140)]
        body = answer_bits[0]
        if research_note:
            body = f"{body} {research_note}".strip()
        if length == 'detailed' and len(points) > 1:
            body = f"{body} {' '.join(points[1:3])}".strip()
        text = f"{opener} {_polish(body, tone)}"

    if feedback_note:
        if 'short' in feedback_note.lower() and len(text) > 180:
            text = _truncate(text, 180)
        elif 'more detail' in feedback_note.lower() and task_kind != 'rewrite':
            extras = _sentences(clean)[1:3]
            if extras:
                text = f"{text} {' '.join(extras)}"

    return {
        'text': _clean_text(text),
        'style_hints': {'length': length, 'tone': tone},
        'task_kind': task_kind,
        'research_used': bool(research_note),
    }


def build_research_query(text: str, browser_title: str | None = None) -> str:
    base = _clean_text(text)
    if len(base) > 120:
        base = base[:120]
    if browser_title and browser_title.lower() not in base.lower():
        return f"{base} {browser_title}".strip()
    return base


def gather_context(*, captured_context: dict, research_mode: str) -> dict:
    page_context = {
        'browser_url': captured_context.get('browser_url'),
        'browser_title': captured_context.get('browser_title'),
        'page_context': '',
        'sources': [],
        'key_points': [],
        'research_mode': research_mode,
    }
    if captured_context.get('browser_url'):
        page_context['sources'].append(captured_context['browser_url'])
        title = captured_context.get('browser_title') or captured_context.get('window_title') or ''
        if title:
            page_context['page_context'] = f"Current page: {title}"
            page_context['key_points'].append(f"Current page context: {title}")

    if research_mode != 'web_search':
        return page_context

    query = build_research_query(
        captured_context.get('input_text', ''),
        captured_context.get('browser_title'),
    )
    if not query:
        return page_context

    step = SimpleNamespace(action_type='WEB_READ', args={'target': 'search', 'query': query, 'use_fixture': os.getenv('AURA_FORCE_FIXTURES') == '1'})
    search = handle_web_action(step)
    if search.get('ok'):
        return {
            **page_context,
            'query': query,
            'key_points': list(dict.fromkeys([*(page_context.get('key_points') or []), *(search.get('key_points') or [])]))[:4],
            'sources': list(dict.fromkeys([*(page_context.get('sources') or []), *(search.get('sources') or [])]))[:4],
            'search_results_count': search.get('search_results_count', 0),
        }
    return {**page_context, 'query': query, 'warnings': [search.get('error') or 'research_unavailable']}


def capture_structured_context() -> dict:
    captured = capture_context()
    if not captured.get('ok'):
        return failure(
            'ASSIST_CAPTURE_CONTEXT',
            error=captured.get('error') or 'context_capture_failed',
            observation=captured,
            result={'captured_context': captured},
            requires_user=not captured.get('input_text'),
            retryable=True,
        )
    return success('ASSIST_CAPTURE_CONTEXT', result={'captured_context': captured}, observation=captured)


def gather_structured_context(step, run_context: dict | None = None) -> dict:
    ctx = run_context or {}
    captured = ctx.get('captured_context') or ((ctx.get('assist') or {}).get('captured_context')) or {}
    research = gather_context(captured_context=captured, research_mode=step.args.get('research_mode', 'none'))
    return success('ASSIST_RESEARCH_CONTEXT', result={'research_context': research}, observation={
        'research_mode': research.get('research_mode'),
        'research_sources_count': len(research.get('sources', [])),
    })


def draft_from_state(run_context: dict, feedback: str | None = None) -> dict:
    plan = run_context.get('plan') or {}
    assist_plan = plan.get('assist') or {}
    captured = run_context.get('captured_context') or ((run_context.get('assist') or {}).get('captured_context')) or {}
    research = run_context.get('research_context') or ((run_context.get('assist') or {}).get('research_context')) or {}
    styles = (plan.get('context') or {}).get('style_hints') or style_hints_for(assist_plan.get('task_kind', 'summarize'))
    draft = generate_draft(
        task_kind=assist_plan.get('task_kind', 'summarize'),
        input_text=captured.get('input_text', ''),
        style_hints=styles,
        research=research,
        feedback=feedback or ((run_context.get('approval_state') or {}).get('feedback')),
    )
    return {
        'draft_text': draft['text'],
        'task_kind': draft['task_kind'],
        'style_hints': draft['style_hints'],
        'research_used': draft['research_used'],
        'feedback': feedback or '',
    }


def draft_step(step, run_context: dict | None = None) -> dict:
    draft = draft_from_state(run_context or {}, feedback=step.args.get('feedback'))
    return success(
        'ASSIST_DRAFT',
        result={'draft': draft},
        observation={'draft_ready': True, 'draft_length': len(draft['draft_text'])},
    )


def wait_for_approval_step(run_context: dict | None = None) -> dict:
    state = (run_context or {}).get('approval_state') or {}
    if state.get('status') == 'approved' and state.get('final_text'):
        return success('ASSIST_WAIT_APPROVAL', result={'approval_state': state}, observation={'approval_required': False, 'approval_status': 'approved'})
    if state.get('status') == 'rejected':
        return failure('ASSIST_WAIT_APPROVAL', error='draft_rejected', observation={'approval_status': 'rejected', 'failure_class': 'approval_rejected'}, result={'approval_state': state}, retryable=False)
    return failure(
        'ASSIST_WAIT_APPROVAL',
        error='approval_required',
        observation={'approval_required': True, 'approval_status': state.get('status', 'pending'), 'failure_class': 'approval_required'},
        result={'approval_state': state},
        requires_user=True,
        retryable=True,
    )


def paste_back_step(run_context: dict | None = None) -> dict:
    ctx = run_context or {}
    approval = ctx.get('approval_state') or {}
    final_text = approval.get('final_text') or approval.get('edited_text') or approval.get('draft_text') or ''
    target = ((ctx.get('captured_context') or {}).get('paste_target')) or {}
    if not final_text:
        return failure('ASSIST_PASTE_BACK', error='missing_approved_text', observation={'failure_class': 'missing_approved_text'})
    result = restore_target_and_paste(final_text, target)
    result['action'] = 'ASSIST_PASTE_BACK'
    return result


def handle_assist_action(step, run_context: dict | None = None) -> dict:
    if step.action_type == 'ASSIST_CAPTURE_CONTEXT':
        return capture_structured_context()
    if step.action_type == 'ASSIST_RESEARCH_CONTEXT':
        return gather_structured_context(step, run_context)
    if step.action_type == 'ASSIST_DRAFT':
        return draft_step(step, run_context)
    if step.action_type == 'ASSIST_WAIT_APPROVAL':
        return wait_for_approval_step(run_context)
    if step.action_type == 'ASSIST_PASTE_BACK':
        return paste_back_step(run_context)
    return failure(step.action_type, error='unsupported_assist_action')
