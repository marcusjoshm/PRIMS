"""Data-access layer for PRIMS (U2).

One module owns every SQLite read and write so the web pages, the JSON API, and
the seed script share one implementation (KTD5). Rows come back as
``sqlite3.Row`` (dict-like) rather than raw tuples.

Schema (KTD2/KTD3/KTD4):
  categories  id, name, parent_id -> categories.id (NULL = top-level collection)
              UNIQUE(parent_id, name); top-level NULL-parent uniqueness is
              enforced in create_category() because SQLite treats NULLs as
              distinct in a UNIQUE constraint.
  locations   id, name UNIQUE
  inventory   id, name, category_id, location_id, quantity, notes
"""
import os
import sqlite3

# Resolved at call time so tests can point DB_PATH at a throwaway file.
DB_PATH = os.environ.get("PRIMS_DB", "prims.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if they do not exist. Does not alter an existing DB."""
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER REFERENCES categories(id),
            UNIQUE (parent_id, name)
        );
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER REFERENCES categories(id),
            location_id INTEGER REFERENCES locations(id),
            quantity INTEGER DEFAULT 0,
            notes TEXT DEFAULT ''
        );
        """
    )
    conn.commit()
    conn.close()


def reset_db():
    """Drop and recreate the schema.

    CREATE TABLE IF NOT EXISTS will not add new columns to a pre-existing
    prims.db, so a schema change (or the seed script, per KTD4) must rebuild
    from scratch. The DB is single-user, git-ignored test data.
    """
    conn = get_conn()
    conn.executescript(
        """
        DROP TABLE IF EXISTS inventory;
        DROP TABLE IF EXISTS locations;
        DROP TABLE IF EXISTS categories;
        """
    )
    conn.commit()
    conn.close()
    init_db()


# --- Categories -----------------------------------------------------------

def create_category(name, parent_id=None):
    """Create a category, rejecting a duplicate name under the same parent.

    The DB constraint covers non-NULL parents; the top-level (NULL parent)
    case is checked here because SQLite treats NULLs as distinct.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    conn = get_conn()
    try:
        if parent_id is None:
            existing = conn.execute(
                "SELECT 1 FROM categories WHERE parent_id IS NULL AND name = ?",
                (name,),
            ).fetchone()
            if existing:
                raise ValueError(f"A top-level category named '{name}' already exists")
        try:
            cur = conn.execute(
                "INSERT INTO categories (name, parent_id) VALUES (?, ?)",
                (name, parent_id),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                f"A category named '{name}' already exists under this parent"
            ) from exc
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_category(category_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM categories WHERE id = ?", (category_id,)
        ).fetchone()
    finally:
        conn.close()


def get_top_level_categories():
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name"
        ).fetchall()
    finally:
        conn.close()


def get_subcategories(parent_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM categories WHERE parent_id = ? ORDER BY name",
            (parent_id,),
        ).fetchall()
    finally:
        conn.close()


def get_all_categories():
    """Every category, ordered for building a tree picker."""
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    finally:
        conn.close()


