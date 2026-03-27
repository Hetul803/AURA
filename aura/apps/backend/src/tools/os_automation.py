from __future__ import annotations

import platform
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from storage.profile_paths import profile_dir
from tools.tool_result import failure, success

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


def _safe_osascript_list(script: str) -> tuple[bool, list[str]]:
    ok, out = _osascript(script)
    if not ok:
        return False, []
    return True, [line.strip() for line in out.splitlines() if line.strip()]


def _clipboard_text() -> str:
    clip = read_clipboard()
    return (clip.get('result') or {}).get('text', '') if clip.get('ok') else ''


def get_browser_context(active_app: str | None = None) -> dict:
    app = active_app or (get_active_app().get('result') or {}).get('active_app')
    if SYSTEM != 'darwin' or not app:
        return {}
    scripts = {
        'Google Chrome': 'tell application "Google Chrome" to if (count of windows) > 0 then return {URL of active tab of front window, title of active tab of front window}',
        'Safari': 'tell application "Safari" to if (count of windows) > 0 then return {URL of front document, name of front document}',
        'Arc': 'tell application "Arc" to if (count of windows) > 0 then return {URL of active tab of front window, title of active tab of front window}',
    }
    script = scripts.get(app)
    if not script:
        return {}
    ok, values = _safe_osascript_list(script)
    if not ok or not values:
        return {}
    return {
        'browser_url': values[0] if len(values) > 0 else '',
        'browser_title': values[1] if len(values) > 1 else '',
    }


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
    if SYSTEM != 'darwin':
        return _not_supported('OS_COPY_SELECTION')
    original_clipboard = _clipboard_text()
    key_result = press_keys('cmd+c')
    if not key_result.get('ok'):
        return key_result
    selected_text = original_clipboard
    changed = False
    for _ in range(6):
        time.sleep(0.08)
        current = _clipboard_text()
        if current != original_clipboard:
            selected_text = current
            changed = True
            break
    if not changed:
        selected_text = _clipboard_text()
    clip = success(
        'OS_COPY_SELECTION',
        result={'text': selected_text, 'length': len(selected_text), 'clipboard_preserved': original_clipboard},
        observation={'clipboard_length': len(selected_text), 'clipboard_preview': selected_text[:120], 'selection_changed_clipboard': changed},
        safety_flags=['clipboard_read'],
    )
    if original_clipboard != selected_text:
        write_clipboard(original_clipboard)
    return clip


def type_text(text: str) -> dict:
    if SYSTEM == 'darwin':
        esc = text.replace('"', '\\"')
        ok, out = _osascript(f'tell application "System Events" to keystroke "{esc}"')
        if ok:
            return success('OS_TYPE_TEXT', result={'typed': len(text)}, observation={'detail': out}, safety_flags=['text_entry'])
        return failure('OS_TYPE_TEXT', error=out or 'type_text_failed', observation={'detail': out})
    return _not_supported('OS_TYPE_TEXT')


def paste_to_active_app(text: str, preserve_clipboard: bool = True) -> dict:
    original_clipboard = _clipboard_text() if preserve_clipboard else ''
    write_result = write_clipboard(text)
    if not write_result.get('ok'):
        write_result['action'] = 'OS_PASTE'
        return write_result
    keys = 'cmd+v' if SYSTEM == 'darwin' else 'ctrl+v'
    press_result = press_keys(keys)
    observation = {'clipboard_length': len(text), 'active_app': active_context().get('active_app'), 'clipboard_preserved': preserve_clipboard}
    if preserve_clipboard and original_clipboard != text:
        write_clipboard(original_clipboard)
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


