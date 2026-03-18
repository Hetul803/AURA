from __future__ import annotations

import platform
import subprocess
from datetime import datetime
from pathlib import Path

from storage.profile_paths import profile_dir
from tools.tool_result import success, failure

SYSTEM = platform.system().lower()



def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        out = (p.stdout or p.stderr or '').strip()
        return p.returncode == 0, out
    except Exception as e:
        return False, str(e)



def _osascript(script: str) -> tuple[bool, str]:
    return _run(['osascript', '-e', script])



def _not_supported(action: str):
    return failure(action, error='NOT_SUPPORTED_ON_THIS_OS', observation={'os': SYSTEM})



def open_app(app_name: str) -> dict:
    if SYSTEM == 'darwin':
        ok, out = _run(['open', '-a', app_name])
    elif SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', f'Start-Process "{app_name}"'])
    else:
        return _not_supported('OS_OPEN_APP')
    observation = {'active_app': app_name, 'detail': out}
    if ok:
        return success('OS_OPEN_APP', result={'app': app_name}, observation=observation)
    return failure('OS_OPEN_APP', error=out or 'open_app_failed', observation=observation, retryable=False)



def activate_app(app_name: str) -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript(f'tell application "{app_name}" to activate')
        observation = {'active_app': app_name, 'detail': out}
        if ok:
            return success('OS_ACTIVATE_APP', result={'app': app_name}, observation=observation)
        return failure('OS_ACTIVATE_APP', error=out or 'activate_app_failed', observation=observation)
    return _not_supported('OS_ACTIVATE_APP')



def open_path(path: str, folder: bool = False) -> dict:
    p = str(Path(path).expanduser())
    action = 'OS_OPEN_FOLDER' if folder else 'OS_OPEN_FILE'
    if SYSTEM == 'darwin':
        ok, out = _run(['open', p])
    elif SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', f'Start-Process "{p}"'])
    else:
        return _not_supported(action)
    observation = {'path': p, 'file_exists': Path(p).exists(), 'detail': out}
    if ok:
        return success(action, result={'path': p, 'opened_path': p}, observation=observation, artifacts=[p] if Path(p).exists() else [])
    return failure(action, error=out or 'open_path_failed', observation=observation)



def get_active_app() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript('tell application "System Events" to get name of first process whose frontmost is true')
        if ok:
            return success('OS_GET_ACTIVE_CONTEXT', result={'active_app': out}, observation={'active_app': out})
        return failure('OS_GET_ACTIVE_CONTEXT', error=out or 'active_app_failed', observation={'active_app': out})
    return _not_supported('OS_GET_ACTIVE_CONTEXT')



def get_active_window_title() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript('tell application "System Events" to tell (first process whose frontmost is true) to get name of front window')
        if ok:
            return success('OS_GET_ACTIVE_CONTEXT', result={'window_title': out}, observation={'window_title': out})
        return failure('OS_GET_ACTIVE_CONTEXT', error=out or 'window_title_failed', observation={'window_title': out})
    return _not_supported('OS_GET_ACTIVE_CONTEXT')



def read_clipboard() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _run(['pbpaste'])
    elif SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard'])
    else:
        return _not_supported('OS_READ_CLIPBOARD')
    observation = {'clipboard_length': len(out), 'clipboard_preview': out[:120]}
    if ok:
        return success('OS_READ_CLIPBOARD', result={'text': out, 'length': len(out)}, observation=observation)
    return failure('OS_READ_CLIPBOARD', error=out or 'clipboard_read_failed', observation=observation)



def write_clipboard(text: str) -> dict:
    if SYSTEM == 'darwin':
        p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, text=True)
        p.communicate(text)
        ok = p.returncode == 0
        detail = ''
    elif SYSTEM == 'windows':
        ok, detail = _run(['powershell', '-NoProfile', '-Command', f'Set-Clipboard -Value @"{text}"@'])
    else:
        return _not_supported('OS_WRITE_CLIPBOARD')
    observation = {'clipboard_length': len(text), 'clipboard_preview': text[:120]}
    if ok:
        return success('OS_WRITE_CLIPBOARD', result={'written': len(text)}, observation=observation, safety_flags=['clipboard_write'])
    return failure('OS_WRITE_CLIPBOARD', error=detail or 'clipboard_write_failed', observation=observation)



