from __future__ import annotations

from pathlib import Path

from tools.tool_result import success, failure



def _path_observation(path: Path) -> dict:
    return {
        'path': str(path),
        'file_exists': path.exists(),
        'is_dir': path.is_dir(),
        'size': path.stat().st_size if path.exists() and path.is_file() else 0,
    }



def handle_filesystem_action(step) -> dict:
    action = step.action_type
    path = Path(step.args.get('path', '')).expanduser()
    observation = _path_observation(path)

    if action == 'FS_EXISTS':
        return success(action, result={'exists': path.exists()}, observation=observation)

    if action == 'FS_READ_TEXT':
        if not path.exists() or not path.is_file():
            return failure(action, error='path_not_found', observation=observation, retryable=False)
        text = path.read_text(encoding=step.args.get('encoding', 'utf-8'))
        return success(action, result={'text': text}, observation={**observation, 'text_preview': text[:400]})

    if action == 'FS_WRITE_TEXT':
        path.parent.mkdir(parents=True, exist_ok=True)
        text = step.args.get('text', '')
        path.write_text(text, encoding=step.args.get('encoding', 'utf-8'))
        return success(action, result={'written': len(text)}, observation=_path_observation(path), artifacts=[str(path)])

    return failure(action, error='unsupported_filesystem_action', observation=observation)
