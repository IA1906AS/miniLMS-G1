"""Defensive Pattern #10: Timed Seat Reservation with Expiration for Limited-Capacity Classes.

This module implements:
1. ReservationStatus: Lifecycle states (HELD, CONFIRMED, CANCELLED, EXPIRED).
2. SeatReservationService: Manages atomic capacity reservations, dynamic hold expiration,
   instant seat reclaim, and concurrency safety.
3. p10_reservation_bp: Flask blueprint exposing seat reservation and confirmation endpoints.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, current_app, g, jsonify, request

from lms_project_1.errors import (
    ConflictError,
    Forbidden,
    NotFound,
    Unauthenticated,
    ValidationError,
)
from lms_project_1.guards import require_role
from lms_project_1.store import Store


class ReservationStatus(enum.StrEnum):
    """Permitted states for a seat reservation."""

    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class SeatReservationService:
    """Service providing atomic capacity enforcement and timed seat reclamation."""

    DEFAULT_TTL_SECONDS = 300  # 5 minutes hold window

    @classmethod
    def get_class_capacity_summary(
        cls,
        class_id: str,
        store: Store,
        now_fn: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        """Calculate live capacity, purging expired reservations atomically."""
        now = now_fn() if now_fn else datetime.now(UTC)

        cls_info = store.classes.get(class_id)
        if cls_info is None:
            raise NotFound(f"Lớp học '{class_id}' không tồn tại")

        capacity = int(cls_info.get("capacity", 30))

        with store.reservation_lock:
            active_holds = 0
            confirmed = 0

            for res in store.seat_reservations.values():
                if res.get("class_id") != class_id:
                    continue

                status = res.get("status")
                if status == ReservationStatus.CONFIRMED:
                    confirmed += 1
                elif status == ReservationStatus.HELD:
                    exp_str = res.get("expires_at", "")
                    exp_dt = datetime.fromisoformat(exp_str) if exp_str else now
                    if now >= exp_dt:
                        # Auto-expire hold
                        res["status"] = ReservationStatus.EXPIRED
                    else:
                        active_holds += 1

            available = max(0, capacity - (confirmed + active_holds))
            return {
                "classId": class_id,
                "className": cls_info.get("name", ""),
                "capacity": capacity,
                "confirmedCount": confirmed,
                "activeHeldCount": active_holds,
                "availableSeats": available,
            }

    @classmethod
    def create_reservation(
        cls,
        actor: dict[str, Any],
        class_id: str,
        store: Store,
        ttl_seconds: int | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        """Atomically claim a temporary seat hold if capacity is available."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        role = str(actor.get("role", "")).upper()
        if role not in ("STUDENT", "ADMIN"):
            raise Forbidden("Chỉ sinh viên mới có thể đặt chỗ lớp học")

        student_id = str(actor.get("id", ""))
        now = now_fn() if now_fn else datetime.now(UTC)
        ttl = ttl_seconds if ttl_seconds is not None else cls.DEFAULT_TTL_SECONDS
        expires_at = now + timedelta(seconds=ttl)

        with store.reservation_lock:
            # Check capacity and purge expired
            summary = cls.get_class_capacity_summary(class_id, store, now_fn=now_fn)
            if summary["availableSeats"] <= 0:
                raise ConflictError("Lớp học đã hết chỗ (Đã đạt giới hạn sĩ số)")

            # Check duplicate active holds or registrations by same student
            for res in store.seat_reservations.values():
                if res.get("class_id") == class_id and res.get("user_id") == student_id:
                    if res.get("status") == ReservationStatus.CONFIRMED:
                        raise ConflictError("Sinh viên đã xác nhận tham gia lớp này")
                    if res.get("status") == ReservationStatus.HELD:
                        exp_str = res.get("expires_at", "")
                        exp_dt = datetime.fromisoformat(exp_str) if exp_str else now
                        if now < exp_dt:
                            raise ConflictError("Sinh viên đang có một lượt giữ chỗ còn hiệu lực")

            reservation_id = f"res_{uuid.uuid4().hex[:12]}"
            record: dict[str, Any] = {
                "id": reservation_id,
                "class_id": class_id,
                "user_id": student_id,
                "status": ReservationStatus.HELD,
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
                "confirmed_at": None,
            }
            store.seat_reservations[reservation_id] = record

        return {
            "message": "Giữ chỗ thành công. Vui lòng xác nhận trước thời hạn hết hạn.",
            "reservation": record,
            "remainingSeats": summary["availableSeats"] - 1,
        }

    @classmethod
    def confirm_reservation(
        cls,
        actor: dict[str, Any],
        class_id: str,
        reservation_id: str,
        store: Store,
        now_fn: Callable[[], datetime] | None = None,
    ) -> dict[str, Any]:
        """Confirm a held seat before it expires. Transitions status to CONFIRMED."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        now = now_fn() if now_fn else datetime.now(UTC)
        actor_id = str(actor.get("id", ""))

        with store.reservation_lock:
            res = store.seat_reservations.get(reservation_id)
            if res is None or res.get("class_id") != class_id:
                raise NotFound(f"Không tìm thấy thông tin giữ chỗ '{reservation_id}'")

            # Ownership check (403)
            if res.get("user_id") != actor_id and str(actor.get("role", "")).upper() != "ADMIN":
                raise Forbidden("Không thể xác nhận giữ chỗ của người khác")

            current_status = res.get("status")
            if current_status == ReservationStatus.CONFIRMED:
                raise ConflictError("Lượt giữ chỗ này đã được xác nhận từ trước")

            # Expiration check (409)
            exp_str = res.get("expires_at", "")
            exp_dt = datetime.fromisoformat(exp_str) if exp_str else now
            if now >= exp_dt or current_status == ReservationStatus.EXPIRED:
                res["status"] = ReservationStatus.EXPIRED
                raise ConflictError("Lượt giữ chỗ đã hết hạn (EXPIRED), không thể xác nhận")

            if current_status != ReservationStatus.HELD:
                raise ConflictError(f"Không thể xác nhận giữ chỗ ở trạng thái {current_status}")

            res["status"] = ReservationStatus.CONFIRMED
            res["confirmed_at"] = now.isoformat()

        return {"message": "Xác nhận đăng ký lớp học thành công", "reservation": res}

    @classmethod
    def cancel_reservation(
        cls,
        actor: dict[str, Any],
        class_id: str,
        reservation_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Cancel a reservation or enrollment, immediately returning capacity."""
        if not actor or not isinstance(actor, dict):
            raise Unauthenticated("Unauthenticated")

        actor_id = str(actor.get("id", ""))

        with store.reservation_lock:
            res = store.seat_reservations.get(reservation_id)
            if res is None or res.get("class_id") != class_id:
                raise NotFound(f"Không tìm thấy thông tin giữ chỗ '{reservation_id}'")

            if res.get("user_id") != actor_id and str(actor.get("role", "")).upper() != "ADMIN":
                raise Forbidden("Không thể hủy giữ chỗ của người khác")

            res["status"] = ReservationStatus.CANCELLED
            res["cancelled_at"] = datetime.now(UTC).isoformat()

        return {"message": "Đã hủy giữ chỗ thành công", "reservation": res}


