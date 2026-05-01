from __future__ import annotations

import platform
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from storage.profile_paths import profile_dir
from tools.tool_result import failure, success

SYSTEM = platform.system().lower()


def _run(cmd: list[str]) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20)
        out = (p.stdout or p.stderr or '').strip()
        return p.returncode == 0, out
    except Exception as e:
        return False, str(e)


def _powershell(script: str) -> tuple[bool, str]:
    return _run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script])


def _osascript(script: str) -> tuple[bool, str]:
    return _run(['osascript', '-e', script])


def _not_supported(action: str):
    return failure(action, error='NOT_SUPPORTED_ON_THIS_OS', observation={'os': SYSTEM})


def _safe_osascript_list(script: str) -> tuple[bool, list[str]]:
    ok, out = _osascript(script)
    if not ok:
        return False, []
    return True, [line.strip() for line in out.splitlines() if line.strip()]


def _normalize_text(value: str | None) -> str:
    return ' '.join((value or '').strip().lower().split())


def _normalize_url(value: str | None) -> str:
    return (value or '').strip().lower()


def _normalized_domain(value: str | None) -> str:
    return urlparse(value or '').netloc.lower()


def _common_prefix(a: str, b: str) -> int:
    count = 0
    for left, right in zip(a, b):
        if left != right:
            break
        count += 1
    return count


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def get_browser_context(active_app: str | None = None) -> dict:
    app = active_app or (get_active_app().get('result') or {}).get('active_app')
    if not app:
        return {}
    if SYSTEM == 'windows':
        if not any(token in app.lower() for token in ['chrome', 'edge', 'firefox', 'brave', 'opera']):
            return {}
        preserved = _preserve_clipboard()
        original = preserved.get('text', '')
        press_keys('ctrl+l')
        time.sleep(0.08)
        press_keys('ctrl+c')
        time.sleep(0.08)
        captured = read_clipboard()
        if preserved.get('preserved'):
            _restore_clipboard_text(original, reason='after_url_capture')
        url = (captured.get('result') or {}).get('text', '').strip()
        if url.startswith(('http://', 'https://')):
            return {'browser_url': url, 'browser_title': get_active_window_title().get('result', {}).get('window_title', '')}
        return {}
    if SYSTEM != 'darwin':
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
    if SYSTEM == 'windows':
        ok, out = _powershell(r'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
"@
$hwnd = [Win32]::GetForegroundWindow()
$processId = 0
[Win32]::GetWindowThreadProcessId($hwnd, [ref]$processId) | Out-Null
$p = Get-Process -Id $processId
$p.ProcessName
''')
        if ok:
            app_name = out.splitlines()[-1].strip() if out.splitlines() else out.strip()
            return success('OS_GET_ACTIVE_CONTEXT', result={'active_app': app_name}, observation={'active_app': app_name})
        return failure('OS_GET_ACTIVE_CONTEXT', error=out or 'active_app_failed', observation={'active_app': ''})
    return _not_supported('OS_GET_ACTIVE_CONTEXT')


def get_active_window_title() -> dict:
    if SYSTEM == 'darwin':
        ok, out = _osascript('tell application "System Events" to tell (first process whose frontmost is true) to get name of front window')
        if ok:
            return success('OS_GET_ACTIVE_CONTEXT', result={'window_title': out}, observation={'window_title': out})
        return failure('OS_GET_ACTIVE_CONTEXT', error=out or 'window_title_failed', observation={'window_title': out})
    if SYSTEM == 'windows':
        ok, out = _powershell(r'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class Win32 {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
}
"@
$hwnd = [Win32]::GetForegroundWindow()
$sb = New-Object System.Text.StringBuilder 1024
[Win32]::GetWindowText($hwnd, $sb, $sb.Capacity) | Out-Null
$sb.ToString()
''')
        if ok:
            return success('OS_GET_ACTIVE_CONTEXT', result={'window_title': out}, observation={'window_title': out})
        return failure('OS_GET_ACTIVE_CONTEXT', error=out or 'window_title_failed', observation={'window_title': ''})
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


def _clipboard_text() -> str:
    clip = read_clipboard()
    return (clip.get('result') or {}).get('text', '') if clip.get('ok') else ''


