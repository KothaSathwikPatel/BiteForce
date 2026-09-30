import os

from app.config import load_dotenv, load_settings, normalise_database_url


def test_defaults_are_safe():
    s = load_settings({})
    assert s.demo_mode and s.auto_send and s.enforce_area
    assert s.database_url == "sqlite:///./bitetrace.db"
    assert s.resend_api_key is None and s.gemini_api_key is None
    assert len(s.secret_salt) >= 32  # random fallback, never empty


def test_vercel_defaults_to_tmp_sqlite():
    assert load_settings({"VERCEL": "1"}).database_url == "sqlite:////tmp/bitetrace.db"


def test_postgres_url_is_normalised():
    assert normalise_database_url("postgres://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalise_database_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalise_database_url("sqlite://") == "sqlite://"


def test_flags_and_numbers_parse():
    s = load_settings({"DEMO_MODE": "false", "AUTO_SEND": "0", "AREA_RADIUS_KM": "12.5",
                       "SECRET_SALT": "x" * 40, "REPORT_TO_EMAIL": "a@b.c"})
    assert not s.demo_mode and not s.auto_send
    assert s.area_radius_km == 12.5 and s.secret_salt == "x" * 40
    assert s.report_to_email == "a@b.c"


def test_bad_number_falls_back():
    assert load_settings({"AREA_RADIUS_KM": "abc"}).area_radius_km == 25.0


def test_dotenv_reader_strips_comments_and_never_overrides(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# c\nFOO_TEST_A=hello   # inline\nFOO_TEST_B='quoted'\nFOO_TEST_C=fromfile\nbadline\n")
    monkeypatch.setenv("FOO_TEST_C", "fromenv")
    monkeypatch.delenv("FOO_TEST_A", raising=False)
    monkeypatch.delenv("FOO_TEST_B", raising=False)
    load_dotenv(f)
    assert os.environ["FOO_TEST_A"] == "hello"
    assert os.environ["FOO_TEST_B"] == "quoted"
    assert os.environ["FOO_TEST_C"] == "fromenv"
    monkeypatch.delenv("FOO_TEST_A")
    monkeypatch.delenv("FOO_TEST_B")


def test_missing_dotenv_is_fine(tmp_path):
    load_dotenv(tmp_path / "nope.env")
