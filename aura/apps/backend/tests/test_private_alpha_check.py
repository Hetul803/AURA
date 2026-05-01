import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / 'infra' / 'scripts' / 'private_alpha_check.py'
spec = importlib.util.spec_from_file_location('private_alpha_check', SCRIPT)
private_alpha_check = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(private_alpha_check)


def test_private_alpha_readiness_check_passes_for_repo():
    result = private_alpha_check.check_private_alpha_readiness(REPO_ROOT)
    assert result['ok'] is True
    assert result['blockers'] == []
    assert any(item['name'] == 'desktop:targets' for item in result['checks'])
