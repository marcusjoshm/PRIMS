"""Browse-page tests (U3).

Covers R6 (home tiles + reachable search), R7/AE1 (a category shows its
sub-categories and its directly-attached items together), R9 (mobile-ready
markup), and flow F1 (browse home -> category -> item to read a quantity).
"""


def _db():
    """The data layer, already pointed at the throwaway DB by the client fixture."""
    import db

    return db


def _html(response):
    return response.get_data(as_text=True)


# --- Home (R6) -------------------------------------------------------------

def test_home_lists_top_level_collections_as_tiles(client):
    # Covers R6.
    db = _db()
    kitchen = db.create_category("Kitchen")
    db.create_category("Library")
    glass = db.create_category("Glassware", parent_id=kitchen)
    db.create_item("Pint glass", category_id=glass, quantity=6)

    resp = client.get("/")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Kitchen" in body
    assert "Library" in body
    # Tiles link into the collection, and carry a subtree-wide item count.
    assert f'href="/category/{kitchen}"' in body
    assert 'class="tiles"' in body
    assert "1 item" in body


def test_home_exposes_search(client):
    # Covers R6: search is reachable from the home screen.
    body = _html(client.get("/"))
    assert 'action="/search"' in body


def test_home_with_no_collections_shows_empty_state(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "empty-state" in _html(resp)


# --- Category (R7 / AE1) ---------------------------------------------------

def test_category_shows_subcategories_and_loose_items_together(client):
    # Covers R7 / AE1: Kitchen holds Glassware + Appliances and a loose item.
    db = _db()
    kitchen = db.create_category("Kitchen")
    db.create_category("Glassware", parent_id=kitchen)
    db.create_category("Appliances", parent_id=kitchen)
    sponges = db.create_item("spare sponges", category_id=kitchen, quantity=4)

    resp = client.get(f"/category/{kitchen}")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Glassware" in body
    assert "Appliances" in body
    assert "spare sponges" in body
    assert f'href="/item/{sponges}"' in body


def test_category_with_only_subcategories_has_no_items_section(client):
    db = _db()
    kitchen = db.create_category("Kitchen")
    db.create_category("Glassware", parent_id=kitchen)

    body = _html(client.get(f"/category/{kitchen}"))
    assert "Glassware" in body
    assert 'id="subcategories"' in body
    assert 'id="items"' not in body


def test_category_with_only_items_has_no_subcategory_section(client):
    db = _db()
    kitchen = db.create_category("Kitchen")
    db.create_item("spare sponges", category_id=kitchen, quantity=4)

    body = _html(client.get(f"/category/{kitchen}"))
    assert "spare sponges" in body
    assert 'id="items"' in body
    assert 'id="subcategories"' not in body


def test_empty_category_renders_empty_state(client):
    db = _db()
    kitchen = db.create_category("Kitchen")

    resp = client.get(f"/category/{kitchen}")
    assert resp.status_code == 200
    assert "empty-state" in _html(resp)


def test_unknown_category_returns_404(client):
    assert client.get("/category/999").status_code == 404


# --- Item detail -----------------------------------------------------------

def test_item_detail_shows_name_quantity_notes_and_location(client):
    db = _db()
    kitchen = db.create_category("Kitchen")
    glass = db.create_category("Glassware", parent_id=kitchen)
    shelf = db.get_or_create_location("Top shelf")
    item = db.create_item(
        "Pint glass",
        category_id=glass,
        location_id=shelf,
        quantity=6,
        notes="Two are chipped",
    )

    resp = client.get(f"/item/{item}")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Pint glass" in body
    assert "6" in body
    assert "Two are chipped" in body
    assert "Top shelf" in body


def test_item_detail_without_location_or_notes_still_renders(client):
    db = _db()
    kitchen = db.create_category("Kitchen")
    item = db.create_item("spare sponges", category_id=kitchen, quantity=4)

    resp = client.get(f"/item/{item}")
    body = _html(resp)
    assert resp.status_code == 200
    assert "spare sponges" in body
    assert "Kitchen" in body


def test_item_detail_renders_edit_and_delete_affordances(client):
    # U5 wires these routes; the page must render their links without 500ing.
    db = _db()
    kitchen = db.create_category("Kitchen")
    item = db.create_item("spare sponges", category_id=kitchen)

    body = _html(client.get(f"/item/{item}"))
    assert f'/item/{item}/edit' in body
    assert f'/item/{item}/delete' in body


def test_delete_confirm_survives_an_apostrophe_in_the_name(client):
    # Jinja autoescapes for HTML, not JS: interpolating a name into the inline
    # confirm() string turns "Kid's plates" into &#39;, which the HTML parser
    # decodes back to a bare quote and breaks the JS literal.
    db = _db()
    kitchen = db.create_category("Kitchen")
    item = db.create_item("Kid's plates", category_id=kitchen)

    body = _html(client.get(f"/item/{item}"))
    assert "&#39;" not in body.split('onsubmit="')[1].split('"')[0]


def test_unknown_item_returns_404(client):
    assert client.get("/item/999").status_code == 404


# --- Flow F1 ---------------------------------------------------------------

def test_browse_from_home_to_item_reads_quantity(client):
    # Covers F1: home -> Kitchen -> Glassware -> item, reading the quantity.
    db = _db()
    kitchen = db.create_category("Kitchen")
    glass = db.create_category("Glassware", parent_id=kitchen)
    item = db.create_item("Pint glass", category_id=glass, quantity=6)

    assert f'href="/category/{kitchen}"' in _html(client.get("/"))
    assert f'href="/category/{glass}"' in _html(client.get(f"/category/{kitchen}"))
    assert f'href="/item/{item}"' in _html(client.get(f"/category/{glass}"))
    assert "6" in _html(client.get(f"/item/{item}"))


def test_pages_carry_mobile_viewport(client):
    # Covers R9.
    assert 'name="viewport"' in _html(client.get("/"))


def test_json_api_still_works(client):
    # Guards KTD5: the page routes must not disturb the existing JSON API.
    resp = client.get("/inventory")
    assert resp.status_code == 200
    assert resp.get_json() == []
