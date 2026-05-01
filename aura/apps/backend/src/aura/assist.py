from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlparse

from llm.assist_client import classify_assist_request, generate_assist_draft
from .context_engine import legacy_assist_context, normalize_context, persist_context_snapshot
from .learning import query_relevant_memory
from .prefs import get_pref_value, set_pref
from .memory import write_memory
from tools.os_automation import capture_context, restore_target_and_paste
from tools.tool_result import failure, success
from tools.web_playwright import handle_web_action

SUPPORTED_ASSIST_KINDS = {'summarize', 'reply', 'rewrite', 'explain', 'answer', 'research_and_respond'}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def looks_like_assist_request(text: str) -> bool:
    lower = text.lower().strip()
    strong_markers = ['summarize', 'reply', 'respond', 'rewrite', 'reword', 'explain', 'answer', 'research']
    if any(marker in lower for marker in strong_markers):
        return True
    if lower.endswith(' this') or lower.startswith(('please ', 'can you ', 'help me ')):
        return any(token in lower for token in ['this', 'text', 'message', 'email', 'paragraph', 'clipboard', 'selected'])
    return False


def classify_assist_task(text: str) -> dict:
    intent = classify_assist_request(text)
    task_kind = intent.task_kind
    if task_kind not in SUPPORTED_ASSIST_KINDS:
        task_kind = 'summarize'
    return {
        'task_kind': task_kind,
        'source_text_present': intent.source_text_present,
        'intent_confidence': intent.intent_confidence,
        'needs_research': intent.needs_research,
        'style_hints': dict(intent.style_hints),
        'approval_required': intent.approval_required,
        'input_requirement': 'selection_or_clipboard',
        'pasteback_mode': intent.pasteback_mode,
        'reasoning_summary': intent.reasoning_summary,
        'provider': intent.provider,
        'model': intent.model,
        'fallback_used': intent.fallback_used,
        'original_text': text.strip(),
    }


def _memory_value(rows: list[dict], memory_key: str) -> str | None:
    for row in rows:
        if row.get('memory_key') == memory_key:
            return str(row.get('value'))
    return None


def extract_feedback_preferences(feedback: str | None) -> dict[str, str]:
    lower = (feedback or '').lower()
    prefs: dict[str, str] = {}
    if any(token in lower for token in ['more direct', 'be direct', 'less polished']):
        prefs['writing.tone'] = 'direct'
    if any(token in lower for token in ['more polished', 'warmer', 'friendlier']):
        prefs['writing.tone'] = 'polished'
    if any(token in lower for token in ['more detail', 'expand', 'longer']):
        prefs['writing.length'] = 'detailed'
    if any(token in lower for token in ['shorter', 'more concise', 'tighten', 'brief']):
        prefs['writing.length'] = 'concise'
    if any(token in lower for token in ['no research', 'don\'t research', 'not needed']) or 'unnecessary research' in lower:
        prefs['assist.research'] = 'avoid'
    if any(token in lower for token in ['research more', 'check sources', 'look it up']):
        prefs['assist.research'] = 'prefer'
    return prefs


def apply_feedback_preferences(feedback: str | None, task_kind: str | None = None):
    learned = extract_feedback_preferences(feedback)
    for key, value in learned.items():
        scoped_key = f'assist.{task_kind}.{key.split(".")[-1]}' if task_kind and key.startswith('writing.') else key
        set_pref(key, value)
        write_memory(key, value, tags=['preference', 'assist', 'feedback'], importance=4)
        if scoped_key != key:
            set_pref(scoped_key, value)
            write_memory(scoped_key, value, tags=['preference', 'assist', 'feedback'], importance=4)
    return learned


