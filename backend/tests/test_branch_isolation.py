"""Branch isolation: a receptionist (or branch manager, doctor, staff) assigned to one branch never sees another's."""
from __future__ import annotations

from tests.booking_helpers import Clinic, iso, ist
from tests.helpers import bearer, otp_login


def _two_branches(client):
    c = Clinic(client)
    north = c.branch
    south = c.post("/branches", {"name": "South", "code": "SOUTH"})
    c.client.patch(f"/api/v1/professionals/{c.pro['id']}", headers=c.h,
                   json={"branches": [{"branch_id": north["id"]}, {"branch_id": south["id"]}]})
    c.put("/schedules", {"professional_id": c.pro["id"], "branch_id": south["id"],
                         "windows": [{"weekday": wd, "start_time": "14:00:00", "end_time": "17:00:00"} for wd in range(5)]})
    at_north = c.staff_book(ist(c.monday, 9), customer={"full_name": "North Patient", "mobile": "9811111111"})
    at_south = c.post("/appointments", {"professional_id": c.pro["id"], "branch_id": south["id"], "service_id": c.service["id"],
                                        "start_at": iso(ist(c.monday, 15)), "customer": {"full_name": "South Patient", "mobile": "9822222222"},
                                        "source": "reception"})
    c.post("/customers", {"full_name": "Walk-in Not Booked Yet", "mobile": "9833333333"})
    return c, north, south, at_north, at_south


def _desk(client, c, branch, mobile="9700000001", role="receptionist"):
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": mobile, "full_name": "Front Desk", "role_code": role, "branch_id": branch["id"]})
    tokens = otp_login(client, mobile)
    client.cookies.clear()
    return {**bearer(tokens), "X-Organization-Id": c.org["id"]}


def _get(client, h, path, **params):
    return client.get(f"/api/v1{path}", headers=h, params=params)


def test_branch_staff_only_see_their_branch(client):
    c, north, south, at_north, at_south = _two_branches(client)
    desk = _desk(client, c, north)
    week = {"from_at": iso(ist(c.monday, 0)), "to_at": iso(ist(c.monday, 23))}

    # Appointments: list, calendar, direct link.
    assert [a["id"] for a in _get(client, desk, "/appointments", **week).json()] == [at_north["id"]]
    assert {e["id"] for e in _get(client, desk, "/appointments/calendar", **week).json()} == {at_north["id"]}
    assert _get(client, desk, f"/appointments/{at_north['id']}").status_code == 200
    assert _get(client, desk, f"/appointments/{at_south['id']}").status_code == 404

    # Changing the other branch's booking is impossible too.
    r = client.post(f"/api/v1/appointments/{at_south['id']}/status", json={"action": "cancel"}, headers=desk)
    assert r.status_code == 404

    # Branches, free times and booking at the other branch.
    assert [b["id"] for b in _get(client, desk, "/branches").json()] == [north["id"]]
    assert _get(client, desk, "/availability", service_id=c.service["id"], branch_id=south["id"], date=c.monday.isoformat()).status_code == 404
    r = client.post("/api/v1/appointments", headers=desk, json={
        "professional_id": c.pro["id"], "branch_id": south["id"], "service_id": c.service["id"], "start_at": iso(ist(c.monday, 16)),
        "customer": {"full_name": "Sneaky", "mobile": "9844444444"}, "source": "reception"})
    assert r.status_code in (404, 422)

    # Patients: the other branch's patients are hidden; someone not booked anywhere yet is visible.
    names = {p["full_name"] for p in _get(client, desk, "/customers", page_size=100).json()["data"]}
    assert "North Patient" in names and "Walk-in Not Booked Yet" in names and "South Patient" not in names
    assert _get(client, desk, f"/customers/{at_south['customer']['id']}").status_code == 404

    # Payments for the other branch's bookings.
    pays = _get(client, desk, "/payments", page_size=100).json()["data"]
    assert {p["appointment_id"] for p in pays if p.get("appointment_id")} <= {at_north["id"]}


def test_owner_still_sees_every_branch(client):
    c, north, south, at_north, at_south = _two_branches(client)
    _desk(client, c, north)
    week = {"from_at": iso(ist(c.monday, 0)), "to_at": iso(ist(c.monday, 23))}
    assert {a["id"] for a in _get(client, c.h, "/appointments", **week).json()} == {at_north["id"], at_south["id"]}
    assert len(_get(client, c.h, "/branches").json()) == 2


def test_staff_without_a_branch_see_the_whole_clinic(client):
    c, north, south, at_north, at_south = _two_branches(client)
    c.post(f"/organizations/{c.org['id']}/members", {"identifier": "9700000009", "full_name": "All Branch Desk", "role_code": "receptionist"})
    tokens = otp_login(client, "9700000009")
    client.cookies.clear()
    h = {**bearer(tokens), "X-Organization-Id": c.org["id"]}
    week = {"from_at": iso(ist(c.monday, 0)), "to_at": iso(ist(c.monday, 23))}
    assert {a["id"] for a in _get(client, h, "/appointments", **week).json()} == {at_north["id"], at_south["id"]}


def test_reports_count_only_the_branch(client):
    c, north, south, at_north, at_south = _two_branches(client)
    manager = _desk(client, c, north, mobile="9700000002", role="branch_manager")
    rows = _get(client, manager, "/reports/appointments", **{"from": c.monday.isoformat(), "to": c.monday.isoformat()}).json()["rows"]
    assert {r["reference"] for r in rows} == {at_north["reference"]}
