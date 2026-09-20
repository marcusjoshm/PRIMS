"""Data-access layer tests (U2).

Covers R1 (uniform item fields incl. notes), R2/R3 (nested categories, items at
any level), KTD2 (adjacency-list subtree traversal), KTD3 + the NULL-parent
uniqueness gap, and delete-blocking for non-empty categories.
"""
import os
import subprocess
import sys
import textwrap

import pytest


def test_create_category_with_parent_nests_it(db_mod):
    # Covers R2.
    kitchen = db_mod.create_category("Kitchen")
    glass = db_mod.create_category("Glassware", parent_id=kitchen)
    row = db_mod.get_category(glass)
    assert row["parent_id"] == kitchen
    assert db_mod.get_subcategories(kitchen)[0]["name"] == "Glassware"


def test_same_name_different_parents_ok_same_parent_rejected(db_mod):
    # Covers R2 / KTD3.
    kitchen = db_mod.create_category("Kitchen")
    library = db_mod.create_category("Library")
    a = db_mod.create_category("Misc", parent_id=kitchen)
    b = db_mod.create_category("Misc", parent_id=library)
    assert a != b
    with pytest.raises(ValueError):
        db_mod.create_category("Misc", parent_id=kitchen)


def test_top_level_duplicate_rejected(db_mod):
    # NULL parent uniqueness is enforced in the data layer, since SQLite treats
    # NULLs as distinct in a UNIQUE(parent_id, name) constraint.
    db_mod.create_category("Kitchen")
    with pytest.raises(ValueError):
        db_mod.create_category("Kitchen")


def test_item_attaches_to_top_level_category(db_mod):
    # Covers R3 / AE4.
    library = db_mod.create_category("Library")
    item_id = db_mod.create_item("The Dispossessed", category_id=library)
    assert db_mod.get_item(item_id)["category_id"] == library


def test_item_notes_persist(db_mod):
    # Covers R1.
    records = db_mod.create_category("Records")
    item_id = db_mod.create_item("Kind of Blue", category_id=records, notes="Miles Davis, 1959")
    assert db_mod.get_item(item_id)["notes"] == "Miles Davis, 1959"


def test_category_shows_subcategories_and_direct_items(db_mod):
    # Covers R7 / AE1: a category with both a sub-category and a loose item.
    kitchen = db_mod.create_category("Kitchen")
    db_mod.create_category("Glassware", parent_id=kitchen)
    db_mod.create_item("spare sponges", category_id=kitchen)
    assert [c["name"] for c in db_mod.get_subcategories(kitchen)] == ["Glassware"]
    assert [i["name"] for i in db_mod.get_items_in_category(kitchen)] == ["spare sponges"]


def test_descendant_ids_returns_nested(db_mod):
    # Covers KTD2: subtree traversal reaches nested descendants, not just children.
    kitchen = db_mod.create_category("Kitchen")
    appliances = db_mod.create_category("Appliances", parent_id=kitchen)
    small = db_mod.create_category("Small appliances", parent_id=appliances)
    ids = db_mod.descendant_ids(kitchen)
    assert set(ids) == {kitchen, appliances, small}


def test_category_item_count_is_subtree_wide(db_mod):
    # Tile counts include items nested under sub-categories.
    kitchen = db_mod.create_category("Kitchen")
    glass = db_mod.create_category("Glassware", parent_id=kitchen)
    db_mod.create_item("spare sponges", category_id=kitchen)
    db_mod.create_item("pint glass", category_id=glass, quantity=6)
    assert db_mod.category_item_count(kitchen) == 2
    assert db_mod.category_item_count(glass) == 1


