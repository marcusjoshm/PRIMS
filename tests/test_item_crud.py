"""Item add / edit / delete tests (U5).

Covers R10 (add an item, choosing an existing category or creating one
inline, with name/quantity/notes/location), R11/AE3 (edit an item including
its quantity), R12 (delete an item), R3/AE4 (attach an item directly to a
top-level collection) and flow F3 (add after shopping).
"""


def _db():
    """The data layer, already pointed at the throwaway DB by the client fixture."""
    import db

    return db


def _html(response):
    return response.get_data(as_text=True)


def _kitchen_tree():
    """Kitchen > Glassware, the fixture most add/edit tests hang off."""
    db = _db()
    kitchen = db.create_category("Kitchen")
    glassware = db.create_category("Glassware", parent_id=kitchen)
    return kitchen, glassware


def _pint_glasses_with_quantity_six():
    """The literal AE3 fixture: a pint-glass item with quantity 6."""
    db = _db()
    _, glassware = _kitchen_tree()
    item = db.create_item("Pint glass", category_id=glassware, quantity=6)
    return item


# --- Reaching the add form (R10 / F3) --------------------------------------

def test_home_offers_an_add_item_entry_point(client):
    # Covers R10: the add form is only real if the owner can reach it.
    body = _html(client.get("/"))
    assert "/item/new" in body


def test_add_form_lists_every_category_including_top_level(client):
    # Covers R10 with KD2/R3: items attach at any level, so the picker must
    # offer top-level collections as well as nested categories.
    kitchen, glassware = _kitchen_tree()

    resp = client.get("/item/new")
    body = _html(resp)
    assert resp.status_code == 200
    assert f'value="{kitchen}"' in body
    assert f'value="{glassware}"' in body
    assert "Glassware" in body


def test_add_form_prefills_the_category_it_was_opened_from(client):
    kitchen, glassware = _kitchen_tree()

    body = _html(client.get(f"/item/new?category_id={glassware}"))
    assert f'value="{glassware}" selected' in body


def test_category_page_offers_add_item_prefilled(client):
    _, glassware = _kitchen_tree()

    body = _html(client.get(f"/category/{glassware}"))
    assert f"/item/new?category_id={glassware}" in body


# --- Adding (R10) ----------------------------------------------------------

