"""Shared pytest fixtures for PRIMS tests.

Each fixture points the data layer at a throwaway SQLite file and rebuilds the
schema, so tests never touch the real prims.db.
"""
import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture
def db_mod(tmp_path):
    import db

    db.DB_PATH = str(tmp_path / "test.db")
    db.reset_db()
    return db


@pytest.fixture
def client(tmp_path):
    import db
    import app as app_module

    db.DB_PATH = str(tmp_path / "test.db")
    db.reset_db()
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()