def capture_context() -> dict:
    app_result = get_active_app()
    title_result = get_active_window_title()
    active_app_name = app_result.get('active_app') or (app_result.get('result') or {}).get('active_app') or ''
    window_title = title_result.get('window_title') or (title_result.get('result') or {}).get('window_title') or ''
    browser = get_browser_context(active_app_name)

    selected_attempted = True
    selection = copy_selected_text()
    selected_text = (selection.get('result') or {}).get('text', '') if selection.get('ok') else ''
    clipboard_fallback_used = False
    original_clipboard = _clipboard_text()

    if selected_text:
        input_text = selected_text
        input_source = 'selected_text'
    else:
        input_text = original_clipboard
        input_source = 'clipboard' if input_text else 'none'
        clipboard_fallback_used = bool(input_text)

    warnings = []
    if not selected_text:
        warnings.append('selected_text_unavailable')
    if not input_text:
        warnings.append('copy_or_select_text_first')

    paste_target = {
        'app_name': active_app_name,
        'window_title': window_title,
        'target_url': browser.get('browser_url'),
        'target_domain': urlparse(browser.get('browser_url') or '').netloc,
        'browser_title': browser.get('browser_title') or window_title,
        'captured_at': datetime.utcnow().isoformat() + 'Z',
    }

    return {
        'ok': bool(active_app_name or window_title or input_text),
        'active_app': active_app_name,
        'window_title': window_title,
        'browser_url': browser.get('browser_url'),
        'browser_title': browser.get('browser_title') or window_title,
        'selected_text': selected_text,
        'clipboard_text': original_clipboard,
        'input_text': input_text,
        'input_source': input_source,
        'capture_method': {
            'selected_text_attempted': selected_attempted,
            'selected_text_succeeded': bool(selected_text),
            'clipboard_fallback_used': clipboard_fallback_used,
            'clipboard_preserved_after_capture': True,
        },
        'paste_target': paste_target,
        'warnings': warnings,
    }


def active_context() -> dict:
    app = get_active_app()
    title = get_active_window_title()
    clip = read_clipboard()
    active_app_name = app.get('active_app') or (app.get('result') or {}).get('active_app')
    browser = get_browser_context(active_app_name)
    return {
        'ok': app.get('ok', False) and title.get('ok', False),
        'active_app': active_app_name,
        'window_title': title.get('window_title') or (title.get('result') or {}).get('window_title'),
        'browser_url': browser.get('browser_url'),
        'browser_title': browser.get('browser_title'),
        'clipboard_length': clip.get('length', 0) or (clip.get('result') or {}).get('length', 0),
    }


def validate_target(target: dict | None, current: dict | None, strict: bool = False) -> tuple[bool, str]:
    target = target or {}
    current = current or {}
    if not target:
        return True, 'no_target_snapshot'
    target_app = (target.get('app_name') or '').lower()
    current_app = (current.get('active_app') or '').lower()
    if target_app and current_app and target_app != current_app:
        return False, 'active_app_changed'
    target_domain = target.get('target_domain') or urlparse(target.get('target_url') or '').netloc
    current_domain = urlparse(current.get('browser_url') or '').netloc
    if target_domain and current_domain and target_domain != current_domain:
        return False, 'browser_domain_changed'
    target_title = target.get('window_title') or ''
    current_title = current.get('window_title') or ''
    if target_title and current_title:
        if strict and target_title != current_title:
            return False, 'window_title_changed'
        if not strict and target_title != current_title and not current_title.startswith(target_title[:20]):
            return False, 'window_title_changed'
    target_browser_title = target.get('browser_title') or ''
    current_browser_title = current.get('browser_title') or ''
    if strict and target_browser_title and current_browser_title and target_browser_title != current_browser_title:
        return False, 'browser_title_changed'
    return True, 'target_valid'


def restore_target_and_paste(text: str, target: dict | None, strict: bool = False) -> dict:
    target = target or {}
    app_name = target.get('app_name') or ''
    if app_name and SYSTEM == 'darwin':
        activate_app(app_name)
        time.sleep(0.12)
    current = capture_context()
    valid, reason = validate_target(target, current, strict=strict)
    if not valid:
        return failure('OS_PASTE', error='paste_target_changed', observation={**current, 'failure_class': 'paste_target_changed', 'failure_detail': reason, 'strict_validation': strict}, requires_user=True, retryable=True, result={'pasted': 0})
    pasted = paste_to_active_app(text, preserve_clipboard=True)
    pasted['observation'] = {**(pasted.get('observation') or {}), 'target_validation': reason, 'browser_url': current.get('browser_url'), 'window_title': current.get('window_title'), 'strict_validation': strict}
    return pasted


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
        ctx = capture_context()
        if ctx.get('ok'):
            return success('OS_GET_ACTIVE_CONTEXT', result=ctx, observation=ctx)
        return failure('OS_GET_ACTIVE_CONTEXT', error='active_context_failed', observation=ctx)
    if action == 'OS_READ_CLIPBOARD':
        return read_clipboard()
    if action == 'OS_WRITE_CLIPBOARD':
        return write_clipboard(args.get('text', ''))
    if action == 'OS_PASTE':
        if args.get('target'):
            return restore_target_and_paste(args.get('text', ''), args.get('target'), strict=bool(args.get('strict')))
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