def test_delete_nonempty_category_blocked(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    db_mod.create_item("spare sponges", category_id=kitchen)
    with pytest.raises(ValueError):
        db_mod.delete_category(kitchen)


def test_delete_empty_category_succeeds(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    empty = db_mod.create_category("Empty", parent_id=kitchen)
    db_mod.delete_category(empty)
    assert db_mod.get_category(empty) is None


def test_update_item_changes_quantity(db_mod):
    # Covers R11 at the data layer.
    kitchen = db_mod.create_category("Kitchen")
    item_id = db_mod.create_item("pint glass", category_id=kitchen, quantity=6)
    db_mod.update_item(item_id, name="pint glass", category_id=kitchen,
                       location_id=None, quantity=5, notes="")
    assert db_mod.get_item(item_id)["quantity"] == 5


def test_get_or_create_location_is_idempotent(db_mod):
    a = db_mod.get_or_create_location("Cupboard")
    b = db_mod.get_or_create_location("Cupboard")
    assert a == b
    assert db_mod.get_or_create_location("") is None


# --- Renaming a category (A1/A2) ------------------------------------------

def test_rename_onto_existing_top_level_name_rejected(db_mod):
    # The NULL-parent duplicate check create_category performs has to apply to
    # renames too, or two top-level "Kitchen" collections can coexist.
    db_mod.create_category("Kitchen")
    library = db_mod.create_category("Library")
    with pytest.raises(ValueError):
        db_mod.update_category(library, "Kitchen")
    assert [c["name"] for c in db_mod.get_top_level_categories()] == ["Kitchen", "Library"]


def test_rename_category_to_its_own_name_is_allowed(db_mod):
    # The duplicate check must exclude the row being renamed.
    kitchen = db_mod.create_category("Kitchen")
    db_mod.update_category(kitchen, "Kitchen")
    assert db_mod.get_category(kitchen)["name"] == "Kitchen"


def test_rename_onto_sibling_name_raises_value_error(db_mod):
    # UNIQUE(parent_id, name) fires here; it must surface as a user-correctable
    # ValueError, not a raw sqlite3.IntegrityError (which the route 500s on).
    kitchen = db_mod.create_category("Kitchen")
    db_mod.create_category("Glassware", parent_id=kitchen)
    mugs = db_mod.create_category("Mugs", parent_id=kitchen)
    with pytest.raises(ValueError):
        db_mod.update_category(mugs, "Glassware")


# --- Unknown foreign keys on items (A3) -----------------------------------

def test_create_item_with_unknown_category_raises_value_error(db_mod):
    with pytest.raises(ValueError):
        db_mod.create_item("Ghost", category_id=999)


def test_create_item_with_unknown_location_raises_value_error(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    with pytest.raises(ValueError):
        db_mod.create_item("Ghost", category_id=kitchen, location_id=999)


def test_update_item_with_unknown_category_raises_value_error(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    item = db_mod.create_item("Pint glass", category_id=kitchen)
    with pytest.raises(ValueError):
        db_mod.update_item(item, name="Pint glass", category_id=999,
                           location_id=None, quantity=1, notes="")


def test_update_item_with_unknown_location_raises_value_error(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    item = db_mod.create_item("Pint glass", category_id=kitchen)
    with pytest.raises(ValueError):
        db_mod.update_item(item, name="Pint glass", category_id=kitchen,
                           location_id=999, quantity=1, notes="")


# --- Deleting a location (A4) ---------------------------------------------

def test_delete_location_still_referenced_by_an_item_blocked(db_mod):
    kitchen = db_mod.create_category("Kitchen")
    cupboard = db_mod.get_or_create_location("Cupboard")
    db_mod.create_item("Pint glass", category_id=kitchen, location_id=cupboard)
    with pytest.raises(ValueError):
        db_mod.delete_location(cupboard)
    assert db_mod.get_location(cupboard) is not None


def test_delete_unused_location_succeeds(db_mod):
    cupboard = db_mod.get_or_create_location("Cupboard")
    db_mod.delete_location(cupboard)
    assert db_mod.get_location(cupboard) is None


# --- Parent validation (A5/A6a) -------------------------------------------

def test_create_category_under_unknown_parent_names_the_missing_parent(db_mod):
    with pytest.raises(ValueError) as excinfo:
        db_mod.create_category("Ghost", parent_id=9999)
    message = str(excinfo.value)
    assert "9999" in message
    assert "already exists" not in message


def test_create_category_cannot_parent_itself(db_mod):
    # A category cannot be its own parent: the id it is about to receive does
    # not exist yet, so the parent check rejects it. A self-parented row makes
    # the recursive CTEs loop forever.
    conn = db_mod.get_conn()
    try:
        next_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next FROM categories"
        ).fetchone()["next"]
    finally:
        conn.close()
    with pytest.raises(ValueError):
        db_mod.create_category("Loop", parent_id=next_id)
    assert db_mod.get_category(next_id) is None


# --- Corrupt-tree defence in depth (A6b) ----------------------------------

def _corrupt_db_with_self_parented_row(db_mod):
    """Force a self-parented category straight into SQLite, bypassing validation.

    Simulates a row that predates (or sidesteps) the parent check, so the
    recursive CTEs have to defend themselves.
    """
    conn = db_mod.get_conn()
    try:
        conn.execute("INSERT INTO categories (id, name, parent_id) VALUES (1, 'Loop', 1)")
        conn.commit()
    finally:
        conn.close()
    return 1


def _call_in_subprocess(db_path, expression, timeout=10):
    """Evaluate a db expression in a fresh process, bounded by a real timeout.

    Run in-process, an unbounded recursive CTE over a self-parented row never
    returns, so the test would hang the whole suite rather than fail.
    """
    code = textwrap.dedent(
        f"""
        import os, sys
        sys.path.insert(0, {repr(os.path.join(os.path.dirname(__file__), "..", "src"))})
        import db
        db.DB_PATH = {db_path!r}
        print(repr({expression}))
        """
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=timeout,
    )


def test_recursive_helpers_terminate_on_a_self_parented_row(db_mod):
    loop = _corrupt_db_with_self_parented_row(db_mod)
    db_mod.create_item("orphan", category_id=loop)
    for expression in (
        f"len(db.descendant_ids({loop}))",
        f"db.category_item_count({loop})",
        f"len(db.get_ancestors({loop}))",
    ):
        try:
            result = _call_in_subprocess(db_mod.DB_PATH, expression)
        except subprocess.TimeoutExpired:
            pytest.fail(f"{expression} did not terminate on a self-parented row")
        assert result.returncode == 0, result.stderr
        assert int(result.stdout.strip()) <= 200, expression
