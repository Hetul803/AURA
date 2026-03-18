from __future__ import annotations
import os
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from storage.profile_paths import profile_dir

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
    return {'ok': False, 'error': 'NOT_SUPPORTED_ON_THIS_OS', 'action': action, 'os': SYSTEM}


def open_app(app_name: str) -> dict:
    if SYSTEM == 'darwin':
        ok, out = _run(['open', '-a', app_name])
        return {'ok': ok, 'action': 'OPEN_APP', 'app': app_name, 'detail': out}
    if SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', f'Start-Process "{app_name}"'])
        return {'ok': ok, 'action': 'OPEN_APP', 'app': app_name, 'detail': out}
    return _not_supported('OPEN_APP')


def activate_app(app_name: str) -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript(f'tell application "{app_name}" to activate')
        return {'ok': ok, 'action': 'ACTIVATE_APP', 'app': app_name, 'detail': out}
    return _not_supported('ACTIVATE_APP')


def open_path(path: str, folder: bool = False) -> dict:
    p = str(Path(path).expanduser())
    if SYSTEM == 'darwin':
        ok, out = _run(['open', p])
        return {'ok': ok, 'action': 'OPEN_FOLDER' if folder else 'OPEN_FILE', 'path': p, 'detail': out}
    if SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', f'Start-Process "{p}"'])
        return {'ok': ok, 'action': 'OPEN_FOLDER' if folder else 'OPEN_FILE', 'path': p, 'detail': out}
    return _not_supported('OPEN_PATH')


def get_active_app() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript('tell application "System Events" to get name of first process whose frontmost is true')
        return {'ok': ok, 'active_app': out}
    return _not_supported('GET_ACTIVE_APP')


def get_active_window_title() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript('tell application "System Events" to tell (first process whose frontmost is true) to get name of front window')
        return {'ok': ok, 'window_title': out}
    return _not_supported('GET_ACTIVE_WINDOW_TITLE')


def read_clipboard() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _run(['pbpaste'])
        return {'ok': ok, 'text': out, 'length': len(out)}
    if SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', 'Get-Clipboard'])
        return {'ok': ok, 'text': out, 'length': len(out)}
    return _not_supported('READ_CLIPBOARD')


def write_clipboard(text: str) -> dict:
    if SYSTEM == 'darwin':
        p = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, text=True)
        p.communicate(text)
        return {'ok': p.returncode == 0, 'written': len(text)}
    if SYSTEM == 'windows':
        ok, out = _run(['powershell', '-NoProfile', '-Command', f'Set-Clipboard -Value @"{text}"@'])
        return {'ok': ok, 'written': len(text), 'detail': out}
    return _not_supported('WRITE_CLIPBOARD')


def press_keys(keys: str) -> dict:
    if SYSTEM == 'darwin':
        mapping = {'cmd+c': 'keystroke "c" using command down', 'cmd+v': 'keystroke "v" using command down'}
        script = mapping.get(keys.lower(), f'keystroke "{keys}"')
        ok, out = _osascript(f'tell application "System Events" to {script}')
        return {'ok': ok, 'keys': keys, 'detail': out}
    return _not_supported('PRESS_KEYS')


def copy_selected_text() -> dict:
    if SYSTEM == 'darwin':
        press_keys('cmd+c')
        return read_clipboard()
    return _not_supported('COPY_SELECTED_TEXT')


def type_text(text: str) -> dict:
    if SYSTEM == 'darwin':
        esc = text.replace('"', '\\"')
        ok, out = _osascript(f'tell application "System Events" to keystroke "{esc}"')
        return {'ok': ok, 'typed': len(text), 'detail': out}
    return _not_supported('TYPE_TEXT')


def paste_to_active_app(text: str) -> dict:
    w = write_clipboard(text)
    if not w.get('ok'):
        return w
    p = press_keys('cmd+v' if SYSTEM == 'darwin' else 'ctrl+v')
    return {'ok': p.get('ok', False), 'pasted': len(text), 'detail': p.get('detail', '')}


def take_screenshot() -> dict:
    out = profile_dir() / 'artifacts' / f"screen-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.png"
    if SYSTEM == 'darwin':
        ok, detail = _run(['screencapture', '-x', str(out)])
        return {'ok': ok, 'path': str(out), 'detail': detail}
    return _not_supported('TAKE_SCREENSHOT')


def active_context() -> dict:
    app = get_active_app()
    title = get_active_window_title()
    clip = read_clipboard()
    return {
        'ok': app.get('ok', False) and title.get('ok', False),
        'active_app': app.get('active_app'),
        'window_title': title.get('window_title'),
        'clipboard_length': clip.get('length', 0),
    }


def handle_os_action(step) -> dict:
    a = step.action_type
    args = step.args
    if a == 'OS_OPEN_APP':
        return open_app(args.get('app_name', ''))
    if a == 'OS_ACTIVATE_APP':
        return activate_app(args.get('app_name', ''))
    if a == 'OS_OPEN_PATH':
        p = args.get('path', '')
        return open_path(p, folder=Path(p).is_dir())
    if a == 'OS_OPEN_FILE':
        return open_path(args.get('path', ''), folder=False)
    if a == 'OS_OPEN_FOLDER':
        return open_path(args.get('path', ''), folder=True)
    if a == 'OS_GET_ACTIVE_CONTEXT':
        return active_context()
    if a == 'OS_READ_CLIPBOARD':
        return read_clipboard()
    if a == 'OS_WRITE_CLIPBOARD':
        return write_clipboard(args.get('text', ''))
    if a == 'OS_PASTE':
        return paste_to_active_app(args.get('text', ''))
    if a == 'OS_COPY_SELECTION':
        return copy_selected_text()
    if a == 'OS_TYPE_TEXT':
        return type_text(args.get('text', ''))
    if a == 'OS_PRESS_KEYS':
        return press_keys(args.get('keys', ''))
    if a == 'TAKE_SCREENSHOT':
        return take_screenshot()
    return _not_supported(a)