def press_keys(keys: str) -> dict:
    if SYSTEM == 'darwin':
        mapping = {'cmd+c': 'keystroke "c" using command down', 'cmd+v': 'keystroke "v" using command down'}
        script = mapping.get(keys.lower(), f'keystroke "{keys}"')
        ok, out = _osascript(f'tell application "System Events" to {script}')
        if ok:
            return success('OS_PRESS_KEYS', result={'keys': keys}, observation={'detail': out})
        return failure('OS_PRESS_KEYS', error=out or 'keypress_failed', observation={'detail': out})
    return _not_supported('OS_PRESS_KEYS')



def copy_selected_text() -> dict:
    if SYSTEM == 'darwin':
        key_result = press_keys('cmd+c')
        if not key_result.get('ok'):
            return key_result
        clip = read_clipboard()
        clip['action'] = 'OS_COPY_SELECTION'
        clip['safety_flags'] = ['clipboard_read']
        return clip
    return _not_supported('OS_COPY_SELECTION')



def type_text(text: str) -> dict:
    if SYSTEM == 'darwin':
        esc = text.replace('"', '\\"')
        ok, out = _osascript(f'tell application "System Events" to keystroke "{esc}"')
        if ok:
            return success('OS_TYPE_TEXT', result={'typed': len(text)}, observation={'detail': out}, safety_flags=['text_entry'])
        return failure('OS_TYPE_TEXT', error=out or 'type_text_failed', observation={'detail': out})
    return _not_supported('OS_TYPE_TEXT')



def paste_to_active_app(text: str) -> dict:
    write_result = write_clipboard(text)
    if not write_result.get('ok'):
        write_result['action'] = 'OS_PASTE'
        return write_result
    keys = 'cmd+v' if SYSTEM == 'darwin' else 'ctrl+v'
    press_result = press_keys(keys)
    observation = {'clipboard_length': len(text), 'active_app': active_context().get('active_app')}
    if press_result.get('ok'):
        return success('OS_PASTE', result={'pasted': len(text)}, observation=observation, safety_flags=['clipboard_write', 'text_entry'])
    return failure('OS_PASTE', error=press_result.get('error') or 'paste_failed', observation=observation)



def take_screenshot() -> dict:
    out = profile_dir() / 'artifacts' / f"screen-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
    if SYSTEM == 'darwin':
        ok, detail = _run(['screencapture', '-x', str(out)])
        observation = {'path': str(out), 'file_exists': out.exists()}
        if ok:
            return success('TAKE_SCREENSHOT', result={'path': str(out)}, observation=observation, artifacts=[str(out)])
        return failure('TAKE_SCREENSHOT', error=detail or 'screenshot_failed', observation=observation)
    return _not_supported('TAKE_SCREENSHOT')



def active_context() -> dict:
    app = get_active_app()
    title = get_active_window_title()
    clip = read_clipboard()
    return {
        'ok': app.get('ok', False) and title.get('ok', False),
        'active_app': app.get('active_app') or (app.get('result') or {}).get('active_app'),
        'window_title': title.get('window_title') or (title.get('result') or {}).get('window_title'),
        'clipboard_length': clip.get('length', 0) or (clip.get('result') or {}).get('length', 0),
    }



def handle_os_action(step) -> dict:
    action = step.action_type
    args = step.args
    if action == 'OS_OPEN_APP':
        return open_app(args.get('app_name', ''))
    if action == 'OS_ACTIVATE_APP':
        return activate_app(args.get('app_name', ''))
    if action == 'OS_OPEN_PATH':
        p = args.get('path', '')
        return open_path(p, folder=Path(p).expanduser().is_dir())
    if action == 'OS_OPEN_FILE':
        return open_path(args.get('path', ''), folder=False)
    if action == 'OS_OPEN_FOLDER':
        return open_path(args.get('path', ''), folder=True)
    if action == 'OS_GET_ACTIVE_CONTEXT':
        ctx = active_context()
        if ctx.get('ok'):
            return success('OS_GET_ACTIVE_CONTEXT', result=ctx, observation=ctx)
        return failure('OS_GET_ACTIVE_CONTEXT', error='active_context_failed', observation=ctx)
    if action == 'OS_READ_CLIPBOARD':
        return read_clipboard()
    if action == 'OS_WRITE_CLIPBOARD':
        return write_clipboard(args.get('text', ''))
    if action == 'OS_PASTE':
        return paste_to_active_app(args.get('text', ''))
    if action == 'OS_COPY_SELECTION':
        return copy_selected_text()
    if action == 'OS_TYPE_TEXT':
        return type_text(args.get('text', ''))
    if action == 'OS_PRESS_KEYS':
        return press_keys(args.get('keys', ''))
    if action == 'TAKE_SCREENSHOT':
        return take_screenshot()
    return _not_supported(action)
