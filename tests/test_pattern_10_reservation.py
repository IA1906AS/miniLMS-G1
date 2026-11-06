"""Tests for Defensive Pattern #10: Timed Seat Reservation with Expiration (p10_reservation.py).

Covers:
1. Inspect capacity summary (GET /classes/<class_id>/capacity).
2. Create temporary seat hold (POST /classes/<class_id>/reservations).
3. Enforce maximum capacity (HTTP 409 when full).
4. Reject duplicate holds by the same student (HTTP 409).
5. Confirm held reservation within TTL window (POST /.../confirm).
6. Cancel reservation & instant seat reclaim (POST /.../cancel).
7. Automatic expiration of expired holds & capacity reclamation.
8. Role enforcement & authentication gate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from flask.testing import FlaskClient

from lms_project_1 import create_app
from lms_project_1.errors import ConflictError
from lms_project_1.reservations import SeatReservationService


@pytest.fixture
def client() -> Any:
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_URL": None,
            "JWT_SECRET": "super_secret_jwt_key_that_is_at_least_32_characters_long",
        }
    )
    with app.test_client() as c:
        yield c


def login_user(client: Any, email: str, password: str = "Lms@2026") -> dict[str, Any]:
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, f"Login failed for {email}: {res.get_json()}"
    return res.get_json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_get_class_capacity_summary(client: FlaskClient) -> None:
    """GET /classes/<class_id>/capacity returns accurate initial capacity."""
    student_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    headers = auth_header(student_token)

    res = client.get("/classes/lab_ai_101/capacity", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["classId"] == "lab_ai_101"
    assert data["capacity"] == 2
    assert data["confirmedCount"] == 0
    assert data["activeHeldCount"] == 0
    assert data["availableSeats"] == 2


def test_create_and_confirm_reservation(client: FlaskClient) -> None:
    """Student creates a seat reservation, then confirms it successfully."""
    student_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    headers = auth_header(student_token)

    # 1. Hold a seat
    res_hold = client.post(
        "/classes/lab_ai_101/reservations",
        json={"ttl_seconds": 300},
        headers=headers,
    )
    assert res_hold.status_code == 201
    hold_data = res_hold.get_json()
    reservation = hold_data["reservation"]
    assert reservation["status"] == "HELD"
    assert reservation["class_id"] == "lab_ai_101"
    res_id = reservation["id"]

    # 2. Check capacity: available seats reduced from 2 to 1
    res_cap = client.get("/classes/lab_ai_101/capacity", headers=headers)
    assert res_cap.status_code == 200
    assert res_cap.get_json()["availableSeats"] == 1
    assert res_cap.get_json()["activeHeldCount"] == 1

    # 3. Confirm reservation
    res_confirm = client.post(
        f"/classes/lab_ai_101/reservations/{res_id}/confirm",
        headers=headers,
    )
    assert res_confirm.status_code == 200
    conf_data = res_confirm.get_json()
    assert conf_data["reservation"]["status"] == "CONFIRMED"
    assert conf_data["reservation"]["confirmed_at"] is not None

    # 4. Check capacity: confirmed = 1, available = 1
    res_cap2 = client.get("/classes/lab_ai_101/capacity", headers=headers)
    assert res_cap2.get_json()["confirmedCount"] == 1
    assert res_cap2.get_json()["activeHeldCount"] == 0
    assert res_cap2.get_json()["availableSeats"] == 1


def test_capacity_exhaustion_enforcement(client: FlaskClient) -> None:
    """When all seats are held or confirmed, new reservation requests are rejected with 409."""
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    dung_token = login_user(client, "dung.sv@lms.test")["accessToken"]
    em_token = login_user(client, "em.sv@lms.test")["accessToken"]

    # Student Chi holds seat 1 of 2
    r1 = client.post("/classes/lab_ai_101/reservations", headers=auth_header(chi_token))
    assert r1.status_code == 201

    # Student Dung holds seat 2 of 2
    r2 = client.post("/classes/lab_ai_101/reservations", headers=auth_header(dung_token))
    assert r2.status_code == 201

    # Student Em attempts to hold seat 3 -> Class is full (HTTP 409 Conflict)
    r3 = client.post("/classes/lab_ai_101/reservations", headers=auth_header(em_token))
    assert r3.status_code == 409
    assert r3.get_json()["error"] == "CONFLICT"


def test_duplicate_active_hold_rejected(client: FlaskClient) -> None:
    """A student cannot hold multiple seats in the same class at the same time."""
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    headers = auth_header(chi_token)

    # First hold succeeds
    r1 = client.post("/classes/seminar_sec/reservations", headers=headers)
    assert r1.status_code == 201

    # Second hold by same student fails with 409
    r2 = client.post("/classes/seminar_sec/reservations", headers=headers)
    assert r2.status_code == 409
    assert r2.get_json()["error"] == "CONFLICT"


def test_cancel_reservation_reclaims_capacity(client: FlaskClient) -> None:
    """Cancelling a reservation immediately reclaims seat capacity."""
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    headers = auth_header(chi_token)

    # 1. Hold a seat in lab_ai_101
    r_hold = client.post("/classes/lab_ai_101/reservations", headers=headers)
    assert r_hold.status_code == 201
    res_id = r_hold.get_json()["reservation"]["id"]

    # Capacity is 1 available
    cap1 = client.get("/classes/lab_ai_101/capacity", headers=headers).get_json()
    assert cap1["availableSeats"] == 1

    # 2. Cancel the reservation
    r_cancel = client.post(f"/classes/lab_ai_101/reservations/{res_id}/cancel", headers=headers)
    assert r_cancel.status_code == 200
    assert r_cancel.get_json()["reservation"]["status"] == "CANCELLED"

    # Capacity is restored to 2 available
    cap2 = client.get("/classes/lab_ai_101/capacity", headers=headers).get_json()
    assert cap2["availableSeats"] == 2


def test_expired_hold_auto_reclaimed(client: FlaskClient) -> None:
    """Expired holds are purged and seat capacity is automatically reclaimed."""
    chi_token = login_user(client, "chi.sv@lms.test")["accessToken"]
    headers_chi = auth_header(chi_token)

    # Chi holds seat with TTL = 10s
    r_hold = client.post(
        "/classes/lab_ai_101/reservations",
        json={"ttl_seconds": 10},
        headers=headers_chi,
    )
    assert r_hold.status_code == 201
    res_id = r_hold.get_json()["reservation"]["id"]

    # Simulate clock advance past expiration
    store = client.application.store  # type: ignore[attr-defined]
    future_time = datetime.now(UTC) + timedelta(seconds=60)

    summary = SeatReservationService.get_class_capacity_summary(
        "lab_ai_101",
        store=store,
        now_fn=lambda: future_time,
    )
    # Seat is reclaimed back to full capacity (2)
    assert summary["availableSeats"] == 2
    assert summary["activeHeldCount"] == 0

    # Confirming the expired reservation fails with 409
    with pytest.raises(ConflictError):
        SeatReservationService.confirm_reservation(
            actor={"id": "u4", "role": "STUDENT"},
            class_id="lab_ai_101",
            reservation_id=res_id,
            store=store,
            now_fn=lambda: future_time,
        )


def test_guest_unauthenticated_rejected(client: FlaskClient) -> None:
    """Unauthenticated request to reserve seats is blocked by Gate (401)."""
    res = client.post("/classes/lab_ai_101/reservations", json={})
    assert res.status_code == 401
