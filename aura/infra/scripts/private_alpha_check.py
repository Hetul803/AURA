from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_FILES = [
    'docs/AURA_VISION_AND_BUILD_CONSTITUTION.md',
    'docs/PRIVACY.md',
    'docs/SECURITY.md',
    'docs/PACKAGING.md',
    'apps/backend/pyproject.toml',
    'apps/desktop/package.json',
    'apps/desktop/electron-builder.yml',
    'infra/releases/downloads.json',
]


def check_private_alpha_readiness(repo_root: str | Path) -> dict[str, Any]:
    root = Path(repo_root)
    checks = []
    for rel in REQUIRED_FILES:
        path = root / rel
        checks.append({'name': f'file:{rel}', 'ok': path.exists(), 'detail': str(path)})

    builder = root / 'apps/desktop/electron-builder.yml'
    text = builder.read_text(encoding='utf-8') if builder.exists() else ''
    checks.extend([
        {'name': 'desktop:product_name', 'ok': 'productName: AURA' in text, 'detail': 'electron-builder productName'},
        {'name': 'desktop:artifact_name', 'ok': 'artifactName:' in text, 'detail': 'release artifact naming'},
        {'name': 'desktop:targets', 'ok': all(token in text for token in ['nsis', 'dmg', 'AppImage']), 'detail': 'windows/mac/linux targets declared'},
    ])

    docs = (root / 'docs/AURA_VISION_AND_BUILD_CONSTITUTION.md').read_text(encoding='utf-8') if (root / 'docs/AURA_VISION_AND_BUILD_CONSTITUTION.md').exists() else ''
    checks.extend([
        {'name': 'constitution:local_first', 'ok': 'local-first' in docs.lower(), 'detail': 'local-first standard present'},
        {'name': 'constitution:approval_system', 'ok': 'Approval System' in docs, 'detail': 'approval primitive documented'},
        {'name': 'constitution:memory_engine', 'ok': 'Memory Engine' in docs, 'detail': 'memory primitive documented'},
    ])

    blockers = [item for item in checks if not item['ok']]
    return {
        'ok': not blockers,
        'checks': checks,
        'blockers': blockers,
        'summary': f"{len(checks) - len(blockers)}/{len(checks)} private alpha checks passed",
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    result = check_private_alpha_readiness(root)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
