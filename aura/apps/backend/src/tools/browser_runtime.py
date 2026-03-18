from __future__ import annotations
from pathlib import Path
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from storage.profile_paths import profile_dir
import threading


class BrowserManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._pw = None
        self._browser: Browser | None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._pages: dict[str, Page] = {}

    def _ensure_browser(self):
        if self._browser is None:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)

    def _state_file(self, domain: str) -> Path:
        return profile_dir() / "browser_state" / f"{domain}.json"

    def domain_for_url(self, url: str) -> str:
        host = urlparse(url).hostname or "default"
        return host.replace(".", "_")

    def page_for(self, domain: str) -> Page:
        with self._lock:
            self._ensure_browser()
            if domain in self._pages and not self._pages[domain].is_closed():
                return self._pages[domain]
            storage_path = self._state_file(domain)
            if storage_path.exists():
                ctx = self._browser.new_context(storage_state=str(storage_path))
            else:
                ctx = self._browser.new_context()
            page = ctx.new_page()
            self._contexts[domain] = ctx
            self._pages[domain] = page
            return page

    def save_state(self, domain: str):
        with self._lock:
            ctx = self._contexts.get(domain)
            if ctx:
                ctx.storage_state(path=str(self._state_file(domain)))

    def clear_session(self, domain: str):
        with self._lock:
            page = self._pages.pop(domain, None)
            if page and not page.is_closed():
                page.close()
            ctx = self._contexts.pop(domain, None)
            if ctx:
                ctx.close()
            sf = self._state_file(domain)
            if sf.exists():
                sf.unlink()


browser_manager = BrowserManager()
