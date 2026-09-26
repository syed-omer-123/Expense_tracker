import os
import sqlite3

import pytest
from werkzeug.security import check_password_hash

import app as app_module
from database import db

VALID = {"name": "Jane Doe", "email": "jane@example.com", "password": "password123"}
DUPLICATE_MSG = "An account with that email already exists."


def register(client, **overrides):
    data = {**VALID, **overrides}
    return client.post("/register", data=data)


def test_get_register_renders_form(client):
    response = client.get("/register")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    for field in ('name="name"', 'name="email"', 'name="password"'):
        assert field in body
    assert 'minlength="8"' in body


def test_template_has_no_hardcoded_action():
    path = os.path.join(app_module.app.root_path, "templates", "register.html")
    with open(path, encoding="utf-8") as f:
        source = f.read()
    assert 'action="/register"' not in source
    assert "url_for('register')" in source


def test_valid_registration_redirects_to_login(client, count_users):
    before = count_users()
    response = register(client)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    assert count_users() == before + 1


def test_registration_persists_user(client):
    register(client, email="Jane@Example.COM")
    user = db.get_user_by_email("jane@example.com")
    assert user is not None
    assert user["name"] == "Jane Doe"
    assert user["email"] == "jane@example.com"
    assert user["password_hash"] != VALID["password"]
    assert user["password_hash"].startswith(("scrypt:", "pbkdf2:"))


def test_stored_hash_verifies_password(client):
    register(client)
    user = db.get_user_by_email(VALID["email"])
    assert check_password_hash(user["password_hash"], VALID["password"])
    assert not check_password_hash(user["password_hash"], "wrong-password")


def test_duplicate_email_rejected(client, count_users):
    register(client)
    before = count_users()
    response = register(client)
    assert response.status_code == 409
    assert DUPLICATE_MSG in response.get_data(as_text=True)
    assert count_users() == before


def test_duplicate_email_case_insensitive(client, count_users):
    register(client, email="a@x.com")
    before = count_users()
    response = register(client, email="A@X.com")
    assert response.status_code == 409
    assert count_users() == before


def test_demo_email_rejected_as_duplicate(client, count_users):
    before = count_users()
    demo_hash = db.get_user_by_email("demo@spendly.com")["password_hash"]
    response = register(client, email="Demo@Spendly.com")
    assert response.status_code == 409
    assert count_users() == before
    assert db.get_user_by_email("demo@spendly.com")["password_hash"] == demo_hash


@pytest.mark.parametrize("length", range(0, 8))
def test_short_password_rejected(client, count_users, length):
    before = count_users()
    response = register(client, password="p" * length)
    assert response.status_code == 400
    assert "at least 8 characters" in response.get_data(as_text=True)
    assert count_users() == before


def test_eight_character_password_accepted(client):
    assert register(client, password="p" * 8).status_code == 302


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_rejected(client, count_users, name):
    before = count_users()
    response = register(client, name=name)
    assert response.status_code == 400
    assert count_users() == before


def test_missing_name_rejected(client, count_users):
    before = count_users()
    response = client.post(
        "/register", data={"email": VALID["email"], "password": VALID["password"]}
    )
    assert response.status_code == 400
    assert count_users() == before


@pytest.mark.parametrize(
    "email", ["plain", "a@", "@x.com", "a@@b.com", "", "   "]
)
def test_invalid_email_rejected(client, count_users, email):
    before = count_users()
    response = register(client, email=email)
    assert response.status_code == 400
    assert count_users() == before


def test_empty_post_returns_400_not_500(client):
    assert client.post("/register").status_code == 400


def test_failed_submit_preserves_name_and_email(client):
    response = register(client, password="short")
    body = response.get_data(as_text=True)
    assert 'value="Jane Doe"' in body
    assert 'value="jane@example.com"' in body
    assert "short" not in body.replace("Password must be at least 8 characters.", "")


def test_reflected_values_are_escaped(client):
    response = register(client, name='"><script>alert(1)</script>', password="x")
    body = response.get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body


def test_integrity_error_race_returns_409(client, monkeypatch, count_users):
    register(client)
    before = count_users()
    monkeypatch.setattr(app_module, "get_user_by_email", lambda email: None)
    response = register(client)
    assert response.status_code == 409
    assert DUPLICATE_MSG in response.get_data(as_text=True)
    assert count_users() == before


def test_create_user_returns_id(app):
    user_id = db.create_user("A", "a@example.com", "password123")
    assert isinstance(user_id, int)
    assert db.get_user_by_email("a@example.com")["id"] == user_id


def test_create_user_duplicate_raises_integrity_error(app):
    db.create_user("A", "a@example.com", "password123")
    with pytest.raises(sqlite3.IntegrityError):
        db.create_user("B", "a@example.com", "password123")


def test_get_user_by_email_found_and_none(app):
    assert db.get_user_by_email("demo@spendly.com") is not None
    assert db.get_user_by_email("nobody@example.com") is None


def test_email_with_quote_is_stored_literally(app):
    email = "o'brien@example.com"
    db.create_user("O'Brien", email, "password123")
    assert db.get_user_by_email(email)["email"] == email