def test_add_item_with_an_existing_category_persists_and_appears_under_it(client):
    # Covers R10.
    db = _db()
    _, glassware = _kitchen_tree()

    resp = client.post(
        "/item/new",
        data={
            "name": "Wine glass",
            "category_id": str(glassware),
            "quantity": "4",
            "notes": "Stemless",
            "location": "Top shelf",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    items = db.get_items_in_category(glassware)
    assert [row["name"] for row in items] == ["Wine glass"]
    saved = items[0]
    assert saved["quantity"] == 4
    assert saved["notes"] == "Stemless"
    assert db.get_location(saved["location_id"])["name"] == "Top shelf"
    assert "Wine glass" in _html(client.get(f"/category/{glassware}"))


def test_add_item_creating_a_category_inline_creates_both(client):
    # Covers R10: the inline-create path is the only category authoring in v1.
    db = _db()
    kitchen, _ = _kitchen_tree()

    client.post(
        "/item/new",
        data={
            "name": "Stock pot",
            "category_id": str(kitchen),
            "new_category": "Cookware",
            "quantity": "1",
        },
        follow_redirects=True,
    )

    cookware = [
        row for row in db.get_subcategories(kitchen) if row["name"] == "Cookware"
    ]
    assert len(cookware) == 1
    items = db.get_items_in_category(cookware[0]["id"])
    assert [row["name"] for row in items] == ["Stock pot"]


def test_add_item_creating_a_top_level_category_inline(client):
    # No parent chosen plus an inline name means a new top-level collection.
    db = _db()

    client.post(
        "/item/new",
        data={"name": "Tent", "category_id": "", "new_category": "Camping"},
        follow_redirects=True,
    )

    camping = [row for row in db.get_top_level_categories() if row["name"] == "Camping"]
    assert len(camping) == 1
    assert [row["name"] for row in db.get_items_in_category(camping[0]["id"])] == ["Tent"]


def test_add_book_attached_directly_to_library_saves_at_top_level(client):
    # Covers R3 / AE4: no sub-type chosen, so the book lives on Library itself.
    db = _db()
    library = db.create_category("Library")
    db.create_category("Records", parent_id=library)

    client.post(
        "/item/new",
        data={"name": "Dune", "category_id": str(library), "quantity": "1"},
        follow_redirects=True,
    )

    assert [row["name"] for row in db.get_items_in_category(library)] == ["Dune"]


def test_add_item_defaults_quantity_and_notes_when_left_blank(client):
    db = _db()
    kitchen, _ = _kitchen_tree()

    client.post(
        "/item/new",
        data={"name": "Whisk", "category_id": str(kitchen), "quantity": "", "notes": ""},
        follow_redirects=True,
    )

    saved = db.get_items_in_category(kitchen)[0]
    assert saved["quantity"] == 0
    assert saved["notes"] == ""
    assert saved["location_id"] is None


# --- Add validation --------------------------------------------------------

def test_add_without_a_name_returns_a_validation_error_not_a_crash(client):
    db = _db()
    kitchen, _ = _kitchen_tree()

    resp = client.post(
        "/item/new", data={"name": "  ", "category_id": str(kitchen), "quantity": "2"}
    )
    body = _html(resp)
    assert resp.status_code == 400
    assert "name" in body.lower()
    assert db.get_all_items() == []
    # The form comes back so the owner can fix it rather than retype everything.
    assert "<form" in body


def test_add_with_a_non_numeric_quantity_returns_a_validation_error(client):
    db = _db()
    kitchen, _ = _kitchen_tree()

    resp = client.post(
        "/item/new",
        data={"name": "Mug", "category_id": str(kitchen), "quantity": "lots"},
    )
    assert resp.status_code == 400
    assert "quantity" in _html(resp).lower()
    assert db.get_all_items() == []


def test_add_with_a_negative_quantity_returns_a_validation_error(client):
    db = _db()
    kitchen, _ = _kitchen_tree()

    resp = client.post(
        "/item/new",
        data={"name": "Mug", "category_id": str(kitchen), "quantity": "-3"},
    )
    assert resp.status_code == 400
    assert db.get_all_items() == []


def test_add_with_an_unknown_category_is_rejected_not_a_500(client):
    # PRAGMA foreign_keys = ON would otherwise raise IntegrityError -> 500.
    db = _db()

    resp = client.post(
        "/item/new", data={"name": "Mug", "category_id": "999", "quantity": "1"}
    )
    assert resp.status_code == 400
    assert db.get_all_items() == []


def test_add_with_a_duplicate_inline_category_name_shows_the_error(client):
    # create_category raises ValueError for a duplicate under the same parent.
    db = _db()
    kitchen, _ = _kitchen_tree()

    resp = client.post(
        "/item/new",
        data={
            "name": "Tumbler",
            "category_id": str(kitchen),
            "new_category": "Glassware",
        },
    )
    assert resp.status_code == 400
    assert "already exists" in _html(resp)
    assert db.get_all_items() == []
    assert len(db.get_subcategories(kitchen)) == 1


# --- Editing (R11 / AE3) ---------------------------------------------------

def test_edit_form_prefills_every_field(client):
    db = _db()
    _, glassware = _kitchen_tree()
    shelf = db.get_or_create_location("Top shelf")
    item = db.create_item(
        "Pint glass",
        category_id=glassware,
        location_id=shelf,
        quantity=6,
        notes="Two are chipped",
    )

    resp = client.get(f"/item/{item}/edit")
    body = _html(resp)
    assert resp.status_code == 200
    assert 'value="Pint glass"' in body
    assert 'value="6"' in body
    assert 'value="Top shelf"' in body
    assert "Two are chipped" in body
    assert f'value="{glassware}" selected' in body


def test_editing_the_quantity_from_six_to_five_persists_five(client):
    # Covers R11 / AE3, built on the literal pint-glass fixture.
    db = _db()
    item = _pint_glasses_with_quantity_six()
    before = db.get_item(item)

    resp = client.post(
        f"/item/{item}/edit",
        data={
            "name": before["name"],
            "category_id": str(before["category_id"]),
            "quantity": "5",
            "notes": before["notes"],
            "location": "",
        },
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert db.get_item(item)["quantity"] == 5
    assert "5" in _html(client.get(f"/item/{item}"))


def test_editing_can_change_name_notes_location_and_category(client):
    # Covers R11 beyond quantity.
    db = _db()
    kitchen, glassware = _kitchen_tree()
    item = db.create_item("Pint glass", category_id=glassware, quantity=6)

    client.post(
        f"/item/{item}/edit",
        data={
            "name": "Pint glasses",
            "category_id": str(kitchen),
            "quantity": "6",
            "notes": "Moved out of Glassware",
            "location": "Sideboard",
        },
        follow_redirects=True,
    )

    row = db.get_item(item)
    assert row["name"] == "Pint glasses"
    assert row["category_id"] == kitchen
    assert row["notes"] == "Moved out of Glassware"
    assert db.get_location(row["location_id"])["name"] == "Sideboard"


def test_editing_to_a_blank_name_returns_a_validation_error(client):
    db = _db()
    item = _pint_glasses_with_quantity_six()

    resp = client.post(
        f"/item/{item}/edit",
        data={"name": "", "category_id": "", "quantity": "5"},
    )
    assert resp.status_code == 400
    assert db.get_item(item)["name"] == "Pint glass"
    assert db.get_item(item)["quantity"] == 6


def test_editing_with_a_bad_quantity_leaves_the_item_untouched(client):
    db = _db()
    item = _pint_glasses_with_quantity_six()
    before = db.get_item(item)

    resp = client.post(
        f"/item/{item}/edit",
        data={
            "name": before["name"],
            "category_id": str(before["category_id"]),
            "quantity": "five",
        },
    )
    assert resp.status_code == 400
    assert db.get_item(item)["quantity"] == 6


def test_edit_form_for_an_unknown_item_returns_404(client):
    assert client.get("/item/999/edit").status_code == 404
    assert client.post("/item/999/edit", data={"name": "x"}).status_code == 404


# --- Deleting (R12) --------------------------------------------------------

def test_deleting_removes_the_item_from_browse_and_search(client):
    # Covers R12.
    db = _db()
    _, glassware = _kitchen_tree()
    item = db.create_item("Pint glass", category_id=glassware, quantity=6, notes="chipped")

    resp = client.post(f"/item/{item}/delete", follow_redirects=True)
    assert resp.status_code == 200

    assert db.get_item(item) is None
    assert client.get(f"/item/{item}").status_code == 404
    assert "Pint glass" not in _html(client.get(f"/category/{glassware}"))
    assert "Pint glass" not in _html(client.get("/search?q=Pint"))
    assert "Pint glass" not in _html(client.get("/search?q=chipped"))


def test_deleting_returns_to_the_items_category(client):
    db = _db()
    _, glassware = _kitchen_tree()
    item = db.create_item("Pint glass", category_id=glassware)

    resp = client.post(f"/item/{item}/delete")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/category/{glassware}")


def test_deleting_an_unknown_item_returns_404(client):
    assert client.post("/item/999/delete").status_code == 404


def test_get_on_the_delete_route_is_not_allowed(client):
    # Deletion is a POST (KTD1: a plain form post, guarded by confirm()).
    db = _db()
    _, glassware = _kitchen_tree()
    item = db.create_item("Pint glass", category_id=glassware)

    assert client.get(f"/item/{item}/delete").status_code == 405
    assert db.get_item(item) is not None


# --- Flow F3 end to end ----------------------------------------------------

def test_add_then_edit_quantity_then_delete_round_trip(client):
    # Covers F3 plus R11/R12: the whole loop through the web pages.
    db = _db()
    kitchen, _ = _kitchen_tree()

    assert "/item/new" in _html(client.get("/"))
    client.post(
        "/item/new",
        data={
            "name": "Pint glass",
            "category_id": str(kitchen),
            "new_category": "Barware",
            "quantity": "6",
            "location": "Top shelf",
        },
        follow_redirects=True,
    )
    barware = [r for r in db.get_subcategories(kitchen) if r["name"] == "Barware"][0]["id"]
    item = db.get_items_in_category(barware)[0]["id"]

    assert f"/item/{item}/edit" in _html(client.get(f"/item/{item}"))
    client.post(
        f"/item/{item}/edit",
        data={
            "name": "Pint glass",
            "category_id": str(barware),
            "quantity": "5",
            "location": "Top shelf",
        },
        follow_redirects=True,
    )
    assert db.get_item(item)["quantity"] == 5

    client.post(f"/item/{item}/delete", follow_redirects=True)
    assert db.get_item(item) is None


def test_item_form_is_mobile_ready(client):
    # Covers R9.
    body = _html(client.get("/item/new"))
    assert 'name="viewport"' in body
    assert "item-form" in body


def test_json_api_is_untouched_by_the_form_routes(client):
    # Guards KTD5.
    resp = client.post("/inventory", json={"name": "Mug", "category_id": None})
    assert resp.status_code == 201
    assert client.get("/inventory").get_json()[0]["name"] == "Mug"
