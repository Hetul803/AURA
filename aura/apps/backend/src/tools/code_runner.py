from __future__ import annotations

import builtins
import difflib
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from tools.tool_result import success, failure


FAILURE_PATTERNS = {
    'syntax_error': re.compile(r'SyntaxError: (.+)'),
    'name_error': re.compile(r"NameError: name '([^']+)' is not defined"),
    'module_not_found': re.compile(r"ModuleNotFoundError: No module named '([^']+)'"),
    'file_not_found': re.compile(r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'"),
    'zero_division': re.compile(r'ZeroDivisionError:'),
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



def classify_failure(stderr: str, stdout: str = '') -> dict[str, Any]:
    combined = f'{stdout}\n{stderr}'.strip()
    for name, pattern in FAILURE_PATTERNS.items():
        match = pattern.search(combined)
        if match:
            detail = match.group(1) if match.groups() else combined.splitlines()[-1] if combined else name
            return {'failure_class': name, 'detail': detail}
    if combined:
        return {'failure_class': 'runtime_error', 'detail': combined.splitlines()[-1]}
    return {'failure_class': 'unknown_error', 'detail': 'Unknown execution failure'}



def _command_observation(proc: subprocess.CompletedProcess[str], workspace: Path, target: str | None = None) -> dict[str, Any]:
    failure = classify_failure(proc.stderr, proc.stdout) if proc.returncode else {}
    return {
        'workspace': str(workspace),
        'target': target,
        'exit_code': proc.returncode,
        'stdout': _truncate(proc.stdout or ''),
        'stderr': _truncate(proc.stderr or ''),
        'failure_class': failure.get('failure_class'),
        'failure_detail': failure.get('detail'),
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
    return failure('CODE_RUN', error=failure_info['detail'], result=result, observation=observation, retryable=True)



def run_python_script(path: str, args: list[str] | None = None, workspace: str | None = None) -> dict[str, Any]:
    script = Path(path).expanduser()
    cwd = _workspace(workspace, str(script))
    if not script.exists():
        return failure('CODE_RUN', error='script_not_found', observation={'workspace': str(cwd), 'target': str(script), 'file_exists': False})
    cmd = ['python', str(script), *(args or [])]
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    observation = _command_observation(proc, cwd, str(script))
    result = {'stdout': proc.stdout, 'stderr': proc.stderr, 'exit_code': proc.returncode, 'command': cmd}
    if proc.returncode == 0:
        return success('CODE_RUN', result=result, observation=observation, artifacts=[str(script)])
    failure_info = classify_failure(proc.stderr, proc.stdout)
    return failure('CODE_RUN', error=failure_info['detail'], result=result, observation=observation, retryable=True, artifacts=[str(script)])



def _line_number_from_trace(stderr: str) -> int | None:
    match = re.search(r'File ".+", line (\d+)', stderr)
    return int(match.group(1)) if match else None



def _replace_word(source: str, old: str, new: str) -> str:
    return re.sub(rf'\b{re.escape(old)}\b', new, source)



def _repair_name_error(path: Path, stderr: str) -> tuple[bool, str | None, str | None]:
    source = path.read_text(encoding='utf-8')
    match = FAILURE_PATTERNS['name_error'].search(stderr)
    if not match:
        return False, None, None
    missing = match.group(1)
    symbols = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', source))
    symbols.update(dir(builtins))
    candidates = [symbol for symbol in symbols if symbol != missing]
    replacement = next(iter(difflib.get_close_matches(missing, candidates, n=1, cutoff=0.7)), None)
    if not replacement or replacement == missing:
        return False, None, None
    updated = _replace_word(source, missing, replacement)
    if updated == source:
        return False, None, None
    path.write_text(updated, encoding='utf-8')
    return True, f'replaced {missing} with {replacement}', replacement



def _repair_missing_colon(path: Path, stderr: str) -> tuple[bool, str | None]:
    line_no = _line_number_from_trace(stderr)
    if not line_no:
        return False, None
    lines = path.read_text(encoding='utf-8').splitlines()
    if line_no < 1 or line_no > len(lines):
        return False, None
    line = lines[line_no - 1]
    stripped = line.strip()
    keywords = ('def ', 'if ', 'elif ', 'else', 'for ', 'while ', 'class ', 'try', 'except ')
    if stripped.startswith(keywords) and not stripped.endswith(':'):
        lines[line_no - 1] = line + ':'
        path.write_text('\n'.join(lines) + ('\n' if path.read_text(encoding='utf-8').endswith('\n') else ''), encoding='utf-8')
        return True, f'added missing colon on line {line_no}'
    return False, None



def repair_python_script(path: str, error: str | None = None, observation: dict[str, Any] | None = None) -> dict[str, Any]:
    script = Path(path).expanduser()
    if not script.exists():
        return failure('CODE_REPAIR', error='script_not_found', observation={'target': str(script), 'file_exists': False})

    stderr = ''
    if observation:
        stderr = observation.get('stderr', '')
    if error and not stderr:
        stderr = str(error)

    backup = script.with_suffix(script.suffix + '.bak')
    backup.write_text(script.read_text(encoding='utf-8'), encoding='utf-8')

    fixed, detail, replacement = _repair_name_error(script, stderr)
    if fixed:
        return success(
            'CODE_REPAIR',
            result={'repair': detail, 'replacement': replacement},
            observation={'target': str(script), 'repair_applied': True, 'failure_class': 'name_error'},
            artifacts=[str(script), str(backup)],
        )

    fixed, detail = _repair_missing_colon(script, stderr)
    if fixed:
        return success(
            'CODE_REPAIR',
            result={'repair': detail},
            observation={'target': str(script), 'repair_applied': True, 'failure_class': 'syntax_error'},
            artifacts=[str(script), str(backup)],
        )

    return failure(
        'CODE_REPAIR',
        error='no_supported_repair',
        observation={'target': str(script), 'repair_applied': False},
        retryable=False,
        artifacts=[str(backup)],
    )



def handle_code_action(step) -> dict:
    action = step.action_type
    args = step.args
    if action == 'CODE_RUN':
        if args.get('kind') == 'shell':
            return run_shell_command(args.get('command', ''), workspace=args.get('workspace'))
        return run_python_script(args.get('path', ''), args=args.get('script_args'), workspace=args.get('workspace'))
    if action == 'CODE_REPAIR':
        return repair_python_script(args.get('path', ''), error=args.get('error'), observation=args.get('observation'))
    return failure(action, error='unsupported_code_action')