def _preserve_clipboard() -> dict:
    clip = read_clipboard()
    if not clip.get('ok'):
        return {
            'ok': False,
            'preserved': False,
            'text': '',
            'length': 0,
            'error': clip.get('error') or 'clipboard_read_failed',
        }
    text = (clip.get('result') or {}).get('text', '')
    return {
        'ok': True,
        'preserved': True,
        'text': text,
        'length': len(text),
        'error': None,
    }


def _restore_clipboard_text(text: str, *, reason: str) -> dict:
    restored = write_clipboard(text)
    return {
        'ok': restored.get('ok', False),
        'restored': restored.get('ok', False),
        'error': None if restored.get('ok') else restored.get('error') or f'clipboard_restore_failed:{reason}',
        'reason': reason,
    }


def press_keys(keys: str) -> dict:
    if SYSTEM == 'darwin':
        mapping = {'cmd+c': 'keystroke "c" using command down', 'cmd+v': 'keystroke "v" using command down'}
        script = mapping.get(keys.lower(), f'keystroke "{keys}"')
        ok, out = _osascript(f'tell application "System Events" to {script}')
        if ok:
            return success('OS_PRESS_KEYS', result={'keys': keys}, observation={'detail': out})
        return failure('OS_PRESS_KEYS', error=out or 'keypress_failed', observation={'detail': out})
    if SYSTEM == 'windows':
        mapping = {
            'ctrl+c': '^c',
            'ctrl+v': '^v',
            'ctrl+l': '^l',
            'enter': '{ENTER}',
            'tab': '{TAB}',
            'esc': '{ESC}',
        }
        sequence = mapping.get(keys.lower(), keys)
        ok, out = _powershell(f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{sequence}')")
        if ok:
            return success('OS_PRESS_KEYS', result={'keys': keys}, observation={'detail': out})
        return failure('OS_PRESS_KEYS', error=out or 'keypress_failed', observation={'detail': out})
    return _not_supported('OS_PRESS_KEYS')


def copy_selected_text() -> dict:
    if SYSTEM not in {'darwin', 'windows'}:
        return _not_supported('OS_COPY_SELECTION')

    preserved = _preserve_clipboard()
    original_clipboard = preserved['text'] if preserved['preserved'] else ''
    key_result = press_keys('cmd+c' if SYSTEM == 'darwin' else 'ctrl+c')
    if not key_result.get('ok'):
        return failure(
            'OS_COPY_SELECTION',
            error=key_result.get('error') or 'selection_copy_failed',
            observation={
                'selection_copy_attempted': True,
                'selection_copy_succeeded': False,
                'capture_path_used': 'none',
                'clipboard_preserved': preserved['preserved'],
                'clipboard_restored_after_capture': preserved['preserved'],
                'capture_failure_reason': key_result.get('error') or 'selection_copy_failed',
            },
            result={
                'text': '',
                'length': 0,
                'capture_path_used': 'none',
                'clipboard_preserved': preserved['preserved'],
                'clipboard_restored_after_capture': preserved['preserved'],
                'original_clipboard_text': original_clipboard,
            },
        )

    selected_text = ''
    changed = False
    for _ in range(8):
        time.sleep(0.08)
        current = _clipboard_text()
        if current != original_clipboard:
            selected_text = current
            changed = True
            break

    capture_succeeded = bool(changed and selected_text.strip())
    restore = {'restored': preserved['preserved'], 'ok': preserved['preserved'], 'error': None}
    if preserved['preserved'] and changed:
        restore = _restore_clipboard_text(original_clipboard, reason='after_capture')

    if capture_succeeded:
        observation = {
            'selection_copy_attempted': True,
            'selection_copy_succeeded': True,
            'clipboard_changed_during_capture': changed,
            'capture_path_used': 'selected_text',
            'clipboard_preserved': preserved['preserved'],
            'clipboard_restored_after_capture': restore['restored'],
            'clipboard_restore_error_after_capture': restore['error'],
            'capture_failure_reason': None,
            'clipboard_length': len(selected_text),
            'clipboard_preview': selected_text[:120],
        }
        result = {
            'text': selected_text,
            'length': len(selected_text),
            'capture_path_used': 'selected_text',
            'clipboard_preserved': preserved['preserved'],
            'clipboard_restored_after_capture': restore['restored'],
            'clipboard_restore_error_after_capture': restore['error'],
            'original_clipboard_text': original_clipboard,
        }
        return success('OS_COPY_SELECTION', result=result, observation=observation, safety_flags=['clipboard_read'])

    failure_reason = 'selection_copy_no_change' if preserved['preserved'] else 'clipboard_preserve_failed'
    return failure(
        'OS_COPY_SELECTION',
        error='selection_unavailable',
        observation={
            'selection_copy_attempted': True,
            'selection_copy_succeeded': False,
            'clipboard_changed_during_capture': changed,
            'capture_path_used': 'none',
            'clipboard_preserved': preserved['preserved'],
            'clipboard_restored_after_capture': restore['restored'],
            'clipboard_restore_error_after_capture': restore['error'],
            'capture_failure_reason': failure_reason,
        },
        result={
            'text': '',
            'length': 0,
            'capture_path_used': 'none',
            'clipboard_preserved': preserved['preserved'],
            'clipboard_restored_after_capture': restore['restored'],
            'clipboard_restore_error_after_capture': restore['error'],
            'original_clipboard_text': original_clipboard,
            'selection_copy_attempted': True,
            'selection_copy_succeeded': False,
        },
        safety_flags=['clipboard_read'],
    )


def type_text(text: str) -> dict:
    if SYSTEM == 'darwin':
        esc = text.replace('"', '\\"')
        ok, out = _osascript(f'tell application "System Events" to keystroke "{esc}"')
        if ok:
            return success('OS_TYPE_TEXT', result={'typed': len(text)}, observation={'detail': out}, safety_flags=['text_entry'])
        return failure('OS_TYPE_TEXT', error=out or 'type_text_failed', observation={'detail': out})
    return _not_supported('OS_TYPE_TEXT')


def _build_target_fingerprint(*, active_app: str, window_title: str, browser: dict, capture_path_used: str) -> dict:
    browser_url = browser.get('browser_url') or ''
    browser_title = browser.get('browser_title') or window_title or ''
    return {
        'app_name': active_app,
        'window_title': window_title,
        'browser_url': browser_url,
        'browser_domain': _normalized_domain(browser_url),
        'browser_title': browser_title,
        'captured_at': _now_iso(),
        'capture_path_used': capture_path_used,
        'normalized': {
            'app_name': _normalize_text(active_app),
            'window_title': _normalize_text(window_title),
            'browser_url': _normalize_url(browser_url),
            'browser_domain': _normalized_domain(browser_url),
            'browser_title': _normalize_text(browser_title),
        },
    }


def paste_to_active_app(text: str, preserve_clipboard: bool = True) -> dict:
    preserved = _preserve_clipboard() if preserve_clipboard else {'preserved': False, 'text': '', 'error': None}
    if preserve_clipboard and not preserved['preserved']:
        return failure(
            'OS_PASTE',
            error='clipboard_preserve_failed',
            observation={
                'paste_attempted': False,
                'clipboard_preserved': False,
                'clipboard_restored_after_paste': False,
                'clipboard_restore_error_after_paste': preserved.get('error'),
                'paste_blocked_reason': 'clipboard_preserve_failed',
            },
            retryable=True,
            requires_user=True,
            result={'pasted': 0},
        )

    write_result = write_clipboard(text)
    if not write_result.get('ok'):
        return failure(
            'OS_PASTE',
            error=write_result.get('error') or 'clipboard_write_failed',
            observation={
                'paste_attempted': False,
                'clipboard_preserved': preserved['preserved'],
                'clipboard_restored_after_paste': preserved['preserved'],
                'clipboard_restore_error_after_paste': None,
                'paste_blocked_reason': 'clipboard_write_failed',
            },
            result={'pasted': 0},
        )

    keys = 'cmd+v' if SYSTEM == 'darwin' else 'ctrl+v'
    press_result = press_keys(keys)
    restore = {'restored': preserved['preserved'], 'error': None}
    if preserve_clipboard:
        restore = _restore_clipboard_text(preserved['text'], reason='after_paste')

    observation = {
        'clipboard_length': len(text),
        'active_app': active_context().get('active_app'),
        'paste_attempted': True,
        'clipboard_preserved': preserved['preserved'],
        'clipboard_restored_after_paste': restore['restored'],
        'clipboard_restore_error_after_paste': restore['error'],
        'paste_blocked_reason': None,
    }
    if press_result.get('ok'):
        return success('OS_PASTE', result={'pasted': len(text)}, observation=observation, safety_flags=['clipboard_write', 'text_entry'])
    return failure('OS_PASTE', error=press_result.get('error') or 'paste_failed', observation=observation, result={'pasted': 0})


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

    selection = copy_selected_text()
    selection_result = selection.get('result') or {}
    selection_observation = selection.get('observation') or {}
    clipboard_text = selection_result.get('original_clipboard_text', '')

    capture_path_used = 'none'
    input_text = ''
    capture_failure_reason = selection_observation.get('capture_failure_reason')
    if selection.get('ok') and selection_result.get('text'):
        capture_path_used = 'selected_text'
        input_text = selection_result.get('text', '')
        capture_failure_reason = None
    elif clipboard_text:
        capture_path_used = 'clipboard_fallback'
        input_text = clipboard_text

    target_fingerprint = _build_target_fingerprint(
        active_app=active_app_name,
        window_title=window_title,
        browser=browser,
        capture_path_used=capture_path_used,
    )

    warnings = []
    if capture_path_used != 'selected_text':
        warnings.append('selected_text_unavailable')
    if capture_path_used == 'clipboard_fallback':
        warnings.append('clipboard_fallback_used')
    if not input_text:
        warnings.append('copy_or_select_text_first')

    return {
        'ok': bool(active_app_name or window_title or input_text),
        'active_app': active_app_name,
        'window_title': window_title,
        'browser_url': browser.get('browser_url'),
        'browser_title': browser.get('browser_title') or window_title,
        'selected_text': selection_result.get('text', '') if capture_path_used == 'selected_text' else '',
        'clipboard_text': clipboard_text,
        'input_text': input_text,
        'input_source': capture_path_used,
        'capture_path_used': capture_path_used,
        'capture_method': {
            'selection_copy_attempted': selection_observation.get('selection_copy_attempted', True),
            'selection_copy_succeeded': selection_observation.get('selection_copy_succeeded', False),
            'clipboard_fallback_used': capture_path_used == 'clipboard_fallback',
            'clipboard_preserved': selection_result.get('clipboard_preserved', selection_observation.get('clipboard_preserved', False)),
            'clipboard_restored_after_capture': selection_result.get('clipboard_restored_after_capture', selection_observation.get('clipboard_restored_after_capture', False)),
            'clipboard_restore_error_after_capture': selection_result.get('clipboard_restore_error_after_capture', selection_observation.get('clipboard_restore_error_after_capture')),
            'capture_failure_reason': capture_failure_reason,
        },
        'target_fingerprint': target_fingerprint,
        'paste_target': target_fingerprint,
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
        'normalized': {
            'active_app': _normalize_text(active_app_name),
            'window_title': _normalize_text(title.get('window_title') or (title.get('result') or {}).get('window_title')),
            'browser_url': _normalize_url(browser.get('browser_url')),
            'browser_domain': _normalized_domain(browser.get('browser_url')),
            'browser_title': _normalize_text(browser.get('browser_title')),
        },
    }


def validate_target(target: dict | None, current: dict | None, strict: bool = False, cautious: bool = False) -> dict:
    target = target or {}
    current = current or {}
    if not target:
        return {
            'result': 'unknown',
            'safe_to_paste': False,
            'reason': 'no_target_fingerprint',
            'context_drift_reason': None,
            'matched_fields': [],
        }

    target_norm = target.get('normalized') or {}
    current_norm = current.get('normalized') or {}
    matched_fields: list[str] = []

    if target_norm.get('app_name') and target_norm.get('app_name') == current_norm.get('active_app'):
        matched_fields.append('app_name')
    elif target_norm.get('app_name') and current_norm.get('active_app'):
        return {
            'result': 'drifted',
            'safe_to_paste': False,
            'reason': 'active_app_changed',
            'context_drift_reason': 'active_app_changed',
            'matched_fields': matched_fields,
        }

    if target_norm.get('browser_url') and target_norm.get('browser_url') == current_norm.get('browser_url'):
        matched_fields.append('browser_url')
    elif target_norm.get('browser_domain') and current_norm.get('browser_domain'):
        if target_norm.get('browser_domain') == current_norm.get('browser_domain'):
            matched_fields.append('browser_domain')
        else:
            return {
                'result': 'drifted',
                'safe_to_paste': False,
                'reason': 'browser_domain_changed',
                'context_drift_reason': 'browser_domain_changed',
                'matched_fields': matched_fields,
            }

    target_window = target_norm.get('window_title', '')
    current_window = current_norm.get('window_title', '')
    if target_window and current_window:
        if target_window == current_window:
            matched_fields.append('window_title')
        else:
            prefix = _common_prefix(target_window, current_window)
            if prefix >= min(18, len(target_window), len(current_window)):
                matched_fields.append('window_title_prefix')
            elif strict:
                return {
                    'result': 'drifted',
                    'safe_to_paste': False,
                    'reason': 'window_title_changed',
                    'context_drift_reason': 'window_title_changed',
                    'matched_fields': matched_fields,
                }

    target_browser_title = target_norm.get('browser_title', '')
    current_browser_title = current_norm.get('browser_title', '')
    if target_browser_title and current_browser_title:
        if target_browser_title == current_browser_title:
            matched_fields.append('browser_title')
        else:
            prefix = _common_prefix(target_browser_title, current_browser_title)
            if prefix >= min(18, len(target_browser_title), len(current_browser_title)):
                matched_fields.append('browser_title_prefix')
            elif strict and 'browser_domain' in matched_fields:
                return {
                    'result': 'drifted',
                    'safe_to_paste': False,
                    'reason': 'browser_title_changed',
                    'context_drift_reason': 'browser_title_changed',
                    'matched_fields': matched_fields,
                }

    if {'app_name', 'browser_url'} <= set(matched_fields) or {'app_name', 'window_title'} <= set(matched_fields):
        return {
            'result': 'exact_match',
            'safe_to_paste': True,
            'reason': 'exact_match',
            'context_drift_reason': None,
            'matched_fields': matched_fields,
        }

    acceptable = 'app_name' in matched_fields and ({'browser_domain'} & set(matched_fields) or {'window_title_prefix', 'browser_title_prefix'} & set(matched_fields))
    if acceptable:
        return {
            'result': 'acceptable_match',
            'safe_to_paste': not (strict or cautious),
            'reason': 'acceptable_match_requires_caution' if strict or cautious else 'acceptable_match',
            'context_drift_reason': None if not (strict or cautious) else 'acceptable_match_requires_caution',
            'matched_fields': matched_fields,
        }

    return {
        'result': 'unknown',
        'safe_to_paste': False,
        'reason': 'insufficient_target_context',
        'context_drift_reason': None,
        'matched_fields': matched_fields,
    }


def restore_target_and_paste(text: str, target: dict | None, strict: bool = False, cautious: bool = False) -> dict:
    target = target or {}
    app_name = target.get('app_name') or ''
    activation = None
    if app_name and SYSTEM == 'darwin':
        activation = activate_app(app_name)
        time.sleep(0.12)

    current = active_context()
    validation = validate_target(target, current, strict=strict, cautious=cautious)
    observation = {
        **current,
        'target_fingerprint': target,
        'target_validation_result': validation['result'],
        'target_validation': validation['reason'],
        'matched_fields': validation.get('matched_fields', []),
        'context_drift_reason': validation.get('context_drift_reason'),
        'paste_attempted': False,
        'paste_blocked_reason': None,
        'strict_validation': strict,
        'cautious_validation': cautious,
        'activation_ok': None if activation is None else activation.get('ok', False),
    }
    if not validation['safe_to_paste']:
        blocked_reason = validation['reason'] if validation['result'] != 'drifted' else 'target_drift_detected'
        observation['paste_blocked_reason'] = blocked_reason
        return failure(
            'OS_PASTE',
            error='paste_target_changed' if validation['result'] == 'drifted' else 'paste_target_uncertain',
            observation={**observation, 'failure_class': 'paste_target_changed' if validation['result'] == 'drifted' else 'paste_target_uncertain', 'failure_detail': validation['reason']},
            requires_user=True,
            retryable=True,
            result={'pasted': 0},
        )

    pasted = paste_to_active_app(text, preserve_clipboard=True)
    pasted['observation'] = {
        **(pasted.get('observation') or {}),
        **observation,
        'paste_attempted': True,
        'paste_blocked_reason': None,
    }
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
            return restore_target_and_paste(args.get('text', ''), args.get('target'), strict=bool(args.get('strict')), cautious=bool(args.get('cautious')))
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
