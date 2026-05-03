from __future__ import annotations

from pathlib import Path

from aura.privacy import redact_text
from tools.tool_result import success, failure



def _path_observation(path: Path) -> dict:
    return {
        'path': str(path),
        'file_exists': path.exists(),
        'is_dir': path.is_dir(),
        'size': path.stat().st_size if path.exists() and path.is_file() else 0,
    }


def _safe_path(path: Path, workspace: str | None = None, *, enforce_workspace: bool = False) -> tuple[bool, str, Path]:
    base = Path(workspace).expanduser().resolve() if workspace else Path.cwd().resolve()
    try:
        resolved = path.expanduser().resolve()
    except Exception:
        return False, 'path_resolution_failed', path
    if '..' in path.parts:
        return False, 'path_traversal_blocked', resolved
    sensitive_roots = [Path('/'), Path.home(), Path('/System'), Path('/Library')]
    if resolved in sensitive_roots:
        return False, 'sensitive_root_blocked', resolved
    if enforce_workspace or workspace:
        try:
            resolved.relative_to(base)
        except ValueError:
            return False, 'outside_workspace_blocked', resolved
    return True, 'workspace_checked', resolved



def handle_filesystem_action(step) -> dict:
    action = step.action_type
    workspace = step.args.get('workspace')
    raw_path = step.args.get('path', '')
    path = Path(raw_path).expanduser()
    safe, reason, resolved = _safe_path(path, workspace=workspace, enforce_workspace=action == 'FS_WRITE_TEXT')
    path = resolved
    observation = _path_observation(path)
    observation['guardian_reason'] = reason
    if not safe:
        return failure(action, error=reason, observation=observation, retryable=False, requires_user=True)

    if action == 'FS_EXISTS':
        return success(action, result={'exists': path.exists()}, observation=observation)

    if action == 'FS_READ_TEXT':
        if not path.exists() or not path.is_file():
            return failure(action, error='path_not_found', observation=observation, retryable=False)
        text = path.read_text(encoding=step.args.get('encoding', 'utf-8'))
        return success(action, result={'text': text}, observation={**observation, 'text_preview': text[:400]})

    if action == 'FS_WRITE_TEXT':
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not step.args.get('allow_overwrite'):
            backup = path.with_suffix(path.suffix + '.aura.bak')
            backup.write_text(path.read_text(encoding=step.args.get('encoding', 'utf-8')), encoding=step.args.get('encoding', 'utf-8'))
            observation['backup_path'] = str(backup)
        text = redact_text(step.args.get('text', ''))
        path.write_text(text, encoding=step.args.get('encoding', 'utf-8'))
        return success(action, result={'written': len(text)}, observation=_path_observation(path), artifacts=[str(path)])

    return failure(action, error='unsupported_filesystem_action', observation=observation)
