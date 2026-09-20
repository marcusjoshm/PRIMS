from flask import (
    Flask, request, jsonify, send_from_directory, render_template,
    redirect, url_for, flash, abort,
)
import os
from werkzeug.utils import secure_filename

import db

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('PRIMS_SECRET_KEY', 'dev-secret-change-me')

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Allowed extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# Web pages
# ---------------------------------------------------------------------------

@app.route('/')
def home():
    """Top-level collections as tiles, each with a subtree-wide item count (R6)."""
    collections = [
        {'row': row, 'count': db.category_item_count(row['id'])}
        for row in db.get_top_level_categories()
    ]
    return render_template('home.html', collections=collections)


@app.route('/category/<int:category_id>')
def category_page(category_id):
    """A category's sub-categories and its directly-attached items (R7/AE1)."""
    category = db.get_category(category_id)
    if category is None:
        abort(404)
    subcategories = [
        {'row': row, 'count': db.category_item_count(row['id'])}
        for row in db.get_subcategories(category_id)
    ]
    return render_template(
        'category.html',
        category=category,
        ancestors=db.get_ancestors(category_id),
        subcategories=subcategories,
        items=db.get_items_in_category(category_id),
    )


@app.route('/item/<int:item_id>')
def item_page(item_id):
    """One item: name, quantity, notes and location."""
    item = db.get_item(item_id)
    if item is None:
        abort(404)
    category = db.get_category(item['category_id']) if item['category_id'] else None
    ancestors = db.get_ancestors(category['id']) if category else []
    return render_template(
        'item.html',
        item=item,
        category=category,
        ancestors=ancestors,
        location=db.get_location(item['location_id']),
    )


# ---------------------------------------------------------------------------
# JSON API (existing endpoints, now backed by the shared data layer in db.py)
# ---------------------------------------------------------------------------

@app.route('/inventory', methods=['POST'])
def create_inventory_item():
    data = request.get_json() or {}
    try:
        item_id = db.create_item(
            name=data.get('name'),
            category_id=data.get('category_id'),
            location_id=data.get('location_id'),
            quantity=data.get('quantity', 0),
            notes=data.get('notes', ''),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Inventory item created successfully', 'id': item_id}), 201


@app.route('/inventory', methods=['GET'])
def get_inventory_items():
    return jsonify([dict(row) for row in db.get_all_items()])


@app.route('/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    data = request.get_json() or {}
    existing = db.get_item(item_id)
    if existing is None:
        return jsonify({'error': 'Inventory item not found'}), 404
    try:
        db.update_item(
            item_id,
            name=data.get('name', existing['name']),
            category_id=data.get('category_id', existing['category_id']),
            location_id=data.get('location_id', existing['location_id']),
            quantity=data.get('quantity', existing['quantity']),
            notes=data.get('notes', existing['notes']),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Inventory item updated successfully'})


@app.route('/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    db.delete_item(item_id)
    return jsonify({'message': 'Inventory item deleted successfully'})


@app.route('/categories', methods=['POST'])
def create_category():
    data = request.get_json() or {}
    try:
        category_id = db.create_category(data.get('name'), data.get('parent_id'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Category created successfully', 'id': category_id}), 201


@app.route('/categories', methods=['GET'])
def get_categories():
    return jsonify([dict(row) for row in db.get_all_categories()])


@app.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    data = request.get_json() or {}
    try:
        db.update_category(category_id, data.get('name'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Category updated successfully'})


@app.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    try:
        db.delete_category(category_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Category deleted successfully'})


@app.route('/locations', methods=['POST'])
def create_location():
    data = request.get_json() or {}
    location_id = db.get_or_create_location(data.get('name'))
    if location_id is None:
        return jsonify({'error': 'Location name is required'}), 400
    return jsonify({'message': 'Location created successfully', 'id': location_id}), 201


@app.route('/locations', methods=['GET'])
def get_locations():
    return jsonify([dict(row) for row in db.get_locations()])


@app.route('/locations/<int:location_id>', methods=['PUT'])
def update_location(location_id):
    data = request.get_json() or {}
    try:
        db.update_location(location_id, data.get('name'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'message': 'Location updated successfully'})


@app.route('/locations/<int:location_id>', methods=['DELETE'])
def delete_location(location_id):
    db.delete_location(location_id)
    return jsonify({'message': 'Location deleted successfully'})


# ---------------------------------------------------------------------------
# File management (unchanged)
# ---------------------------------------------------------------------------

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'message': 'File uploaded successfully', 'filename': filename}), 201
    else:
        return jsonify({'error': 'File type not allowed'}), 400


@app.route('/files', methods=['GET'])
def list_files():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return jsonify(files)


@app.route('/files/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/files/<filename>', methods=['DELETE'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'message': 'File deleted successfully'})
    else:
        return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    db.init_db()
    app.run(debug=True)
