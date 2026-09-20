# PRIMS
A "Personal Resource and Information Management System" for organizing my life.

## Overview
PRIMS (Personal Resource and Information Management System) is designed to help organize personal inventory, such as kitchen supplies, clothes, and electronics, with specific locations for easy retrieval.

## Features Implemented
- Web interface for browsing, searching, and managing inventory
  - Home screen of top-level collections, each with a subtree-wide item count
  - Category pages showing sub-categories and directly-attached items together
  - One search box matching item names *and* notes across every collection
  - Add, edit, and delete items, creating a category inline when needed
  - Mobile-friendly: it works at phone width, for checking inventory while out
- Categories nest to any depth, and an item can attach at any level
- SQLite database behind a single data-access layer (`src/db.py`)
- JSON API for inventory items, categories, and locations
- File upload/download/delete endpoints
- Seed script with realistic sample data
- 91 automated tests (`pytest`), plus the original curl smoke script

## Checklist
- [x] Set up project structure
- [x] Implement basic CRUD operations
- [x] Create test script for CRUD operations
- [x] Add search functionality
- [x] Develop a web interface
- [ ] Implement user authentication
- [ ] Deploy the application

Every item records the same three fields — name, quantity, and freeform notes.
A book's author or a record's artist lives in the notes, where search finds it.

## Getting Started
To run the application locally, follow these steps:
1. Clone the repository: `git clone https://github.com/marcusjoshm/PRIMS.git`
2. Navigate to the project directory: `cd PRIMS`
3. Create a virtual environment: `python3 -m venv venv`
4. Activate the virtual environment: `source venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`
6. *(Optional)* Load sample data: `python src/seed.py`
7. Run the application: `python src/app.py`, then open http://127.0.0.1:5000

> **`src/seed.py` is destructive.** It drops every table and rebuilds the
> database from the sample inventory. It asks for confirmation first if the
> database already holds items; pass `--force` to skip the prompt. Point it at
> a different file with `PRIMS_DB=/tmp/demo.db python src/seed.py`.

## Running the tests
```bash
python -m pytest tests/          # 91 unit and page tests
bash tests/test_crud_operations.sh   # curl smoke test, needs the app running
```

## Web pages
| Path | Purpose |
| --- | --- |
| `/` | Top-level collections, with an entry point to add an item |
| `/category/<id>` | A category's sub-categories and its own items |
| `/item/<id>` | One item's name, quantity, location, category, and notes |
| `/search?q=` | Items matching a term in their name or notes |
| `/item/new`, `/item/<id>/edit`, `/item/<id>/delete` | Add, edit, remove |

## License
This project is licensed under the MIT License.

## File Management
PRIMS includes file management capabilities, allowing users to upload, list, download, and delete files. This feature is useful for managing important documents and configurations.

### Endpoints
- **Upload File**: POST `/upload` - Upload a file to the server.
- **List Files**: GET `/files` - Retrieve a list of all uploaded files.
- **Download File**: GET `/files/<filename>` - Download a specific file.
- **Delete File**: DELETE `/files/<filename>` - Delete a specific file from the server.

These endpoints support various file types, including `txt`, `pdf`, `png`, `jpg`, `jpeg`, and `gif`. Ensure that the files you upload meet the allowed criteria.