def learning_signals_for(task_kind: str) -> dict:
    relevant = query_relevant_memory(task_type='assist:writing', action_key='ASSIST_PASTE_BACK')
    prefs = relevant.get('preferences', [])
    workflow = relevant.get('workflow', [])
    safety = relevant.get('safety', [])
    drift_signals = [item for item in workflow if 'paste_target_changed' in str(item.get('pattern_key') or '') or 'target_drift' in str(item.get('pattern_key') or '')]
    exact_match_successes = [item for item in workflow if item.get('pattern_key') == 'paste_validation:exact_match' and item.get('success_count', 0) >= max(1, item.get('failure_count', 0))]
    clipboard_fallback_usage = [item for item in workflow if item.get('pattern_key') == 'capture_path:clipboard_fallback']
    signals = {
        'preferred_length': get_pref_value(f'assist.{task_kind}.length') or get_pref_value('writing.length') or _memory_value(prefs, 'writing.length') or 'concise',
        'preferred_tone': get_pref_value(f'assist.{task_kind}.tone') or get_pref_value('writing.tone') or _memory_value(prefs, 'writing.tone') or 'polished',
        'research_preference': get_pref_value(f'assist.{task_kind}.research') or get_pref_value('assist.research') or _memory_value(prefs, 'assist.research') or 'auto',
        'approval_required': True,
        'strict_paste_validation': any(item.get('policy') == 'revalidate_target' for item in safety),
        'cautious_paste_mode': any(item.get('policy') in {'require_confirmation', 'revalidate_target'} for item in safety) or len(drift_signals) >= 2,
        'preferred_capture_mode': 'clipboard_fallback' if clipboard_fallback_usage else 'selected_text',
        'paste_confidence': 'high' if exact_match_successes else 'normal',
        'recent_workflow_patterns': [item.get('pattern_key') for item in workflow[:3]],
    }
    return signals


def style_hints_for(task_kind: str, feedback: str | None = None) -> dict:
    signals = learning_signals_for(task_kind)
    hinted = extract_feedback_preferences(feedback)
    length = hinted.get('writing.length') or signals['preferred_length']
    tone = hinted.get('writing.tone') or signals['preferred_tone']
    return {'length': length, 'tone': tone, 'task_kind': task_kind}


def research_mode_for(task_kind: str, needs_research: bool, feedback: str | None = None) -> str:
    signals = learning_signals_for(task_kind)
    overrides = extract_feedback_preferences(feedback)
    research_pref = overrides.get('assist.research') or signals.get('research_preference') or 'auto'
    if research_pref == 'avoid' and task_kind not in {'research_and_respond'}:
        return 'none'
    if needs_research or research_pref == 'prefer' or task_kind == 'research_and_respond':
        return 'web_search'
    if task_kind in {'answer', 'explain'}:
        return 'page'
    return 'none'


def build_research_query(request_text: str, source_text: str, browser_title: str | None = None) -> str:
    base = re.sub(r'\s+', ' ', source_text or request_text).strip()
    if len(base) > 140:
        base = base[:140]
    if browser_title and browser_title.lower() not in base.lower():
        return f'{base} {browser_title}'.strip()
    return base


def gather_context(*, request_text: str, captured_context: dict, research_mode: str) -> dict:
    page_context = {
        'browser_url': captured_context.get('browser_url'),
        'browser_title': captured_context.get('browser_title'),
        'page_context': '',
        'sources': [],
        'key_points': [],
        'research_mode': research_mode,
        'search_used': False,
    }
    if captured_context.get('browser_url'):
        page_context['sources'].append(captured_context['browser_url'])
        title = captured_context.get('browser_title') or captured_context.get('window_title') or ''
        if title:
            page_context['page_context'] = f'Current page: {title}'
            page_context['key_points'].append(f'Current page context: {title}')

    if research_mode != 'web_search':
        return page_context

    query = build_research_query(request_text, captured_context.get('input_text', ''), captured_context.get('browser_title'))
    if not query:
        return page_context

    step = SimpleNamespace(action_type='WEB_READ', args={'target': 'search', 'query': query, 'use_fixture': os.getenv('AURA_FORCE_FIXTURES') == '1'})
    search = handle_web_action(step)
    if search.get('ok'):
        return {
            **page_context,
            'query': query,
            'search_used': True,
            'key_points': list(dict.fromkeys([*(page_context.get('key_points') or []), *(search.get('key_points') or [])]))[:4],
            'sources': list(dict.fromkeys([*(page_context.get('sources') or []), *(search.get('sources') or [])]))[:4],
            'search_results_count': search.get('search_results_count', 0),
        }
    return {**page_context, 'query': query, 'search_used': True, 'warnings': [search.get('error') or 'research_unavailable']}


