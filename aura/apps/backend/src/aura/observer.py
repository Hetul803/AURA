from __future__ import annotations
from playwright.sync_api import Page
from tools.os_automation import active_context


def current_url(page: Page) -> str:
    return page.url


def page_title(page: Page) -> str:
    try:
        return page.title()
    except Exception:
        return ""


def login_needed(page: Page) -> bool:
    url = page.url.lower()
    if 'accounts.google.com' in url:
        return True
    txt = page.content().lower()
    return any(t in txt for t in ['sign in', 'login', 'captcha', 'verify it\'s you'])


def element_exists(page: Page, selector: str) -> bool:
    try:
        return page.locator(selector).count() > 0
    except Exception:
        return False


def element_visible(page: Page, selector: str) -> bool:
    try:
        return page.locator(selector).first.is_visible(timeout=500)
    except Exception:
        return False


def gmail_unread_count(page: Page) -> int:
    selectors = ['tr.zE', '[aria-label*="unread"]', '[data-thread-id].zE']
    for sel in selectors:
        try:
            count = page.locator(sel).count()
            if count:
                return count
        except Exception:
            pass
    return 0


def browser_file_picker_open(page: Page) -> bool:
    # best-effort signal: any visible file input
    return element_visible(page, 'input[type="file"]')


def snapshot(page: Page) -> dict:
    os_ctx = active_context()
    return {
        'url': current_url(page),
        'title': page_title(page),
        'login_required': login_needed(page),
        'gmail_unread': gmail_unread_count(page),
        'file_picker_open': browser_file_picker_open(page),
        'active_app': os_ctx.get('active_app'),
        'active_window_title': os_ctx.get('window_title'),
        'clipboard_length': os_ctx.get('clipboard_length', 0),
    }
