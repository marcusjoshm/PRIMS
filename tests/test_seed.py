"""Seed-script tests (U6).

Covers R5 (three collections populated with nested sub-types and items), AE1
(Kitchen holds sub-categories *and* a loose item), AE2 ("Kind of Blue" with
"Miles Davis, 1959" in its notes, findable by searching "Miles"), and the
destructive-run guard: the script rebuilds the schema, so running it against a
populated database must ask first.

Every test drives ``seed.seed()`` (or ``seed.main()`` with an explicit argv)
directly against the throwaway DB the fixtures create -- nothing here may block
on stdin, and nothing may touch the real prims.db.
"""
import pytest


def _db():
    """The data layer, already pointed at the throwaway DB by the fixtures."""
    import db

    return db


def _seed_mod():
    """The seed module. Imported after a fixture has redirected db.DB_PATH."""
    import seed

    return seed


def _html(response):
    return response.get_data(as_text=True)


def _top(name):
    """The top-level collection row with this name, or None."""
    db = _db()
    for row in db.get_top_level_categories():
        if row["name"] == name:
            return row
    return None


def _child(parent_id, name):
    db = _db()
    for row in db.get_subcategories(parent_id):
        if row["name"] == name:
            return row
    return None


def _no_prompt(monkeypatch):
    """Make any interactive prompt an immediate, loud failure."""
    def _boom(*args, **kwargs):
        raise AssertionError("seed prompted for confirmation when it should not have")

    monkeypatch.setattr("builtins.input", _boom)


# --- Collections and nesting (R5) ------------------------------------------

def test_seed_creates_the_three_collections(db_mod):
    # Covers R5.
    _seed_mod().seed()

    names = [row["name"] for row in db_mod.get_top_level_categories()]
    assert "Kitchen" in names
    assert "Library" in names
    assert "Records" in names


def test_kitchen_nests_the_expected_sub_types(db_mod):
    # Covers R5: Kitchen's sub-types are real nested categories, not name prefixes.
    _seed_mod().seed()

    kitchen = _top("Kitchen")
    sub_names = [row["name"] for row in db_mod.get_subcategories(kitchen["id"])]
    for expected in ("Glassware", "Appliances", "Dishes"):
        assert expected in sub_names


def test_nested_sub_categories_actually_hold_items(db_mod):
    # Covers R5: nesting is populated, not an empty skeleton.
    _seed_mod().seed()

    kitchen = _top("Kitchen")
    for name in ("Glassware", "Appliances", "Dishes"):
        sub = _child(kitchen["id"], name)
        assert db_mod.get_items_in_category(sub["id"]), f"{name} has no items"


def test_every_collection_holds_a_dozen_plus_items(db_mod):
    # Covers R5: the interface is populated, not a token entry per collection.
    _seed_mod().seed()

    for name in ("Kitchen", "Library", "Records"):
        count = db_mod.category_item_count(_top(name)["id"])
        assert count >= 12, f"{name} only has {count} items"


# --- AE1: a loose item attached directly to a collection --------------------

def test_kitchen_holds_a_loose_item_attached_directly(db_mod):
    # Supports AE1: an item hangs off Kitchen itself, not off a sub-category.
    _seed_mod().seed()

    kitchen = _top("Kitchen")
    loose = [row["name"] for row in db_mod.get_items_in_category(kitchen["id"])]
    assert loose, "Kitchen has no directly-attached items"
    assert any("sponge" in name.lower() for name in loose), loose


def test_opening_kitchen_shows_sub_categories_and_the_loose_item_together(client):
    # Supports AE1, end to end through the U3 category page.
    _seed_mod().seed()

    kitchen = _top("Kitchen")
    body = _html(client.get(f"/category/{kitchen['id']}"))
    assert "Glassware" in body
    assert "Appliances" in body
    assert 'id="subcategories"' in body
    assert 'id="items"' in body
    assert "sponge" in body.lower()


# --- AE2: artist in notes, found by search ---------------------------------

def test_seed_creates_kind_of_blue_with_the_artist_in_notes(db_mod):
    # Supports AE2 + KD1: artist and year live in notes, not in new columns.
    _seed_mod().seed()

    matches = [row for row in db_mod.get_all_items() if row["name"] == "Kind of Blue"]
    assert len(matches) == 1, matches
    assert matches[0]["notes"] == "Miles Davis, 1959"


def test_searching_miles_finds_kind_of_blue(client):
    # Supports AE2 end to end through the U4 search page.
    _seed_mod().seed()

    resp = client.get("/search?q=Miles")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Kind of Blue" in body


