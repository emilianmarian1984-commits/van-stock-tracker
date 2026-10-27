import csv
import io
from datetime import date

from flask import (Blueprint, Response, abort, flash, g, redirect,
                   render_template, request, url_for)

from .auth import login_required
from .db import get_db

bp = Blueprint("stock", __name__)

CATEGORIES = ["Filters", "Brakes", "Electrical", "Fluids", "Engine", "General"]

# Security awareness campaign - short tips shown on the dashboard, one per day.
# Each tip maps back to a row in the threat table (see README / portfolio).
VAN_TIPS = [
    ("Lock the phone, not just the van",
     "Set a 6-digit PIN or fingerprint. A stolen phone that's unlocked = "
     "your whole stock list and customer job refs.", "T3"),
    ("Log out on a shared laptop",
     "Using a customer's or a mate's computer? Hit Log out before you walk away.",
     "T4"),
    ("Three random words",
     "Your password should be three random words, e.g. 'spanner-cloud-tulip'. "
     "Never the same one as your email.", "T1"),
    ("Parts 'supplier' texting a link?",
     "Real suppliers don't ask you to log in through a text link. Open the app "
     "yourself from your bookmark.", "T5"),
    ("Spotted a weird stock change?",
     "Check History. If a movement isn't yours, change your password today.", "T1"),
]


def get_part(part_id):
    part = get_db().execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    if part is None:
        abort(404, f"Part {part_id} doesn't exist.")
    return part


def _read_part_form():
    """Validate the add/edit form. Returns (data, errors)."""
    f = request.form
    errors = []
    data = {
        "name": f.get("name", "").strip(),
        "part_number": f.get("part_number", "").strip(),
        "category": f.get("category", "General"),
        "location": f.get("location", "").strip(),
    }
    if not data["name"]:
        errors.append("Part name is required.")
    if len(data["name"]) > 100:
        errors.append("Part name is too long.")
    if data["category"] not in CATEGORIES:
        errors.append("Pick a category from the list.")
    for field in ("quantity", "min_quantity"):
        try:
            data[field] = int(f.get(field, 0))
            if data[field] < 0:
                raise ValueError
        except ValueError:
            errors.append(f"{field.replace('_', ' ').title()} must be a whole number, 0 or more.")
            data[field] = 0
    try:
        data["unit_cost"] = round(float(f.get("unit_cost", 0) or 0), 2)
        if data["unit_cost"] < 0:
            raise ValueError
    except ValueError:
        errors.append("Unit cost must be a number, 0 or more.")
        data["unit_cost"] = 0
    return data, errors


@bp.route("/")
@login_required
def index():
    db = get_db()
    low = db.execute(
        "SELECT * FROM parts WHERE quantity <= min_quantity ORDER BY quantity, name"
    ).fetchall()
    totals = db.execute(
        "SELECT COUNT(*) AS lines, COALESCE(SUM(quantity),0) AS items,"
        " COALESCE(SUM(quantity * unit_cost),0) AS value FROM parts"
    ).fetchone()
    recent = db.execute(
        "SELECT m.*, p.name AS part_name, u.username FROM movements m"
        " JOIN parts p ON p.id = m.part_id JOIN users u ON u.id = m.user_id"
        " ORDER BY m.id DESC LIMIT 5"
    ).fetchall()
    tip = VAN_TIPS[date.today().toordinal() % len(VAN_TIPS)]
    return render_template("stock/index.html", low=low, totals=totals,
                           recent=recent, tip=tip)


@bp.route("/parts")
@login_required
def parts():
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "")
    sql = "SELECT * FROM parts WHERE 1=1"
    params = []
    if q:
        sql += " AND (name LIKE ? OR part_number LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if cat in CATEGORIES:
        sql += " AND category = ?"
        params.append(cat)
    sql += " ORDER BY category, name"
    rows = get_db().execute(sql, params).fetchall()
    return render_template("stock/parts.html", parts=rows, q=q, cat=cat,
                           categories=CATEGORIES)


@bp.route("/parts/new", methods=("GET", "POST"))
@login_required
def create():
    data = {}
    if request.method == "POST":
        data, errors = _read_part_form()
        if not errors:
            db = get_db()
            cur = db.execute(
                "INSERT INTO parts (name, part_number, category, location, quantity,"
                " min_quantity, unit_cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data["name"], data["part_number"], data["category"], data["location"],
                 data["quantity"], data["min_quantity"], data["unit_cost"]),
            )
            if data["quantity"]:
                db.execute(
                    "INSERT INTO movements (part_id, user_id, change, reason)"
                    " VALUES (?, ?, ?, 'Opening stock')",
                    (cur.lastrowid, g.user["id"], data["quantity"]),
                )
            db.commit()
            flash(f"Added {data['name']}.")
            return redirect(url_for("stock.parts"))
        for e in errors:
            flash(e)
    return render_template("stock/form.html", part=data, categories=CATEGORIES,
                           title="Add part")


