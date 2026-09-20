"""Search tests (U4).

Covers R8 (one search finds items across every collection, matching name and
notes), AE2 (a term that appears only in the notes still finds the record),
R9 (mobile-ready markup) and flow F2 (the bookstore duplicate check).
"""


def _db():
    """The data layer, already pointed at the throwaway DB by the client fixture."""
    import db

    return db


def _html(response):
    return response.get_data(as_text=True)


def _library_with_kind_of_blue():
    """The literal AE2 fixture: a Library record with the artist only in notes."""
    db = _db()
    library = db.create_category("Library")
    records = db.create_category("Records", parent_id=library)
    item = db.create_item(
        "Kind of Blue",
        category_id=records,
        quantity=1,
        notes="Miles Davis, 1959",
    )
    return library, records, item


# --- Matching on name (R8) -------------------------------------------------

def test_search_matches_a_substring_of_the_item_name(client):
    # Covers R8.
    _, _, item = _library_with_kind_of_blue()

    resp = client.get("/search?q=Blue")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Kind of Blue" in body
    assert f'href="/item/{item}"' in body


def test_search_spans_every_collection(client):
    # Covers R8: one query reaches items in unrelated top-level collections.
    db = _db()
    kitchen = db.create_category("Kitchen")
    library = db.create_category("Library")
    glass = db.create_item("Blue tumbler", category_id=kitchen)
    book = db.create_item("Blue Highways", category_id=library)

    body = _html(client.get("/search?q=blue"))
    assert f'href="/item/{glass}"' in body
    assert f'href="/item/{book}"' in body


# --- Matching on notes (R8 / AE2) ------------------------------------------

def test_search_matches_a_term_found_only_in_notes(client):
    # Covers R8 / AE2: "Miles" appears nowhere in the name.
    _, _, item = _library_with_kind_of_blue()

    resp = client.get("/search?q=Miles")
    body = _html(resp)
    assert resp.status_code == 200
    assert "Kind of Blue" in body
    assert f'href="/item/{item}"' in body


def test_search_is_case_insensitive(client):
    # Covers R8.
    _library_with_kind_of_blue()

    assert "Kind of Blue" in _html(client.get("/search?q=miles"))
    assert "Kind of Blue" in _html(client.get("/search?q=MILES"))
    assert "Kind of Blue" in _html(client.get("/search?q=kind OF blue"))


# --- Result presentation ---------------------------------------------------

def test_results_show_which_collection_holds_the_item(client):
    # Flow F2 needs the answer "yes, it is already in the Library".
    _library_with_kind_of_blue()

    body = _html(client.get("/search?q=Miles"))
    assert "Library" in body
    assert "Records" in body


def test_results_use_the_shared_entry_list_markup(client):
    _library_with_kind_of_blue()

    assert 'class="entry-list"' in _html(client.get("/search?q=Miles"))


def test_search_page_echoes_the_query_in_the_header_box(client):
    # The shared header form re-displays q; search must not break that.
    _library_with_kind_of_blue()

    body = _html(client.get("/search?q=Miles"))
    assert 'value="Miles"' in body


# --- Empty and no-match states ---------------------------------------------

def test_no_matches_renders_a_clear_no_results_state(client):
    _library_with_kind_of_blue()

    resp = client.get("/search?q=Coltrane")
    body = _html(resp)
    assert resp.status_code == 200
    assert 'id="no-results"' in body
    assert "Kind of Blue" not in body


def test_missing_q_renders_a_prompt_not_an_error(client):
    resp = client.get("/search")
    assert resp.status_code == 200
    assert 'id="search-prompt"' in _html(resp)


def test_blank_and_whitespace_q_render_the_prompt(client):
    _library_with_kind_of_blue()

    for url in ("/search?q=", "/search?q=%20%20"):
        resp = client.get(url)
        assert resp.status_code == 200, url
        body = _html(resp)
        assert 'id="search-prompt"' in body, url
        assert "Kind of Blue" not in body, url


# --- SQL LIKE wildcards ----------------------------------------------------

def test_percent_in_a_query_is_matched_literally(client):
    # "%" is a LIKE wildcard; a searcher typing it means the character.
    db = _db()
    pantry = db.create_category("Pantry")
    juice = db.create_item("Juice 100% pure", category_id=pantry)
    db.create_item("100 paper clips", category_id=pantry)

    body = _html(client.get("/search?q=100%25"))
    assert f'href="/item/{juice}"' in body
    assert "paper clips" not in body


def test_underscore_in_a_query_is_matched_literally(client):
    # "_" is a single-character LIKE wildcard; treat it as a literal.
    db = _db()
    lab = db.create_category("Lab")
    literal = db.create_item("sample a_b", category_id=lab)
    db.create_item("sample axb", category_id=lab)

    body = _html(client.get("/search?q=a_b"))
    assert f'href="/item/{literal}"' in body
    assert "axb" not in body


# --- Flow F2 ---------------------------------------------------------------

def test_duplicate_check_flow_from_a_phone(client):
    # Covers F2 + R9: search a title from the header box on a small screen and
    # see whether the Library already holds it.
    _library_with_kind_of_blue()

    resp = client.get("/search?q=Kind of Blue")
    body = _html(resp)
    assert 'name="viewport"' in body
    assert 'action="/search"' in body
    assert "Kind of Blue" in body
    assert "Library" in body

    assert 'id="no-results"' in _html(client.get("/search?q=Bitches Brew"))
