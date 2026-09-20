"""Seed PRIMS with a realistic nested inventory (U6, R5).

Populates three collections -- Kitchen (with nested Glassware, Appliances and
Dishes, plus a loose item attached directly to Kitchen), Library (books) and
Records (albums). Per KD1 every item carries the same three fields, so a book's
author and a record's artist/year live in the freeform ``notes`` where search
finds them; per KD2 categories nest as deep as the content warrants and items
may hang off any level.

Run it from the repository root::

    python src/seed.py                 # prompts before wiping a populated DB
    python src/seed.py --force         # never prompts (scripts, CI, Makefiles)
    PRIMS_DB=/tmp/demo.db python src/seed.py

This is destructive: per KTD4 there is no migration framework, so seeding drops
and recreates the schema in whatever database ``db.DB_PATH`` points at. Seeding
an empty or absent database happens silently; seeding over existing items asks
for confirmation first unless ``--force``/``--yes`` is given. A database that
cannot be read at all is refused outright rather than guessed at as empty.

Every write goes through the ``db`` data layer -- this script hand-writes no SQL.
"""
import argparse
import sqlite3
import sys

import db


# --- Seed content ----------------------------------------------------------
# A category is (name, items, sub-categories); an item is
# (name, quantity, notes, location).

INVENTORY = [
    (
        "Kitchen",
        [
            # Attached directly to Kitchen, alongside its sub-categories (AE1).
            ("Spare sponges", 6, "Under-sink pack, restock in spring", "Under-sink cupboard"),
            ("Kitchen shears", 1, "Take-apart blades, dishwasher safe", "Utensil drawer"),
        ],
        [
            (
                "Glassware",
                [
                    ("Pint glass", 6, "Two are chipped on the rim", "Top shelf"),
                    ("Tumbler", 10, "Everyday water glasses", "Top shelf"),
                    ("Mason jar", 8, "Wide mouth, 16 oz", "Pantry shelf"),
                ],
                [
                    (
                        "Stemware",
                        [
                            ("Wine glass", 8, "Universal bowl, set of eight", "Top shelf"),
                            ("Champagne flute", 4, "Wedding gift", "Top shelf"),
                            ("Coupe glass", 4, "Thrifted, mismatched", "Top shelf"),
                        ],
                        [],
                    ),
                ],
            ),
            (
                "Appliances",
                [
                    ("Blender", 1, "Glass jar, gasket replaced 2024", "Counter"),
                    ("Stand mixer", 1, "Comes with dough hook and whisk", "Corner shelf"),
                    ("Toaster", 1, "Four slot, crumb tray sticks", "Counter"),
                    ("Electric kettle", 1, "Gooseneck, for pour-over", "Counter"),
                    ("Food processor", 1, "Missing the shredding disc", "Lower cupboard"),
                ],
                [],
            ),
            (
                "Dishes",
                [
                    ("Dinner plate", 8, "White stoneware", "Plate cupboard"),
                    ("Side plate", 8, "Matches the dinner plates", "Plate cupboard"),
                    ("Cereal bowl", 6, "Two have hairline cracks", "Plate cupboard"),
                    ("Mug", 10, "Nothing matches anything", "Mug shelf"),
                    ("Serving platter", 2, "Oval, only used at holidays", "Lower cupboard"),
                ],
                [],
            ),
        ],
    ),
    (
        "Library",
        [
            ("Atlas of the World", 1, "Times Books, 2014", "Bottom shelf"),
        ],
        [
            (
                "Fiction",
                [
                    ("Beloved", 1, "Toni Morrison, 1987", "Bookshelf"),
                    ("Moby-Dick", 1, "Herman Melville, 1851", "Bookshelf"),
                    ("Never Let Me Go", 1, "Kazuo Ishiguro, 2005", "Bookshelf"),
                    ("Their Eyes Were Watching God", 1, "Zora Neale Hurston, 1937", "Bookshelf"),
                ],
                [
                    (
                        "Science Fiction",
                        [
                            ("Dune", 1, "Frank Herbert, 1965", "Bookshelf"),
                            ("The Left Hand of Darkness", 2, "Ursula K. Le Guin, 1969", "Bookshelf"),
                            ("The Dispossessed", 1, "Ursula K. Le Guin, 1974", "Bookshelf"),
                        ],
                        [],
                    ),
                ],
            ),
            (
                "Nonfiction",
                [
                    ("The Sixth Extinction", 1, "Elizabeth Kolbert, 2014", "Bookshelf"),
                    ("The Soul of a New Machine", 1, "Tracy Kidder, 1981", "Bookshelf"),
                    ("Blue Highways", 1, "William Least Heat-Moon, 1982", "Bookshelf"),
                    ("The Warmth of Other Suns", 1, "Isabel Wilkerson, 2010", "Bookshelf"),
                ],
                [],
            ),
            (
                "Cookbooks",
                [
                    ("Salt Fat Acid Heat", 1, "Samin Nosrat, 2017", "Kitchen shelf"),
                    ("The Joy of Cooking", 1, "Irma S. Rombauer, 1931", "Kitchen shelf"),
                    ("An Everlasting Meal", 1, "Tamar Adler, 2011", "Kitchen shelf"),
                ],
                [],
            ),
        ],
    ),
    (
        "Records",
        [
            ("Record cleaning brush", 1, "Carbon fibre, replace pad yearly", "Record crate"),
        ],
        [
            (
                "Jazz",
                [
                    # AE2: the artist lives only in the notes, so search finds it.
                    ("Kind of Blue", 1, "Miles Davis, 1959", "Record crate"),
                    ("A Love Supreme", 1, "John Coltrane, 1965", "Record crate"),
                    ("Mingus Ah Um", 1, "Charles Mingus, 1959", "Record crate"),
                    ("Time Out", 1, "The Dave Brubeck Quartet, 1959", "Record crate"),
                    ("Head Hunters", 1, "Herbie Hancock, 1973", "Record crate"),
                ],
                [],
            ),
            (
                "Rock",
                [
                    ("Rumours", 1, "Fleetwood Mac, 1977", "Record crate"),
                    ("Led Zeppelin IV", 1, "Led Zeppelin, 1971", "Record crate"),
                    ("Marquee Moon", 1, "Television, 1977", "Record crate"),
                    ("The Velvet Underground and Nico", 1, "The Velvet Underground, 1967", "Record crate"),
                ],
                [],
            ),
            (
                "Soul and Funk",
                [
                    ("What's Going On", 1, "Marvin Gaye, 1971", "Record crate"),
                    ("Songs in the Key of Life", 1, "Stevie Wonder, 1976", "Record crate"),
                    ("Superfly", 1, "Curtis Mayfield, 1972", "Record crate"),
                    ("Back to Black", 1, "Amy Winehouse, 2006", "Shelf above the deck"),
                ],
                [],
            ),
        ],
    ),
]