def test_library_books_capture_the_author_in_notes(client):
    # Covers R5 + KD1: a book is findable by an author who appears only in notes.
    _seed_mod().seed()

    library = _top("Library")
    books = _db().get_items_in_category(library["id"])
    nested = [
        item
        for sub in _db().get_subcategories(library["id"])
        for item in _db().get_items_in_category(sub["id"])
    ]
    with_notes = [row for row in books + nested if row["notes"].strip()]
    assert len(with_notes) >= 10, "Library books should record their author in notes"

    author = with_notes[0]["notes"].split(",")[0].split()[-1]
    assert with_notes[0]["name"] in _html(client.get(f"/search?q={author}"))


# --- Home page -------------------------------------------------------------

def test_home_shows_three_collections_with_non_zero_counts(client):
    # Covers R5 through R6's home tiles: populated on first open.
    _seed_mod().seed()

    body = _html(client.get("/"))
    assert "Kitchen" in body
    assert "Library" in body
    assert "Records" in body
    assert "empty-state" not in body
    assert "0 items" not in body


# --- Re-runnability --------------------------------------------------------

def test_seeding_twice_rebuilds_rather_than_duplicating(db_mod):
    # KTD4: the seed rebuilds the schema, so a second run is not additive.
    seed = _seed_mod()
    seed.seed()
    first = len(db_mod.get_all_items())

    seed.seed()
    assert len(db_mod.get_all_items()) == first
    assert len([r for r in db_mod.get_top_level_categories() if r["name"] == "Kitchen"]) == 1


def test_seed_replaces_pre_existing_unrelated_data(db_mod):
    # KTD4: rebuilding drops whatever was there before.
    db_mod.create_category("Garage")
    seed = _seed_mod()
    seed.seed()

    assert [r["name"] for r in db_mod.get_top_level_categories()] == [
        "Kitchen",
        "Library",
        "Records",
    ]


def test_seed_returns_a_summary_of_what_it_created(db_mod):
    summary = _seed_mod().seed()

    assert set(summary) == {"Kitchen", "Library", "Records"}
    assert all(count >= 12 for count in summary.values()), summary


def test_seed_prints_a_summary(db_mod, capsys):
    _seed_mod().seed()

    out = capsys.readouterr().out
    assert "Kitchen" in out
    assert "Library" in out
    assert "Records" in out


# --- Destructive-run guard -------------------------------------------------

def test_main_seeds_an_empty_database_without_prompting(db_mod, monkeypatch):
    _no_prompt(monkeypatch)

    assert _seed_mod().main([]) == 0
    assert _top("Kitchen") is not None


def test_main_refuses_to_wipe_a_populated_database_when_declined(db_mod, monkeypatch):
    db_mod.create_category("Garage")
    garage = _top("Garage")
    db_mod.create_item("Snow shovel", category_id=garage["id"], quantity=1)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "n")

    assert _seed_mod().main([]) != 0
    assert _top("Garage") is not None
    assert [r["name"] for r in db_mod.get_all_items()] == ["Snow shovel"]


def test_main_wipes_a_populated_database_when_confirmed(db_mod, monkeypatch):
    garage = db_mod.create_category("Garage")
    db_mod.create_item("Snow shovel", category_id=garage, quantity=1)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "y")

    assert _seed_mod().main([]) == 0
    assert _top("Garage") is None
    assert _top("Kitchen") is not None


@pytest.mark.parametrize("flag", ["--force", "--yes"])
def test_force_flag_skips_the_prompt_entirely(db_mod, monkeypatch, flag):
    # Non-interactive use must never block on stdin.
    garage = db_mod.create_category("Garage")
    db_mod.create_item("Snow shovel", category_id=garage, quantity=1)
    _no_prompt(monkeypatch)

    assert _seed_mod().main([flag]) == 0
    assert _top("Kitchen") is not None


def test_a_populated_database_that_only_has_categories_still_seeds_unprompted(
    db_mod, monkeypatch
):
    # The guard protects real inventory; an empty schema with a stray category
    # is not data worth blocking on.
    db_mod.create_category("Garage")
    _no_prompt(monkeypatch)

    assert _seed_mod().main([]) == 0


def test_guard_treats_a_missing_schema_as_empty(tmp_path, monkeypatch):
    # A fresh checkout has no prims.db at all: connecting finds no tables.
    import db

    db.DB_PATH = str(tmp_path / "absent.db")
    _no_prompt(monkeypatch)

    assert _seed_mod().main([]) == 0
    assert _top("Kitchen") is not None


def test_declined_prompt_reports_why_nothing_happened(db_mod, monkeypatch, capsys):
    garage = db_mod.create_category("Garage")
    db_mod.create_item("Snow shovel", category_id=garage, quantity=1)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")

    _seed_mod().main([])
    assert "Aborted" in capsys.readouterr().out


def test_seed_targets_whatever_db_path_currently_points_at(tmp_path):
    # The seeding logic must not hardcode a path, or tests would hit prims.db.
    import db

    target = tmp_path / "elsewhere.db"
    db.DB_PATH = str(target)
    _seed_mod().seed()

    assert target.exists()
    assert _top("Kitchen") is not None