# Blueprint registration
p10_reservation_bp = Blueprint("p10_reservation", __name__)


@p10_reservation_bp.route("/classes/<class_id>/capacity", methods=["GET"])
@require_role("ADMIN", "admin", "INSTRUCTOR", "instructor", "STUDENT", "student", "teacher")
def get_class_capacity_endpoint(class_id: str) -> tuple[Response, int]:
    """Inspect current capacity, active holds, and available seats for a class."""
    store: Store = current_app.config["STORE"]
    summary = SeatReservationService.get_class_capacity_summary(class_id, store=store)
    return jsonify(summary), 200


@p10_reservation_bp.route("/classes/<class_id>/reservations", methods=["POST"])
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_create_reservation(class_id: str) -> tuple[Response, int]:
    """Hold a temporary seat in a capacity-constrained class."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    body = request.get_json(silent=True) or {}
    ttl = body.get("ttl_seconds")
    if ttl is not None:
        try:
            ttl = int(ttl)
        except ValueError as exc:
            raise ValidationError("ttl_seconds phải là số nguyên") from exc

    result = SeatReservationService.create_reservation(
        actor=actor,
        class_id=class_id,
        store=store,
        ttl_seconds=ttl,
    )
    return jsonify(result), 201


@p10_reservation_bp.route(
    "/classes/<class_id>/reservations/<reservation_id>/confirm",
    methods=["POST"],
)
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_confirm_reservation(class_id: str, reservation_id: str) -> tuple[Response, int]:
    """Confirm a held seat before TTL expiration."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    result = SeatReservationService.confirm_reservation(
        actor=actor,
        class_id=class_id,
        reservation_id=reservation_id,
        store=store,
    )
    return jsonify(result), 200


@p10_reservation_bp.route(
    "/classes/<class_id>/reservations/<reservation_id>/cancel",
    methods=["POST"],
)
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_cancel_reservation(class_id: str, reservation_id: str) -> tuple[Response, int]:
    """Cancel a seat reservation or registration, releasing seat capacity."""
    actor = getattr(g, "actor", None)
    store: Store = current_app.config["STORE"]

    result = SeatReservationService.cancel_reservation(
        actor=actor,
        class_id=class_id,
        reservation_id=reservation_id,
        store=store,
    )
    return jsonify(result), 200