def capture_structured_context() -> dict:
    captured = legacy_assist_context(persist_context_snapshot(normalize_context(capture_context(), source='assist')))
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
    request_text = (ctx.get('plan') or {}).get('context', {}).get('request_text') or ctx.get('text') or ''
    research = gather_context(request_text=request_text, captured_context=captured, research_mode=step.args.get('research_mode', 'none'))
    return success('ASSIST_RESEARCH_CONTEXT', result={'research_context': research}, observation={
        'research_mode': research.get('research_mode'),
        'research_sources_count': len(research.get('sources', [])),
        'research_used': bool(research.get('search_used') or research.get('page_context')),
    })


def draft_from_state(run_context: dict, feedback: str | None = None) -> dict:
    plan = run_context.get('plan') or {}
    assist_plan = plan.get('assist') or {}
    captured = run_context.get('captured_context') or ((run_context.get('assist') or {}).get('captured_context')) or {}
    research = run_context.get('research_context') or ((run_context.get('assist') or {}).get('research_context')) or {}
    task_kind = assist_plan.get('task_kind', 'summarize')
    learning_signals = learning_signals_for(task_kind)
    plan_styles = (plan.get('context') or {}).get('style_hints') or {}
    styles = {**plan_styles, **style_hints_for(task_kind, feedback=feedback)}
    retry_feedback = feedback or ((run_context.get('approval_state') or {}).get('feedback')) or ''
    generated = generate_assist_draft(
        task_kind=task_kind,
        source_text=captured.get('input_text', ''),
        request_text=run_context.get('text') or plan.get('context', {}).get('request_text') or '',
        research_context=research,
        style_hints=styles,
        retry_feedback=retry_feedback,
        learning_signals=learning_signals,
    )
    return {
        'draft_text': generated.draft_text,
        'task_kind': task_kind,
        'style_hints': dict(generated.style_signals_used or styles),
        'research_used': generated.research_used,
        'feedback': retry_feedback,
        'provider': generated.provider,
        'model': generated.model,
        'fallback_used': generated.fallback_used,
        'confidence': generated.confidence,
        'notes': generated.notes,
        'learning_signals_applied': learning_signals,
    }


def draft_step(step, run_context: dict | None = None) -> dict:
    try:
        draft = draft_from_state(run_context or {}, feedback=step.args.get('feedback'))
    except RuntimeError as exc:
        message = str(exc)
        return failure(
            'ASSIST_DRAFT',
            error=message,
            observation={'failure_class': 'assist_model_unavailable' if 'unavailable' in message else 'assist_generation_failed'},
            requires_user=True,
            retryable=False,
        )
    return success(
        'ASSIST_DRAFT',
        result={'draft': draft},
        observation={
            'draft_ready': True,
            'draft_length': len(draft['draft_text']),
            'generation_provider': draft['provider'],
            'generation_model': draft['model'],
            'generation_confidence': draft['confidence'],
        },
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
    learned = ((ctx.get('draft_state') or {}).get('learning_signals_applied') or {})
    strict = bool(learned.get('strict_paste_validation'))
    cautious = bool(learned.get('cautious_paste_mode'))
    result = restore_target_and_paste(final_text, target, strict=strict, cautious=cautious)
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
