"""In-place upgrade of a pre-branch prims.db (B1).

The old schema (main's ``src/app.py``) had ``categories(id, name UNIQUE)``,
an ``inventory`` without ``notes``, and no ``parent_id`` anywhere.
``CREATE TABLE IF NOT EXISTS`` is a no-op against tables that already exist,
so ``init_db()`` has to add the new columns itself. It must do that without
dropping anything: the only other documented recovery is ``seed.py``, which
wipes the database, so a user with real data would be told to destroy it.

Nothing here may touch the real prims.db -- every test builds its own old-schema
file under tmp_path and points ``db.DB_PATH`` at it.
"""
import sqlite3

import pytest


# Exactly what main's init_db() created, before this branch.
OLD_SCHEMA = """
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category_id INTEGER,
        location_id INTEGER,
        quantity INTEGER DEFAULT 0,
        FOREIGN KEY (category_id) REFERENCES categories(id),
        FOREIGN KEY (location_id) REFERENCES locations(id)
    );
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS locations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
"""


def _columns(path, table):
    conn = sqlite3.connect(path)
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def _unique_indexed_columns(path, table):
    """The column tuples covered by a UNIQUE index on this table."""
    conn = sqlite3.connect(path)
    try:
        covered = set()
        for index in conn.execute(f"PRAGMA index_list({table})").fetchall():
            name, unique = index[1], index[2]
            if not unique:
                continue
            cols = tuple(
                row[2] for row in conn.execute(f"PRAGMA index_info('{name}')")
            )
            covered.add(cols)
        return covered
    finally:
        conn.close()


@pytest.fixture
def old_db(tmp_path):
    """A populated database built by the OLD code, with db pointed at it."""
    import db

    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute("INSERT INTO categories (id, name) VALUES (1, 'Garage')")
    conn.execute("INSERT INTO locations (id, name) VALUES (1, 'Shed')")
    conn.execute(
        "INSERT INTO inventory (id, name, category_id, location_id, quantity) "
        "VALUES (1, 'Snow shovel', 1, 1, 2)"
    )
    conn.commit()
    conn.close()

    db.DB_PATH = path
    return db


# --- The columns the new code needs ----------------------------------------

def test_init_db_adds_parent_id_to_an_existing_categories_table(old_db):
    old_db.init_db()

    assert "parent_id" in _columns(old_db.DB_PATH, "categories")


def test_init_db_adds_notes_to_an_existing_inventory_table(old_db):
    old_db.init_db()

    assert "notes" in _columns(old_db.DB_PATH, "inventory")


# --- Nothing may be lost ---------------------------------------------------

def test_upgrading_keeps_every_pre_existing_row(old_db):
    old_db.init_db()

    categories = old_db.get_all_categories()
    items = old_db.get_all_items()
    locations = old_db.get_locations()

    assert [row["name"] for row in categories] == ["Garage"]
    assert [row["name"] for row in locations] == ["Shed"]
    assert [(row["name"], row["quantity"]) for row in items] == [("Snow shovel", 2)]


def test_upgraded_categories_become_top_level_collections(old_db):
    old_db.init_db()

    assert old_db.get_all_categories()[0]["parent_id"] is None
    assert [row["name"] for row in old_db.get_top_level_categories()] == ["Garage"]


def test_upgraded_items_come_back_with_empty_notes(old_db):
    old_db.init_db()

    assert old_db.get_all_items()[0]["notes"] == ""


# --- The upgraded database actually works ----------------------------------

def test_the_new_data_layer_works_against_an_upgraded_database(old_db):
    old_db.init_db()

    garage = old_db.get_top_level_categories()[0]["id"]
    tools = old_db.create_category("Tools", parent_id=garage)
    old_db.create_item("Hex key set", category_id=tools, quantity=1, notes="Metric")

    assert [row["name"] for row in old_db.get_subcategories(garage)] == ["Tools"]
    assert old_db.category_item_count(garage) == 2
    assert [row["name"] for row in old_db.search_items("metric")] == ["Hex key set"]


def test_upgrading_is_idempotent(old_db):
    old_db.init_db()
    old_db.init_db()

    assert _columns(old_db.DB_PATH, "categories").count("parent_id") == 1
    assert _columns(old_db.DB_PATH, "inventory").count("notes") == 1
    assert [row["name"] for row in old_db.get_all_items()] == ["Snow shovel"]


# --- Fresh and upgraded databases enforce the same nesting constraint ------

def test_upgraded_database_rejects_a_duplicate_name_under_one_parent(old_db):
    old_db.init_db()

    garage = old_db.get_top_level_categories()[0]["id"]
    old_db.create_category("Tools", parent_id=garage)
    with pytest.raises(ValueError):
        old_db.create_category("Tools", parent_id=garage)


def test_upgraded_schema_carries_the_same_unique_index_as_a_fresh_one(
    old_db, tmp_path
):
    old_db.init_db()
    upgraded = old_db.DB_PATH

    old_db.DB_PATH = str(tmp_path / "fresh.db")
    old_db.init_db()
    fresh = old_db.DB_PATH

    assert ("parent_id", "name") in _unique_indexed_columns(fresh, "categories")
    assert ("parent_id", "name") in _unique_indexed_columns(upgraded, "categories")
