import sqlite3

import click
from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))


@click.command("init-db")
def init_db_command():
    """Wipe and recreate the database tables."""
    init_db()
    click.echo("Database initialised.")


@click.command("seed-demo")
def seed_demo_command():
    """Add some typical van parts so the app is not empty for a demo."""
    db = get_db()
    parts = [
        ("Oil filter", "HU 816 x", "Filters", "Bin A1", 6, 3, 7.50),
        ("Air filter", "C 30 005", "Filters", "Bin A2", 2, 2, 11.20),
        ("Fuel filter", "WK 820/14", "Filters", "Bin A3", 1, 2, 19.90),
        ("Glow plug", "0 250 403 009", "Electrical", "Drawer 2", 8, 4, 9.80),
        ("Brake pads front", "GDB1956", "Brakes", "Shelf B", 1, 1, 32.00),
        ("Engine oil 5W-30 5L", "C3 LL-04", "Fluids", "Floor", 3, 2, 28.50),
        ("Wiper blade 24in", "AR604S", "General", "Door pocket", 0, 1, 12.00),
    ]
    db.executemany(
        "INSERT INTO parts (name, part_number, category, location, quantity,"
        " min_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
        parts,
    )
    db.commit()
    click.echo(f"Added {len(parts)} demo parts.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)
