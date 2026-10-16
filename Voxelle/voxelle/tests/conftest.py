import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="voxelle-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["GNANI_API_KEY"] = ""
os.environ["VAPID_PUBLIC_KEY"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.db import db, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    init_db()
    with db() as con:
        for table in ("settings", "schedule_items", "dose_events", "push_subs", "alerts"):
            con.execute(f"DELETE FROM {table}")
    yield
