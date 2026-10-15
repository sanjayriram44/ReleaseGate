from fastapi.testclient import TestClient

H = {"X-User-Id": "alice"}
TODAY = "2026-06-15"


def set_clock(client: TestClient, now: str = f"{TODAY}T12:00:00Z") -> None:
    assert client.put("/api/v1/test/clock", json={"now": now}).status_code == 200


def register(client: TestClient, version: str, end: str | None, **kw: object):  # type: ignore[no-untyped-def]
    body: dict[str, object] = {"product": "Router", "version": version}
    if end is not None:
        body["support_end_date"] = end
    return client.post("/api/v1/releases", json=body, headers=H, **kw)  # type: ignore[arg-type]


def test_ac01_support_status_and_rejection(client: TestClient) -> None:
    set_clock(client)
    past = register(client, "1.0", "2026-06-14")
    today = register(client, "2.0", TODAY)
    future = register(client, "3.0", "2027-01-01")
    assert (past.status_code, today.status_code, future.status_code) == (201, 201, 201)
    assert past.json()["support_status"] == "unsupported"
    assert today.json()["support_status"] == "supported"
    assert future.json()["support_status"] == "supported"

    missing = register(client, "4.0", None)
    assert missing.status_code == 400
    assert missing.json() == {
        "error": {"code": "INVALID_REQUEST", "message": "support_end_date is required"}
    }
    # nothing saved: the same product/version can still be registered afterwards
    assert register(client, "4.0", "2027-01-01").status_code == 201


def test_get_release_recomputes_status_from_clock(client: TestClient) -> None:
    set_clock(client)
    rid = register(client, "1.0", TODAY).json()["release_id"]
    assert client.get(f"/api/v1/releases/{rid}").json()["support_status"] == "supported"
    set_clock(client, "2026-06-16T00:00:00Z")
    assert client.get(f"/api/v1/releases/{rid}").json()["support_status"] == "unsupported"


def test_duplicate_is_409(client: TestClient) -> None:
    assert register(client, "1.0", TODAY).status_code == 201
    dup = register(client, "1.0", "2030-01-01")
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "RELEASE_EXISTS"


def test_unknown_release_is_404(client: TestClient) -> None:
    r = client.get("/api/v1/releases/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "RELEASE_NOT_FOUND"


def test_missing_user_id_is_400(client: TestClient) -> None:
    r = client.post(
        "/api/v1/releases", json={"product": "p", "version": "1", "support_end_date": TODAY}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_inputs_are_400_with_shared_error_shape(client: TestClient) -> None:
    bad = [
        {"product": "p", "version": "1", "support_end_date": "15/06/2026"},
        {"product": "p", "version": "1", "support_end_date": "2026-06-15T00:00:00Z"},
        {"product": "", "version": "1", "support_end_date": TODAY},
        {"product": 5, "version": "1", "support_end_date": TODAY},
        {"version": "1", "support_end_date": TODAY},
    ]
    for body in bad:
        r = client.post("/api/v1/releases", json=body, headers=H)
        assert r.status_code == 400, body
        assert set(r.json()["error"]) >= {"code", "message"}
    r = client.post(
        "/api/v1/releases", content="not json", headers={**H, "Content-Type": "application/json"}
    )
    assert r.status_code == 400


def test_timestamp_in_test_clock_must_be_utc(client: TestClient) -> None:
    r = client.put("/api/v1/test/clock", json={"now": "2026-06-15T12:00:00+02:00"})
    assert r.status_code == 400
    r = client.put("/api/v1/test/clock", json={"now": "2026-06-15T12:00:00"})
    assert r.status_code == 400
    r = client.put("/api/v1/test/clock", json={"now": "2026-06-15T12:00:00Z"})
    assert r.json() == {"now": "2026-06-15T12:00:00Z"}
