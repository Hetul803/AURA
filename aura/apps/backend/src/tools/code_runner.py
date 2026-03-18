from __future__ import annotations

import builtins
import difflib
import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

from tools.tool_result import success, failure

FAILURE_PATTERNS = {
    'syntax_error': re.compile(r'SyntaxError: (.+)'),
    'name_error': re.compile(r"NameError: name '([^']+)' is not defined"),
    'import_error': re.compile(r'ImportError: (.+)'),
    'dependency_error': re.compile(r"ModuleNotFoundError: No module named '([^']+)'"),
    'file_not_found': re.compile(r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'"),
    'permission_error': re.compile(r'PermissionError: (.+)'),
}



def _workspace(path: str | None, fallback: str | None = None) -> Path:
    if path:
        candidate = Path(path).expanduser()
        return candidate if candidate.is_dir() else candidate.parent
    if fallback:
        candidate = Path(fallback).expanduser()
        return candidate if candidate.is_dir() else candidate.parent
    return Path.cwd()



def _truncate(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[:limit] + '\n...[truncated]'



def _traceback_excerpt(stderr: str) -> str:
    lines = [line for line in stderr.strip().splitlines() if line.strip()]
    return '\n'.join(lines[-8:]) if lines else ''



def classify_failure(stderr: str, stdout: str = '') -> dict[str, Any]:
    combined = f'{stdout}\n{stderr}'.strip()
    for name, pattern in FAILURE_PATTERNS.items():
        match = pattern.search(combined)
        if match:
            detail = match.group(1) if match.groups() else combined.splitlines()[-1] if combined else name
            return {
                'failure_class': name,
                'detail': detail,
                'traceback_excerpt': _traceback_excerpt(stderr or combined),
                'repairable': name in {'syntax_error', 'name_error'},
                'requires_user': name in {'dependency_error', 'permission_error'},
            }
    if combined:
        return {
            'failure_class': 'runtime_error',
            'detail': combined.splitlines()[-1],
            'traceback_excerpt': _traceback_excerpt(stderr or combined),
            'repairable': False,
            'requires_user': False,
        }
    return {
        'failure_class': 'unknown_error',
        'detail': 'Unknown execution failure',
        'traceback_excerpt': '',
        'repairable': False,
        'requires_user': False,
    }



def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()



def _command_observation(proc: subprocess.CompletedProcess[str], workspace: Path, target: str | None = None) -> dict[str, Any]:
    failure_info = classify_failure(proc.stderr, proc.stdout) if proc.returncode else {
        'failure_class': None,
        'detail': None,
        'traceback_excerpt': '',
        'repairable': False,
        'requires_user': False,
    }
    return {
        'workspace': str(workspace),
        'target': target,
        'exit_code': proc.returncode,
        'stdout': _truncate(proc.stdout or ''),
        'stderr': _truncate(proc.stderr or ''),
        'failure_class': failure_info.get('failure_class'),
        'failure_detail': failure_info.get('detail'),
        'traceback_excerpt': failure_info.get('traceback_excerpt'),
        'repairable': failure_info.get('repairable', False),
        'requires_user': failure_info.get('requires_user', False),
        'command_succeeded': proc.returncode == 0,
        'file_exists': bool(target and Path(target).expanduser().exists()),
    }



def run_shell_command(command: str, workspace: str | None = None) -> dict[str, Any]:
    cwd = _workspace(workspace)
    proc = subprocess.run(command, shell=True, cwd=str(cwd), capture_output=True, text=True)
    observation = _command_observation(proc, cwd)
    result = {'stdout': proc.stdout, 'stderr': proc.stderr, 'exit_code': proc.returncode, 'command': command}
    if proc.returncode == 0:
        return success('CODE_RUN', result=result, observation=observation)
    failure_info = classify_failure(proc.stderr, proc.stdout)
    return failure(
        'CODE_RUN',
        error=failure_info['detail'],
        result={**result, 'failure_class': failure_info['failure_class']},
        observation=observation,
        retryable=failure_info['repairable'],
        requires_user=failure_info['requires_user'],
    )



def run_python_script(path: str, args: list[str] | None = None, workspace: str | None = None) -> dict[str, Any]:
    script = Path(path).expanduser()
    cwd = _workspace(workspace, str(script))
    if not script.exists():
        observation = {'workspace': str(cwd), 'target': str(script), 'file_exists': False, 'failure_class': 'file_not_found', 'failure_detail': str(script), 'repairable': False, 'requires_user': False}
        return failure('CODE_RUN', error='script_not_found', observation=observation)
    cmd = ['python', str(script), *(args or [])]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    observation = _command_observation(proc, cwd, str(script))
    result = {'stdout': proc.stdout, 'stderr': proc.stderr, 'exit_code': proc.returncode, 'command': cmd}
    if proc.returncode == 0:
        return success('CODE_RUN', result=result, observation=observation, artifacts=[str(script)])
    failure_info = classify_failure(proc.stderr, proc.stdout)
    return failure(
        'CODE_RUN',
        error=failure_info['detail'],
        result={**result, 'failure_class': failure_info['failure_class']},
        observation=observation,
        retryable=failure_info['repairable'],
        requires_user=failure_info['requires_user'],
        artifacts=[str(script)],
    )



def _line_number_from_trace(stderr: str) -> int | None:
    match = re.search(r'File ".+", line (\d+)', stderr)
    return int(match.group(1)) if match else None



def _replace_word(source: str, old: str, new: str) -> str:
    return re.sub(rf'\b{re.escape(old)}\b', new, source)



def _repair_name_error(source: str, stderr: str) -> tuple[str, dict[str, Any] | None]:
    match = FAILURE_PATTERNS['name_error'].search(stderr)
    if not match:
        return source, None
    missing = match.group(1)
    symbols = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', source))
    symbols.update(dir(builtins))
    candidates = [symbol for symbol in symbols if symbol != missing]
    replacement = next(iter(difflib.get_close_matches(missing, candidates, n=1, cutoff=0.7)), None)
    if not replacement or replacement == missing:
        return source, None
    updated = _replace_word(source, missing, replacement)
    if updated == source:
        return source, None
    return updated, {'repair': f'replaced {missing} with {replacement}', 'replacement': replacement, 'changed_symbol': missing}



def _repair_missing_colon(source: str, stderr: str) -> tuple[str, dict[str, Any] | None]:
    line_no = _line_number_from_trace(stderr)
    if not line_no:
        return source, None
    had_trailing_newline = source.endswith('\n')
    lines = source.splitlines()
    if line_no < 1 or line_no > len(lines):
        return source, None
    line = lines[line_no - 1]
    stripped = line.strip()
    keywords = ('def ', 'if ', 'elif ', 'else', 'for ', 'while ', 'class ', 'try', 'except ')
    if stripped.startswith(keywords) and not stripped.endswith(':'):
        lines[line_no - 1] = line + ':'
        updated = '\n'.join(lines) + ('\n' if had_trailing_newline else '')
        return updated, {'repair': f'added missing colon on line {line_no}', 'line_no': line_no}
    return source, None



def _diff_summary(before: str, after: str) -> str:
    diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(), fromfile='before', tofile='after', lineterm=''))
    return '\n'.join(diff[:20])



