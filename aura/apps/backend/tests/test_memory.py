from pathlib import Path
from datetime import datetime, timedelta
from aura.memory import write_memory, list_memories, update_memory, delete_memory
from storage.profile_paths import profile_dir
from storage.retention import enforce_retention


def test_memory_crud_and_search():
    write_memory('gmail.browser', 'Default', ['preference'], 4)
    found = list_memories('gmail')
    assert found
    mid = found[0]['id']
    assert update_memory(mid, pinned=1)
    delete_memory(mid)


def test_retention_distills_old_artifacts():
    p = profile_dir() / 'artifacts' / 'old.png'
    p.write_text('x', encoding='utf-8')
    old = datetime.utcnow() - timedelta(days=31)
    ts = old.timestamp()
    import os
    os.utime(p, (ts, ts))
    out = enforce_retention()
    assert out['deleted_raw'] >= 1
    assert Path(str(p) + '.summary.json').exists()
