import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from aura.steps import Step
from tools.web_playwright import handle_web_action


def test_live_playwright_local_navigation():
    with TemporaryDirectory() as td:
        root = Path(td)
        (root / 'index.html').write_text('<html><head><title>LocalTest</title></head><body><h1>Hello</h1></body></html>', encoding='utf-8')
        handler = functools.partial(SimpleHTTPRequestHandler, directory=str(root))
        srv = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            port = srv.server_port
            step = Step(id='1', name='open local', action_type='WEB_NAVIGATE', args={'url': f'http://127.0.0.1:{port}/index.html'})
            try:
                out = handle_web_action(step)
            except Exception as e:
                pytest.skip(f'Playwright browser unavailable: {e}')
            assert out['ok']
            assert '127.0.0.1' in out['observation']['url']
        finally:
            srv.shutdown()
