import os
import sys
import tempfile

# Must run before app / database.db are imported: db.py reads SPENDLY_DB_PATH at
# import time and app.py seeds the database on import.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ["SPENDLY_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="spendly_import_"), "import.db"
)

import pytest  # noqa: E402

import app as app_module  # noqa: E402
from database import db  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    db.init_db()
    db.seed_db()
    app_module.app.config["TESTING"] = True
    return app_module.app


@pytest.fixture
def count_users():
    def _count():
        conn = db.get_db()
        try:
            return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()

    return _count