def repair_python_script(path: str, error: str | None = None, observation: dict[str, Any] | None = None, strategy: str | None = None) -> dict[str, Any]:
    script = Path(path).expanduser()
    if not script.exists():
        return failure('CODE_REPAIR', error='script_not_found', observation={'target': str(script), 'file_exists': False, 'failure_class': 'file_not_found'})

    stderr = (observation or {}).get('stderr', '') or str(error or '')
    failure_class = (observation or {}).get('failure_class') or classify_failure(stderr).get('failure_class')
    before = script.read_text(encoding='utf-8')
    before_hash = _file_hash(before)
    backup = script.with_suffix(script.suffix + '.bak')
    backup.write_text(before, encoding='utf-8')

    updated = before
    metadata = None
    if strategy == 'repair_python_name' or failure_class == 'name_error':
        updated, metadata = _repair_name_error(before, stderr)
    elif strategy == 'repair_python_syntax' or failure_class == 'syntax_error':
        updated, metadata = _repair_missing_colon(before, stderr)

    if not metadata:
        return failure(
            'CODE_REPAIR',
            error='no_supported_repair',
            observation={'target': str(script), 'repair_applied': False, 'failure_class': failure_class, 'before_hash': before_hash},
            retryable=False,
            artifacts=[str(backup)],
        )

    after_hash = _file_hash(updated)
    if after_hash == before_hash:
        return failure(
            'CODE_REPAIR',
            error='noop_repair',
            observation={'target': str(script), 'repair_applied': False, 'failure_class': failure_class, 'before_hash': before_hash, 'after_hash': after_hash},
            retryable=False,
            artifacts=[str(backup)],
        )

    script.write_text(updated, encoding='utf-8')
    diff = _diff_summary(before, updated)
    return success(
        'CODE_REPAIR',
        result={
            **metadata,
            'change_summary': metadata['repair'],
            'diff': diff,
            'before_hash': before_hash,
            'after_hash': after_hash,
        },
        observation={
            'target': str(script),
            'repair_applied': True,
            'failure_class': failure_class,
            'before_hash': before_hash,
            'after_hash': after_hash,
            'content_changed': True,
        },
        artifacts=[str(script), str(backup)],
    )



def handle_code_action(step) -> dict:
    action = step.action_type
    args = step.args
    if action == 'CODE_RUN':
        if args.get('kind') == 'shell':
            return run_shell_command(args.get('command', ''), workspace=args.get('workspace'))
        return run_python_script(args.get('path', ''), args=args.get('script_args'), workspace=args.get('workspace'))
    if action == 'CODE_REPAIR':
        return repair_python_script(
            args.get('path', ''),
            error=args.get('error'),
            observation=args.get('observation'),
            strategy=args.get('strategy'),
        )
    return failure(action, error='unsupported_code_action')
