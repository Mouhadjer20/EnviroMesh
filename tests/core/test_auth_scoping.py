import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services import auth, database_access


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.mark.parametrize(
    "path",
    ["/devices/", "/telemetry/", "/groups/", "/users/", "/auth/me"],
)
def test_protected_routes_reject_anonymous_requests(client, path):
    response = client.get(path)
    assert response.status_code == 401


def test_admin_dependency_rejects_technician():
    with pytest.raises(HTTPException) as error:
        auth.require_admin({"role": "zone_technician"})
    assert error.value.status_code == 403


def test_group_scope_is_derived_from_the_authenticated_user():
    assert auth.scope_group({"role": "admin", "group_code": None}) is None
    assert auth.scope_group({"role": "zone_technician", "group_code": "G3"}) == "G3"
    assert auth.scope_group({"role": "zone_technician", "group_code": None}) == "-"


def test_password_rotation_blocks_regular_api_access():
    user = {"password_change_required": True}
    with pytest.raises(HTTPException) as error:
        auth.get_current_user(user)
    assert error.value.status_code == 403


@pytest.mark.parametrize("query", ["list_telemetry", "latest_telemetry"])
def test_technician_telemetry_scope_uses_registry_membership(monkeypatch, query):
    captured = {}

    def capture(sql, params=None, what="data"):
        captured.update(sql=sql, params=params, what=what)
        return []

    monkeypatch.setattr(database_access, "_query", capture)
    if query == "list_telemetry":
        database_access.list_telemetry(group_code="G3")
    else:
        database_access.latest_telemetry(group_code="G3")

    assert captured["params"]["group_code"] == "G3"
    assert "g.group_code = %(group_code)s" in captured["sql"]
    assert "metadata->>'group_code') = %(group_code)s" not in captured["sql"]