@bp.route("/parts/<int:part_id>/edit", methods=("GET", "POST"))
@login_required
def edit(part_id):
    part = get_part(part_id)
    if request.method == "POST":
        data, errors = _read_part_form()
        if not errors:
            db = get_db()
            diff = data["quantity"] - part["quantity"]
            db.execute(
                "UPDATE parts SET name=?, part_number=?, category=?, location=?,"
                " quantity=?, min_quantity=?, unit_cost=? WHERE id=?",
                (data["name"], data["part_number"], data["category"], data["location"],
                 data["quantity"], data["min_quantity"], data["unit_cost"], part_id),
            )
            if diff:
                db.execute(
                    "INSERT INTO movements (part_id, user_id, change, reason)"
                    " VALUES (?, ?, ?, 'Manual correction')",
                    (part_id, g.user["id"], diff),
                )
            db.commit()
            flash("Part updated.")
            return redirect(url_for("stock.parts"))
        for e in errors:
            flash(e)
        part = data
    return render_template("stock/form.html", part=part, categories=CATEGORIES,
                           title="Edit part", part_id=part_id)


@bp.route("/parts/<int:part_id>/delete", methods=("POST",))
@login_required
def delete(part_id):
    part = get_part(part_id)
    db = get_db()
    db.execute("DELETE FROM parts WHERE id = ?", (part_id,))
    db.commit()
    flash(f"Deleted {part['name']}.")
    return redirect(url_for("stock.parts"))


@bp.route("/parts/<int:part_id>/move", methods=("GET", "POST"))
@login_required
def move(part_id):
    """Book stock in (from supplier) or out (used on a job)."""
    part = get_part(part_id)
    if request.method == "POST":
        direction = request.form.get("direction")
        job_ref = request.form.get("job_ref", "").strip()[:50]
        errors = []
        try:
            qty = int(request.form.get("qty", 0))
            if qty <= 0:
                raise ValueError
        except ValueError:
            errors.append("Quantity must be a whole number above 0.")
            qty = 0
        if direction not in ("in", "out"):
            errors.append("Choose in or out.")
        if direction == "out" and qty > part["quantity"]:
            errors.append(f"Only {part['quantity']} in the van - can't use {qty}.")
        if direction == "out" and not job_ref:
            errors.append("Add a job reference so you can bill the part.")

        if not errors:
            change = qty if direction == "in" else -qty
            reason = "Restock" if direction == "in" else "Used on job"
            db = get_db()
            db.execute("UPDATE parts SET quantity = quantity + ? WHERE id = ?",
                       (change, part_id))
            db.execute(
                "INSERT INTO movements (part_id, user_id, change, reason, job_ref)"
                " VALUES (?, ?, ?, ?, ?)",
                (part_id, g.user["id"], change, reason, job_ref or None),
            )
            db.commit()
            flash(f"{reason}: {qty} x {part['name']}.")
            return redirect(url_for("stock.index"))
        for e in errors:
            flash(e)
    return render_template("stock/move.html", part=part)


@bp.route("/history")
@login_required
def history():
    rows = get_db().execute(
        "SELECT m.*, p.name AS part_name, u.username FROM movements m"
        " JOIN parts p ON p.id = m.part_id JOIN users u ON u.id = m.user_id"
        " ORDER BY m.id DESC LIMIT 200"
    ).fetchall()
    return render_template("stock/history.html", rows=rows)


def _csv_safe(value):
    """Stop CSV/formula injection when the file is opened in Excel."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@bp.route("/export.csv")
@login_required
def export_csv():
    rows = get_db().execute("SELECT * FROM parts ORDER BY category, name").fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Name", "Part number", "Category", "Location", "Qty", "Min", "Unit cost"])
    for r in rows:
        w.writerow([_csv_safe(r["name"]), _csv_safe(r["part_number"]),
                    r["category"], _csv_safe(r["location"]), r["quantity"],
                    r["min_quantity"], f"{r['unit_cost']:.2f}"])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=van-stock.csv"})


@bp.route("/briefing", methods=("GET", "POST"))
@login_required
def briefing():
    """60-second security briefing card shown on first login (campaign artefact 1)."""
    if request.method == "POST":
        if request.form.get("ack") == "yes":
            db = get_db()
            db.execute("UPDATE users SET briefing_done = 1 WHERE id = ?", (g.user["id"],))
            db.commit()
            flash("Thanks - you can find these tips again under Security.")
            return redirect(url_for("stock.index"))
        flash("Tick the box to confirm you've read it.")
    return render_template("stock/briefing.html")


@bp.route("/security")
@login_required
def security():
    return render_template("stock/security.html", tips=VAN_TIPS)
