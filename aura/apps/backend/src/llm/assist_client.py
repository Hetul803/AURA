from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from llm.ollama_client import default_ollama_model, ollama_available, ollama_generate, parse_json_response

AssistTaskKind = Literal['summarize', 'reply', 'rewrite', 'explain', 'answer', 'research_and_respond']


class AssistIntentResult(BaseModel):
    task_kind: AssistTaskKind
    source_text_present: bool
    intent_confidence: float = Field(ge=0.0, le=1.0)
    needs_research: bool
    style_hints: dict[str, str] = Field(default_factory=dict)
    approval_required: bool = True
    pasteback_mode: str = 'reactivate_validate_paste'
    reasoning_summary: str = ''
    provider: str = 'parser'
    model: str | None = None
    fallback_used: bool = False


class AssistDraftResult(BaseModel):
    draft_text: str
    style_signals_used: dict[str, str] = Field(default_factory=dict)
    research_used: bool = False
    provider: str
    model: str
    fallback_used: bool = False
    confidence: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


INTENT_SYSTEM_PROMPT = (
    'You classify only assisted-writing requests. '
    'Return strict JSON with keys: task_kind, source_text_present, intent_confidence, needs_research, '
    'style_hints, approval_required, pasteback_mode, reasoning_summary. '
    'Allowed task_kind values: summarize, reply, rewrite, explain, answer, research_and_respond. '
    'Use research_and_respond only when the user explicitly asks for research before responding. '
    'Do not add markdown.'
)

DRAFT_SYSTEM_PROMPT = (
    'You draft high-quality assisted-writing output. '
    'Return strict JSON with keys: draft_text, style_signals_used, research_used, confidence, notes. '
    'The draft_text must be natural and useful, not robotic. '
    'Honor the requested task and style. '
    'Use only provided research/context. '
    'Do not mention being an AI. '
    'Do not add markdown fences.'
)


def assist_model_metadata() -> dict:
    if not ollama_available():
        return {'available': False, 'provider': 'ollama', 'model': default_ollama_model()}
    return {'available': True, 'provider': 'ollama', 'model': default_ollama_model()}


def _json_prompt(payload: dict) -> str:
    import json
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _parser_style(text: str) -> dict[str, str]:
    lower = text.lower()
    tone = 'direct' if any(token in lower for token in ['direct', 'blunt', 'plain']) else 'polished'
    length = 'detailed' if any(token in lower for token in ['detailed', 'more detail', 'thorough']) else 'concise'
    return {'tone': tone, 'length': length}


def classify_assist_with_parser(text: str) -> AssistIntentResult:
    lower = text.lower().strip()
    scores = {
        'summarize': 0,
        'reply': 0,
        'rewrite': 0,
        'explain': 0,
        'answer': 0,
        'research_and_respond': 0,
    }
    phrase_weights = {
        'summarize': ['summarize', 'summary', 'short version', 'tl;dr'],
        'reply': ['reply', 'respond', 'send back', 'write back', 'draft a reply'],
        'rewrite': ['rewrite', 'reword', 'polish', 'make this better', 'improve this'],
        'explain': ['explain', 'what does this mean', 'clarify', 'break this down'],
        'answer': ['answer', 'what should i say', 'what should i send'],
        'research_and_respond': ['research', 'look up', 'find sources', 'research and respond'],
    }
    for kind, phrases in phrase_weights.items():
        for phrase in phrases:
            if phrase in lower:
                scores[kind] += 3
    if '?' in text:
        scores['answer'] += 2
    if 'reply' in lower and 'research' in lower:
        scores['research_and_respond'] += 2
    if 'selected text' in lower or 'clipboard' in lower or 'this' in lower:
        source_text_present = True
    else:
        source_text_present = bool(re.search(r'".+"|\'.+\'', text))
    if 'research' in lower and max(scores.values()) < 4:
        scores['research_and_respond'] += 2

    task_kind = max(scores, key=scores.get)
    top = scores[task_kind]
    second = max([score for kind, score in scores.items() if kind != task_kind] or [0])
    confidence = 0.55 if top <= 0 else min(0.95, 0.55 + (top * 0.08) - (second * 0.03))
    needs_research = task_kind in {'research_and_respond'} or ('research' in lower and task_kind in {'answer', 'reply'})
    if task_kind == 'answer' and any(token in lower for token in ['look up', 'check online', 'find sources']):
        needs_research = True
        task_kind = 'research_and_respond'
    return AssistIntentResult(
        task_kind=task_kind,
        source_text_present=source_text_present,
        intent_confidence=round(max(0.2, min(confidence, 0.95)), 2),
        needs_research=needs_research,
        style_hints=_parser_style(text),
        approval_required=True,
        pasteback_mode='reactivate_validate_paste',
        reasoning_summary='parser_fallback',
        provider='parser',
        model=None,
        fallback_used=True,
    )


def classify_assist_request(text: str) -> AssistIntentResult:
    metadata = assist_model_metadata()
    if not metadata['available']:
        return classify_assist_with_parser(text)

    prompt = _json_prompt({
        'request': text,
        'supported_task_kinds': ['summarize', 'reply', 'rewrite', 'explain', 'answer', 'research_and_respond'],
        'notes': 'Assume source text usually comes from selected text or clipboard if the request says this/selected/copied.',
    })
    raw = ollama_generate(prompt=prompt, system=INTENT_SYSTEM_PROMPT, format_json=True, timeout=12.0, options={'temperature': 0.0})
    if not raw.get('ok'):
        fallback = classify_assist_with_parser(text)
        fallback.provider = 'parser'
        return fallback
    try:
        parsed = AssistIntentResult.model_validate(parse_json_response(raw['response']))
    except (ValidationError, ValueError):
        fallback = classify_assist_with_parser(text)
        fallback.provider = 'parser'
        return fallback
    parsed.provider = raw['provider']
    parsed.model = raw['model']
    parsed.fallback_used = False
    return parsed


def generate_assist_draft(*, task_kind: str, source_text: str, request_text: str,
                          research_context: dict, style_hints: dict[str, str],
                          retry_feedback: str = '', learning_signals: dict | None = None) -> AssistDraftResult:
    metadata = assist_model_metadata()
    if not metadata['available']:
        raise RuntimeError('assist_model_unavailable')

    prompt = _json_prompt({
        'task_kind': task_kind,
        'request_text': request_text,
        'source_text': source_text,
        'research_context': research_context,
        'style_hints': style_hints,
        'retry_feedback': retry_feedback,
        'learning_signals': learning_signals or {},
        'requirements': {
            'approval_required': True,
            'natural_output': True,
            'avoid_robotic_tone': True,
            'keep_research_bounded': True,
        },
    })
    raw = ollama_generate(prompt=prompt, system=DRAFT_SYSTEM_PROMPT, format_json=True, timeout=35.0, options={'temperature': 0.35})
    if not raw.get('ok'):
        raise RuntimeError(raw.get('error') or 'assist_generation_failed')
    try:
        parsed = AssistDraftResult.model_validate(parse_json_response(raw['response']))
    except (ValidationError, ValueError) as exc:
        raise RuntimeError(f'assist_generation_parse_failed:{exc}') from exc
    parsed.provider = raw['provider']
    parsed.model = raw['model']
    parsed.fallback_used = False
    return parsed
