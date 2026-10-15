from app.main import create_app


def test_app_builds() -> None:
    assert create_app().title
