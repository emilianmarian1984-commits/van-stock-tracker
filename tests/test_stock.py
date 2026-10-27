from vanstock.db import get_db


def add_part(client, **kw):
    data = {"name": "Oil filter", "part_number": "HU 816 x", "category": "Filters",
            "location": "Bin A1", "quantity": "5", "min_quantity": "2", "unit_cost": "7.50"}
    data.update(kw)
    return client.post("/parts/new", data=data)


def test_create_part_and_opening_movement(app, client, auth):
    auth.setup_and_login()
    add_part(client)
    with app.app_context():
        db = get_db()
        assert db.execute("SELECT quantity FROM parts").fetchone()[0] == 5
        assert db.execute("SELECT change FROM movements").fetchone()[0] == 5


def test_validation_rejects_bad_input(app, client, auth):
    auth.setup_and_login()
    r = add_part(client, name="", quantity="-3", category="Hacked")
    assert b"Part name is required" in r.data
    assert b"must be a whole number" in r.data
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM parts").fetchone()[0] == 0


def test_use_part_on_job_reduces_stock(app, client, auth):
    auth.setup_and_login()
    add_part(client)
    client.post("/parts/1/move", data={"direction": "out", "qty": "2", "job_ref": "AB12 CDE"})
    with app.app_context():
        assert get_db().execute("SELECT quantity FROM parts").fetchone()[0] == 3


def test_cannot_use_more_than_in_van(app, client, auth):
    auth.setup_and_login()
    add_part(client, quantity="1")
    r = client.post("/parts/1/move", data={"direction": "out", "qty": "4", "job_ref": "X"})
    assert b"Only 1 in the van" in r.data
    with app.app_context():
        assert get_db().execute("SELECT quantity FROM parts").fetchone()[0] == 1


def test_job_ref_required_when_using_part(client, auth):
    auth.setup_and_login()
    add_part(client)
    r = client.post("/parts/1/move", data={"direction": "out", "qty": "1", "job_ref": ""})
    assert b"Add a job reference" in r.data


def test_low_stock_shows_on_dashboard(client, auth):
    auth.setup_and_login()
    add_part(client, name="Fuel filter", quantity="1", min_quantity="2")
    add_part(client, name="Glow plug", quantity="8", min_quantity="2")
    r = client.get("/")
    assert b"Low stock (1)" in r.data
    assert b"Fuel filter" in r.data


def test_search_is_parameterised(client, auth):
    auth.setup_and_login()
    add_part(client)
    r = client.get("/parts?q=' OR 1=1 --")
    assert r.status_code == 200
    assert b"No parts found" in r.data


def test_html_is_escaped(client, auth):
    auth.setup_and_login()
    add_part(client, name="<script>alert(1)</script>")
    r = client.get("/parts")
    assert b"<script>alert(1)</script>" not in r.data
    assert b"&lt;script&gt;" in r.data


def test_csv_export_blocks_formula_injection(client, auth):
    auth.setup_and_login()
    add_part(client, name="=HYPERLINK(\"http://evil\")")
    r = client.get("/export.csv")
    assert b"'=HYPERLINK" in r.data


def test_edit_and_delete(app, client, auth):
    auth.setup_and_login()
    add_part(client)
    client.post("/parts/1/edit", data={"name": "Oil filter N47", "category": "Filters",
                                       "quantity": "4", "min_quantity": "2", "unit_cost": "8"})
    with app.app_context():
        assert get_db().execute("SELECT name FROM parts").fetchone()[0] == "Oil filter N47"
    client.post("/parts/1/delete")
    with app.app_context():
        assert get_db().execute("SELECT COUNT(*) FROM parts").fetchone()[0] == 0
