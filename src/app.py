from flask import Flask, request, jsonify, send_from_directory, render_template
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Allowed extensions
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    # Connect to the SQLite database
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    # Create a table for inventory items
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            location_id INTEGER,
            quantity INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(id),
            FOREIGN KEY (location_id) REFERENCES locations(id)
        )
    ''')
    # Create a table for categories
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    # Create a table for locations
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def home():
    return render_template('home.html')

# Create a new inventory item
@app.route('/inventory', methods=['POST'])
def create_inventory_item():
    data = request.get_json()
    name = data.get('name')
    category_id = data.get('category_id')
    location_id = data.get('location_id')
    quantity = data.get('quantity', 0)
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO inventory (name, category_id, location_id, quantity) VALUES (?, ?, ?, ?)',
                   (name, category_id, location_id, quantity))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Inventory item created successfully'}), 201

# Read all inventory items
@app.route('/inventory', methods=['GET'])
def get_inventory_items():
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM inventory')
    items = cursor.fetchall()
    conn.close()
    return jsonify(items)

# Update an inventory item
@app.route('/inventory/<int:item_id>', methods=['PUT'])
def update_inventory_item(item_id):
    data = request.get_json()
    name = data.get('name')
    category_id = data.get('category_id')
    location_id = data.get('location_id')
    quantity = data.get('quantity')
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE inventory
        SET name = ?, category_id = ?, location_id = ?, quantity = ?
        WHERE id = ?
    ''', (name, category_id, location_id, quantity, item_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Inventory item updated successfully'})

# Delete an inventory item
@app.route('/inventory/<int:item_id>', methods=['DELETE'])
def delete_inventory_item(item_id):
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM inventory WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Inventory item deleted successfully'})

# Create a new category
@app.route('/categories', methods=['POST'])
def create_category():
    data = request.get_json()
    name = data.get('name')
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO categories (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Category created successfully'}), 201

# Read all categories
@app.route('/categories', methods=['GET'])
def get_categories():
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM categories')
    categories = cursor.fetchall()
    conn.close()
    return jsonify(categories)

# Update a category
@app.route('/categories/<int:category_id>', methods=['PUT'])
def update_category(category_id):
    data = request.get_json()
    name = data.get('name')
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE categories SET name = ? WHERE id = ?', (name, category_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Category updated successfully'})

# Delete a category
@app.route('/categories/<int:category_id>', methods=['DELETE'])
def delete_category(category_id):
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM categories WHERE id = ?', (category_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Category deleted successfully'})

# Create a new location
@app.route('/locations', methods=['POST'])
def create_location():
    data = request.get_json()
    name = data.get('name')
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO locations (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Location created successfully'}), 201

# Read all locations
@app.route('/locations', methods=['GET'])
def get_locations():
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM locations')
    locations = cursor.fetchall()
    conn.close()
    return jsonify(locations)

# Update a location
@app.route('/locations/<int:location_id>', methods=['PUT'])
def update_location(location_id):
    data = request.get_json()
    name = data.get('name')
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE locations SET name = ? WHERE id = ?', (name, location_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Location updated successfully'})

# Delete a location
@app.route('/locations/<int:location_id>', methods=['DELETE'])
def delete_location(location_id):
    conn = sqlite3.connect('prims.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM locations WHERE id = ?', (location_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Location deleted successfully'})

# File upload endpoint
@app.route('/upload', methods=['POST'])
def upload_file():
    # Check if the post request has the file part
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    # If the user does not select a file, the browser submits an empty file without a filename
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        return jsonify({'message': 'File uploaded successfully', 'filename': filename}), 201
    else:
        return jsonify({'error': 'File type not allowed'}), 400

# List uploaded files
@app.route('/files', methods=['GET'])
def list_files():
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return jsonify(files)

# Download a file
@app.route('/files/<filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Delete a file
@app.route('/files/<filename>', methods=['DELETE'])
def delete_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({'message': 'File deleted successfully'})
    else:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    init_db()
    app.run(debug=True) 