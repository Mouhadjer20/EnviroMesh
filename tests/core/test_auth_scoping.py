import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from services import auth, database_access


@pytest.fixture
def client():
    main.app.dependency_overrides.clear()
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


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


@pytest.mark.parametrize(
    "path",
    ["/devices/G41", "/telemetry/?device_id=G41", "/telemetry/G41/latest"],
)
def test_technician_is_denied_device_and_telemetry_routes_outside_group(client, monkeypatch, path):
    technician = {"id": "tech-1", "role": "zone_technician", "group_code": "G3"}
    main.app.dependency_overrides[auth.get_current_user] = lambda: technician
    monkeypatch.setattr(database_access, "get_device_group", lambda device_id: {"group_code": "G4"})

    response = client.get(path)

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied: device belongs to another group"


def test_technician_can_access_device_in_own_group(client, monkeypatch):
    technician = {"id": "tech-1", "role": "zone_technician", "group_code": "G3"}
    main.app.dependency_overrides[auth.get_current_user] = lambda: technician
    monkeypatch.setattr(database_access, "get_device_group", lambda device_id: {"group_code": "G3"})
    monkeypatch.setattr(database_access, "list_devices", lambda *args, **kwargs: [{"device_id": "G31"}])

    response = client.get("/devices/G31")

    assert response.status_code == 200
    assert response.json()["device_id"] == "G31"


def test_device_access_uses_registry_group_and_keeps_unknown_devices_not_found(monkeypatch):
    monkeypatch.setattr(database_access, "get_device_group", lambda device_id: None)

    with pytest.raises(HTTPException) as error:
        auth.ensure_device_access("G99", {"role": "zone_technician", "group_code": "G3"})

    assert error.value.status_code == 404


def test_admin_can_access_device_in_any_group(monkeypatch):
    monkeypatch.setattr(database_access, "get_device_group", lambda device_id: {"group_code": "G4"})

    assert auth.ensure_device_access("G41", {"role": "admin", "group_code": None}) is None