def descendant_ids(category_id):
    """Return category_id plus all nested descendant ids (recursive CTE, KTD2)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM categories WHERE id = ?
                UNION ALL
                SELECT c.id FROM categories c JOIN subtree s ON c.parent_id = s.id
            )
            SELECT id FROM subtree
            """,
            (category_id,),
        ).fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def category_item_count(category_id):
    """Count items in a category and every category nested beneath it."""
    conn = get_conn()
    try:
        row = conn.execute(
            """
            WITH RECURSIVE subtree(id) AS (
                SELECT id FROM categories WHERE id = ?
                UNION ALL
                SELECT c.id FROM categories c JOIN subtree s ON c.parent_id = s.id
            )
            SELECT COUNT(*) AS n FROM inventory
            WHERE category_id IN (SELECT id FROM subtree)
            """,
            (category_id,),
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def get_ancestors(category_id):
    """Return categories from the top-level root down to (and including) this one.

    One recursive CTE rather than a query per level: the search page calls this
    once per result, so walking the chain in Python opened a connection for
    every ancestor of every hit. Returns [] for an unknown id.
    """
    conn = get_conn()
    try:
        return conn.execute(
            """
            WITH RECURSIVE chain(id, name, parent_id, depth) AS (
                SELECT id, name, parent_id, 0 FROM categories WHERE id = ?
                UNION ALL
                SELECT c.id, c.name, c.parent_id, chain.depth + 1
                FROM categories c JOIN chain ON c.id = chain.parent_id
            )
            SELECT id, name, parent_id FROM chain ORDER BY depth DESC
            """,
            (category_id,),
        ).fetchall()
    finally:
        conn.close()


def update_category(category_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE categories SET name = ? WHERE id = ?", (name, category_id)
        )
        conn.commit()
    finally:
        conn.close()


def category_is_empty(category_id):
    return not get_subcategories(category_id) and not get_items_in_category(category_id)


def delete_category(category_id):
    """Delete a category only when it has no sub-categories and no items."""
    if not category_is_empty(category_id):
        raise ValueError("Cannot delete a category that still has sub-categories or items")
    conn = get_conn()
    try:
        conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
        conn.commit()
    finally:
        conn.close()


# --- Items ----------------------------------------------------------------

def create_item(name, category_id, location_id=None, quantity=0, notes=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Item name is required")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO inventory (name, category_id, location_id, quantity, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, category_id, location_id, quantity, notes or ""),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_item(item_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM inventory WHERE id = ?", (item_id,)
        ).fetchone()
    finally:
        conn.close()


def get_items_in_category(category_id):
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM inventory WHERE category_id = ? ORDER BY name",
            (category_id,),
        ).fetchall()
    finally:
        conn.close()


def get_all_items():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM inventory ORDER BY name").fetchall()
    finally:
        conn.close()


def update_item(item_id, name, category_id, location_id, quantity, notes):
    name = (name or "").strip()
    if not name:
        raise ValueError("Item name is required")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE inventory SET name = ?, category_id = ?, location_id = ?, "
            "quantity = ?, notes = ? WHERE id = ?",
            (name, category_id, location_id, quantity, notes or "", item_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_item(item_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        conn.commit()
    finally:
        conn.close()


def search_items(query):
    """Find items whose name or notes match the query (case-insensitive), across
    all collections. Empty query returns nothing.

    ``%`` and ``_`` are LIKE wildcards, but someone typing "100%" or "a_b" into
    the search box means those characters literally, so they are escaped (along
    with the backslash that escapes them) rather than passed through.
    """
    query = (query or "").strip()
    if not query:
        return []
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    like = f"%{escaped}%"
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM inventory "
            "WHERE name COLLATE NOCASE LIKE ? ESCAPE '\\' "
            "OR notes COLLATE NOCASE LIKE ? ESCAPE '\\' ORDER BY name",
            (like, like),
        ).fetchall()
    finally:
        conn.close()


# --- Locations ------------------------------------------------------------

def get_or_create_location(name):
    """Return the id for a location name, creating it if new. Blank name -> None."""
    name = (name or "").strip()
    if not name:
        return None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM locations WHERE name = ?", (name,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute("INSERT INTO locations (name) VALUES (?)", (name,))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_location(location_id):
    if location_id is None:
        return None
    conn = get_conn()
    try:
        return conn.execute(
            "SELECT * FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
    finally:
        conn.close()


def get_locations():
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM locations ORDER BY name").fetchall()
    finally:
        conn.close()


def update_location(location_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Location name is required")
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE locations SET name = ? WHERE id = ?", (name, location_id)
        )
        conn.commit()
    finally:
        conn.close()


def delete_location(location_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
        conn.commit()
    finally:
        conn.close()
