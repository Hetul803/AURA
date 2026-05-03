from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from storage.profile_paths import profile_dir
from tools.os_automation import capture_context
from .state import db_conn, record_audit_event


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _json_dumps(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _json_loads(value: str | None, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _domain(url: str | None) -> str:
    return urlparse(url or '').netloc.lower()


def _input_preview(text: str | None, limit: int = 240) -> str:
    compact = ' '.join((text or '').split())
    return compact[:limit]


def _find_git_root(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in [current, *current.parents]:
        if (candidate / '.git').exists():
            return candidate
    return None


def _current_folder() -> str:
    configured = os.getenv('AURA_CURRENT_FOLDER') or os.getenv('AURA_WORKSPACE')
    if configured:
        return str(Path(configured).expanduser())
    return str(Path.cwd())


def _project_context(folder: str) -> dict:
    path = Path(folder).expanduser()
    git_root = _find_git_root(path) if path.exists() else None
    return {
        'current_folder': str(path),
        'current_repo': str(git_root) if git_root else '',
        'project_name': git_root.name if git_root else path.name,
        'is_git_repo': bool(git_root),
    }


def default_workspace_root() -> str:
    root = profile_dir() / 'workspaces'
    root.mkdir(parents=True, exist_ok=True)
    return str(root)


def github_repo_from_url(url: str | None) -> dict | None:
    parsed = urlparse(url or '')
    if parsed.netloc.lower() not in {'github.com', 'www.github.com'}:
        return None
    parts = [part for part in parsed.path.split('/') if part]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1].removesuffix('.git')
    if not owner or not repo:
        return None
    html_url = f'https://github.com/{owner}/{repo}'
    clone_url = f'{html_url}.git'
    return {
        'type': 'github_repo',
        'owner': owner,
        'repo': repo,
        'repo_full_name': f'{owner}/{repo}',
        'html_url': html_url,
        'clone_url': clone_url,
    }


def normalize_context(raw: dict | None = None, *, source: str = 'desktop') -> dict:
    raw = raw or {}
    folder = raw.get('current_folder') or _current_folder()
    project = _project_context(folder)
    browser_url = raw.get('browser_url') or ''
    selected_text = raw.get('selected_text') or ''
    clipboard_text = raw.get('clipboard_text') or ''
    input_text = raw.get('input_text') or selected_text or clipboard_text
    input_source = raw.get('input_source') or raw.get('capture_path_used') or ('selected_text' if selected_text else ('clipboard' if clipboard_text else 'none'))
    context_refs = []
    github_ref = github_repo_from_url(browser_url)
    if github_ref:
        context_refs.append(github_ref)

    snapshot = {
        'snapshot_id': raw.get('snapshot_id') or str(uuid4()),
        'captured_at': raw.get('captured_at') or _now_iso(),
        'source': source,
        'active_app': raw.get('active_app') or '',
        'window_title': raw.get('window_title') or '',
        'browser_url': browser_url,
        'browser_domain': raw.get('browser_domain') or _domain(browser_url),
        'browser_title': raw.get('browser_title') or raw.get('window_title') or '',
        'selected_text': selected_text,
        'clipboard_text': clipboard_text,
        'input_text': input_text,
        'input_source': input_source,
        'input_preview': _input_preview(input_text),
        'capture_path_used': raw.get('capture_path_used') or input_source,
        'capture_method': raw.get('capture_method') or {},
        'target_fingerprint': raw.get('target_fingerprint') or {},
        'paste_target': raw.get('paste_target') or raw.get('target_fingerprint') or {},
        'warnings': raw.get('warnings') or [],
        'device': {
            'kind': 'desktop',
            'os': os.name,
        },
        'project': project,
        'workspace_hint': raw.get('workspace_hint') or default_workspace_root(),
        'context_refs': context_refs,
        'privacy': {
            'local_first': True,
            'durable_memory_allowed': False,
            'contains_clipboard_text': bool(clipboard_text),
            'contains_selected_text': bool(selected_text),
        },
        'ok': bool(raw.get('ok') or browser_url or input_text or raw.get('active_app') or raw.get('window_title') or project.get('current_folder')),
    }
    return snapshot


def persist_context_snapshot(snapshot: dict) -> dict:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO context_snapshots(
              snapshot_id, captured_at, source, active_app, window_title,
              browser_url, browser_domain, browser_title, input_source,
              input_preview, current_folder, current_repo, workspace_hint, snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot['snapshot_id'],
                snapshot['captured_at'],
                snapshot['source'],
                snapshot.get('active_app'),
                snapshot.get('window_title'),
                snapshot.get('browser_url'),
                snapshot.get('browser_domain'),
                snapshot.get('browser_title'),
                snapshot.get('input_source'),
                snapshot.get('input_preview'),
                (snapshot.get('project') or {}).get('current_folder'),
                (snapshot.get('project') or {}).get('current_repo'),
                snapshot.get('workspace_hint'),
                _json_dumps(snapshot),
            ),
        )
    record_audit_event({
        'event_type': 'context_snapshot_captured',
        'message': 'Context snapshot captured',
        'payload': {
            'snapshot_id': snapshot['snapshot_id'],
            'source': snapshot['source'],
            'browser_domain': snapshot.get('browser_domain'),
            'input_source': snapshot.get('input_source'),
            'context_refs': snapshot.get('context_refs', []),
        },
    })
    return snapshot


def capture_current_context(*, source: str = 'desktop', persist: bool = True) -> dict:
    if os.getenv('AURA_FORCE_FIXTURES') == '1':
        raw = {
            'ok': True,
            'active_app': 'Fixture Browser',
            'window_title': 'AURA fixture context',
            'browser_url': 'https://github.com/Hetul803/AURA',
            'browser_title': 'Hetul803/AURA',
            'selected_text': 'Fixture selected text for AURA tests.',
            'clipboard_text': '',
            'input_text': 'Fixture selected text for AURA tests.',
            'input_source': 'fixture',
            'capture_path_used': 'fixture',
            'capture_method': {'fixture': True, 'clipboard_preserved': True, 'clipboard_restored_after_capture': True},
            'target_fingerprint': {'app_name': 'Fixture Browser', 'browser_domain': 'github.com', 'browser_url': 'https://github.com/Hetul803/AURA'},
            'paste_target': {'app_name': 'Fixture Browser', 'browser_domain': 'github.com', 'browser_url': 'https://github.com/Hetul803/AURA'},
        }
    else:
        raw = capture_context()
    snapshot = normalize_context(raw, source=source)
    return persist_context_snapshot(snapshot) if persist else snapshot


def latest_context_snapshot() -> dict | None:
    row = db_conn().execute(
        'SELECT snapshot_json FROM context_snapshots ORDER BY captured_at DESC LIMIT 1',
    ).fetchone()
    return _json_loads(row['snapshot_json'], {}) if row else None


def list_context_snapshots(limit: int = 20) -> list[dict]:
    rows = db_conn().execute(
        'SELECT snapshot_json FROM context_snapshots ORDER BY captured_at DESC LIMIT ?',
        (limit,),
    ).fetchall()
    return [_json_loads(row['snapshot_json'], {}) for row in rows]


def legacy_assist_context(snapshot: dict) -> dict:
    """Return the shape existing assist flows and desktop UI already consume."""
    return {
        'ok': snapshot.get('ok', False),
        'snapshot_id': snapshot.get('snapshot_id'),
        'active_app': snapshot.get('active_app'),
        'window_title': snapshot.get('window_title'),
        'browser_url': snapshot.get('browser_url'),
        'browser_domain': snapshot.get('browser_domain'),
        'browser_title': snapshot.get('browser_title'),
        'selected_text': snapshot.get('selected_text', ''),
        'clipboard_text': snapshot.get('clipboard_text', ''),
        'input_text': snapshot.get('input_text', ''),
        'input_source': snapshot.get('input_source'),
        'capture_path_used': snapshot.get('capture_path_used'),
        'capture_method': snapshot.get('capture_method') or {},
        'target_fingerprint': snapshot.get('target_fingerprint') or {},
        'paste_target': snapshot.get('paste_target') or {},
        'warnings': snapshot.get('warnings') or [],
        'context_refs': snapshot.get('context_refs') or [],
        'project': snapshot.get('project') or {},
        'workspace_hint': snapshot.get('workspace_hint'),
    }
