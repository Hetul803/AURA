#!/usr/bin/env bash
set -euo pipefail
start=$(python3 - <<'PY'
import time; print(time.time())
PY
)
logdir=$(mktemp -d)

suites='[]'
run_suite() {
  name=$1; shift
  if "$@" >"$logdir/$name.log" 2>&1; then
    status=pass
  else
    status=fail
  fi
  suites=$(python3 - <<PY
import json
arr=json.loads('''$suites''')
arr.append({'name':'$name','status':'$status','log':'$logdir/$name.log'})
print(json.dumps(arr))
PY
)
  [[ "$status" == "pass" ]] || { cat "$logdir/$name.log"; exit 1; }
}

run_suite backend bash -lc "cd apps/backend && pytest -q"
run_suite desktop bash -lc "cd apps/desktop && pnpm test"
run_suite desktop_build_sanity bash -lc "cd apps/desktop && pnpm build"
run_suite web bash -lc "cd apps/web && NODE_ENV=test pnpm test"

end=$(python3 - <<'PY'
import time; print(time.time())
PY
)
dur=$(python3 - <<PY
print(round($end-$start,2))
PY
)
python3 infra/scripts/write_test_run.py "$suites" "$dur"
