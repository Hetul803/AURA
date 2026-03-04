#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys, time
from datetime import datetime
from pathlib import Path

stamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
outdir = Path('test_runs') / stamp
outdir.mkdir(parents=True, exist_ok=True)

payload = {
  'timestamp': stamp,
  'suites': json.loads(sys.argv[1]),
  'duration_seconds': float(sys.argv[2]),
  'environment': {'python': sys.version.split()[0], 'node': os.popen('node -v').read().strip()},
  'git_commit': os.popen('git rev-parse --short HEAD 2>/dev/null').read().strip() or None
}
(outdir / 'results.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')
print(outdir / 'results.json')
