"""Data-access layer tests (U2).

Covers R1 (uniform item fields incl. notes), R2/R3 (nested categories, items at
any level), KTD2 (adjacency-list subtree traversal), KTD3 + the NULL-parent
uniqueness gap, and delete-blocking for non-empty categories.
"""
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