# --- Seeding ---------------------------------------------------------------

def _create_branch(node, parent_id=None):
    """Create one category, its items, and its sub-categories. Returns item count."""
    name, items, children = node
    category_id = db.create_category(name, parent_id=parent_id)
    for item_name, quantity, notes, location in items:
        db.create_item(
            item_name,
            category_id=category_id,
            location_id=db.get_or_create_location(location),
            quantity=quantity,
            notes=notes,
        )
    count = len(items)
    for child in children:
        count += _create_branch(child, parent_id=category_id)
    return count


def seed(quiet=False):
    """Rebuild the schema and populate it with the seed inventory.

    Operates on whatever ``db.DB_PATH`` currently points at, so tests can seed a
    throwaway file. Destructive by design (KTD4) -- ``main()`` owns the guard
    that asks before wiping real data. Returns {collection name: item count}.
    """
    db.reset_db()
    summary = {node[0]: _create_branch(node) for node in INVENTORY}
    if not quiet:
        _print_summary(summary)
    return summary


def _print_summary(summary):
    print(f"Seeded {db.DB_PATH}")
    for name, count in summary.items():
        print(f"  {name:<10} {count} items")
    print(f"Total: {sum(summary.values())} items across {len(summary)} collections.")


# --- Destructive-run guard -------------------------------------------------

def existing_item_count():
    """How much inventory the target database already holds.

    An absent file or a database without the PRIMS schema counts as empty: there
    is nothing to lose, so seeding it needs no confirmation.

    Every other failure -- a locked database, a corrupt file, a permissions
    problem -- re-raises instead. A count that cannot be taken is not a count of
    zero, and this guard stands between real inventory and reset_db(): reporting
    "empty" for a database nobody could read would wipe it without asking.
    """
    try:
        return len(db.get_all_items())
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return 0
        raise


def _confirm(item_count):
    print(f"{db.DB_PATH} already holds {item_count} items.")
    print("Seeding drops every table and rebuilds it from the seed inventory.")
    try:
        answer = input("Wipe it and reseed? [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer.strip().lower() in ("y", "yes")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Rebuild the PRIMS database and fill it with seed data.",
    )
    parser.add_argument(
        "-f",
        "--force",
        "--yes",
        action="store_true",
        help="skip the confirmation prompt when the database already has items",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if not args.force:
        try:
            existing = existing_item_count()
        except sqlite3.DatabaseError as exc:
            # Unreadable is not empty. Refuse rather than reach reset_db().
            print(f"Cannot read {db.DB_PATH}: {exc}", file=sys.stderr)
            print(
                "Not seeding: refusing to wipe a database this script cannot read.",
                file=sys.stderr,
            )
            return 2
        if existing and not _confirm(existing):
            print("Aborted; nothing was changed.")
            return 1

    seed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
