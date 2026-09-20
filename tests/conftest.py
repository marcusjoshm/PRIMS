"""Shared pytest fixtures for PRIMS tests.

Each fixture points the data layer at a throwaway SQLite file and rebuilds the
schema, so tests never touch the real prims.db.
"""
import os
import re
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

_CSRF_INPUT = re.compile(
    r'name="csrf_token"[^>]*\svalue="([^"]+)"|value="([^"]+)"[^>]*\sname="csrf_token"'
)


def csrf_token(client, form_path="/item/new"):
    """The CSRF token a real browser would have, read off a rendered form.

    GETting the page both seeds the session token and hands back the hidden
    field the form emits, which is exactly the round trip a browser makes.
    """
    body = client.get(form_path).get_data(as_text=True)
    match = _CSRF_INPUT.search(body)
    assert match is not None, f"no csrf_token field rendered by {form_path}"
    return match.group(1) or match.group(2)


def post_form(client, path, data=None, form_path="/item/new", **kwargs):
    """POST a page form the way a browser does: with the token it rendered."""
    form = dict(data or {})
    form["csrf_token"] = csrf_token(client, form_path)
    return client.post(path, data=form, **kwargs)


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


@pytest.fixture
def app_client(client):
    """A second, independent browser session against the same app and DB.

    Its cookie jar is separate, so it stands in for someone else's browser --
    an attacker minting a token in their own session, for instance.
    """
    import app as app_module

    return app_module.app.test_client()
