"""JSON API validation tests.

The HTML forms guard their own inputs, but the JSON endpoints hand values
straight to the data layer. With `PRAGMA foreign_keys = ON`, a bad id or a
still-referenced row raises sqlite3.IntegrityError, which escapes as a 500
unless the data layer turns it into a ValueError the route maps to 400.
"""


def _db():
    """The data layer, already pointed at the throwaway DB by the client fixture."""
    import db

    return db


def test_create_item_with_unknown_category_is_a_400(client):
    response = client.post('/inventory', json={'name': 'Ghost', 'category_id': 999})
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_create_item_with_unknown_location_is_a_400(client):
    db = _db()
    kitchen = db.create_category('Kitchen')
    response = client.post(
        '/inventory', json={'name': 'Ghost', 'category_id': kitchen, 'location_id': 999}
    )
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_update_item_with_unknown_category_is_a_400(client):
    db = _db()
    kitchen = db.create_category('Kitchen')
    item = db.create_item('Pint glass', category_id=kitchen)
    response = client.put(f'/inventory/{item}', json={'category_id': 999})
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_rename_category_onto_a_sibling_is_a_400(client):
    db = _db()
    kitchen = db.create_category('Kitchen')
    db.create_category('Glassware', parent_id=kitchen)
    mugs = db.create_category('Mugs', parent_id=kitchen)
    response = client.put(f'/categories/{mugs}', json={'name': 'Glassware'})
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_rename_category_onto_another_top_level_name_is_a_400(client):
    db = _db()
    db.create_category('Kitchen')
    library = db.create_category('Library')
    response = client.put(f'/categories/{library}', json={'name': 'Kitchen'})
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_create_category_under_an_unknown_parent_is_a_400(client):
    response = client.post('/categories', json={'name': 'Ghost', 'parent_id': 9999})
    assert response.status_code == 400
    assert '9999' in response.get_json()['error']


def test_delete_location_still_in_use_is_a_400(client):
    db = _db()
    kitchen = db.create_category('Kitchen')
    cupboard = db.get_or_create_location('Cupboard')
    db.create_item('Pint glass', category_id=kitchen, location_id=cupboard)
    response = client.delete(f'/locations/{cupboard}')
    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_delete_unused_location_still_succeeds(client):
    db = _db()
    cupboard = db.get_or_create_location('Cupboard')
    response = client.delete(f'/locations/{cupboard}')
    assert response.status_code == 200
    assert db.get_location(cupboard) is None
