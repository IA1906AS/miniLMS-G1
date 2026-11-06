"""Course Class Seat Reservation and Timed Hold Management Module.

Provides atomic capacity reservations, dynamic hold expiration (TTL),
instant seat reclaim upon cancellation, and thread-safe concurrency control.
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
        """Calculate real-time capacity and active reservations for a class."""
        now = (now_fn or (lambda: datetime.now(UTC)))()

        with store.reservation_lock:
            # 1. Fetch class details from store
            cls_obj = store.get_class(class_id)
            if not cls_obj:
                raise NotFound(f"Không tìm thấy lớp học với mã '{class_id}'")

            capacity = cls_obj.get("capacity", 30)

            # 2. Reconcile reservations: expire past-deadline holds
            all_res = store.get_reservations_for_class(class_id)
            confirmed_count = 0
            active_holds_count = 0

            for res in all_res:
                status = res.get("status")
                expires_at_str = res.get("expires_at")
                if status == ReservationStatus.CONFIRMED:
                    confirmed_count += 1
                elif status == ReservationStatus.HELD:
                    if expires_at_str:
                        exp = datetime.fromisoformat(expires_at_str)
                        if exp <= now:
                            # Auto-reclaim expired hold
                            res["status"] = ReservationStatus.EXPIRED
                            continue
                    active_holds_count += 1

            available_seats = max(0, capacity - confirmed_count - active_holds_count)

            return {
                "class_id": class_id,
                "classId": class_id,
                "code": cls_obj.get("code", class_id),
                "room": cls_obj.get("room", "Room-Online"),
                "capacity": capacity,
                "confirmed_count": confirmed_count,
                "confirmedCount": confirmed_count,
                "active_holds_count": active_holds_count,
                "activeHoldsCount": active_holds_count,
                "activeHeldCount": active_holds_count,
                "available_seats": available_seats,
                "availableSeats": available_seats,
                "as_of": now.isoformat(),
                "asOf": now.isoformat(),
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
        """Reserve a seat atomically under lock if seats are available."""
        if not actor or not actor.get("id"):
            raise Unauthenticated("Chưa đăng nhập")

        user_id = actor["id"]
        now = (now_fn or (lambda: datetime.now(UTC)))()
        hold_ttl = ttl_seconds if ttl_seconds is not None else cls.DEFAULT_TTL_SECONDS
        if hold_ttl <= 0:
            raise ValidationError("Thời gian giữ chỗ phải lớn hơn 0")

        with store.reservation_lock:
            # 1. Reconcile and check capacity
            summary = cls.get_class_capacity_summary(class_id, store=store, now_fn=now_fn)
            if summary["available_seats"] <= 0:
                raise ConflictError(
                    f"Lớp học {class_id} đã hết chỗ khả dụng (Sĩ số: {summary['capacity']}, "
                    f"Đã giữ: {summary['active_holds_count']}, "
                    f"Đã xác nhận: {summary['confirmed_count']})"
                )

            # 2. Check if user already has an active hold or confirmed seat in this class
            existing = store.get_user_reservation_for_class(class_id=class_id, user_id=user_id)
            if existing:
                st = existing.get("status")
                if st == ReservationStatus.CONFIRMED:
                    raise ConflictError("Bạn đã đăng ký và xác nhận chỗ ở lớp này rồi")
                if st == ReservationStatus.HELD:
                    exp_str = existing.get("expires_at")
                    if exp_str and datetime.fromisoformat(exp_str) > now:
                        raise ConflictError(
                            "Bạn đang có một phiên giữ chỗ còn hiệu lực. "
                            "Vui lòng xác nhận hoặc chờ hết hạn."
                        )

            # 3. Create hold record
            res_id = f"res-{uuid.uuid4().hex[:10]}"
            expires_at = now + timedelta(seconds=hold_ttl)
            record: dict[str, Any] = {
                "id": res_id,
                "class_id": class_id,
                "user_id": user_id,
                "status": ReservationStatus.HELD,
                "expires_at": expires_at.isoformat(),
                "created_at": now.isoformat(),
                "confirmed_at": None,
            }

            store.save_reservation(record)

            return {
                "message": "Giữ chỗ thành công. Vui lòng xác nhận trước khi hết hạn.",
                "reservation": record,
                "ttl_seconds": hold_ttl,
                "expires_at": expires_at.isoformat(),
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
        """Confirm a held seat before TTL expires, locking it in permanently."""
        if not actor or not actor.get("id"):
            raise Unauthenticated("Chưa đăng nhập")

        user_id = actor["id"]
        role = actor.get("role", "").lower()
        now = (now_fn or (lambda: datetime.now(UTC)))()

        with store.reservation_lock:
            res = store.get_reservation(reservation_id)
            if not res or res.get("class_id") != class_id:
                raise NotFound(f"Không tìm thấy mã giữ chỗ '{reservation_id}' cho lớp {class_id}")

            # Authorization: only reservation owner or admin can confirm
            if res.get("user_id") != user_id and role != "admin":
                raise Forbidden("Bạn không có quyền xác nhận giữ chỗ của người khác")

            current_status = res.get("status")
            if current_status == ReservationStatus.CONFIRMED:
                return {"message": "Chỗ đã được xác nhận từ trước", "reservation": res}

            if current_status in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
                raise ConflictError(
                    f"Không thể xác nhận giữ chỗ đã ở trạng thái '{current_status}'"
                )

            # Check expiration
            exp_str = res.get("expires_at")
            if exp_str:
                exp = datetime.fromisoformat(exp_str)
                if exp <= now:
                    res["status"] = ReservationStatus.EXPIRED
                    raise ConflictError(
                        "Thời gian giữ chỗ đã hết hạn. Chỗ đã được giải phóng cho học viên khác."
                    )

            # Mark confirmed
            res["status"] = ReservationStatus.CONFIRMED
            res["confirmed_at"] = now.isoformat()

            return {
                "message": "Xác nhận đăng ký lớp học thành công",
                "reservation": res,
            }

    @classmethod
    def cancel_reservation(
        cls,
        actor: dict[str, Any],
        class_id: str,
        reservation_id: str,
        store: Store,
    ) -> dict[str, Any]:
        """Cancel a reservation/hold, immediately releasing the capacity for others."""
        if not actor or not actor.get("id"):
            raise Unauthenticated("Chưa đăng nhập")

        user_id = actor["id"]
        role = actor.get("role", "").lower()

        with store.reservation_lock:
            res = store.get_reservation(reservation_id)
            if not res or res.get("class_id") != class_id:
                raise NotFound(f"Không tìm thấy mã giữ chỗ '{reservation_id}'")

            if res.get("user_id") != user_id and role != "admin":
                raise Forbidden("Bạn không có quyền hủy giữ chỗ của người khác")

            res["status"] = ReservationStatus.CANCELLED
            res["cancelled_at"] = datetime.now(UTC).isoformat()

        return {"message": "Đã hủy giữ chỗ thành công", "reservation": res}


# Blueprint registration
reservations_bp = Blueprint("reservations", __name__)
p10_reservation_bp = reservations_bp  # Backward compatibility alias


@reservations_bp.route("/classes/<class_id>/capacity", methods=["GET"])
@require_role("ADMIN", "admin", "INSTRUCTOR", "instructor", "STUDENT", "student", "teacher")
def get_class_capacity_endpoint(class_id: str) -> tuple[Response, int]:
    """Inspect current capacity, active holds, and available seats for a class."""
    store: Store = current_app.config["STORE"]
    summary = SeatReservationService.get_class_capacity_summary(class_id, store=store)
    return jsonify(summary), 200


@reservations_bp.route("/classes/<class_id>/reservations", methods=["POST"])
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_create_reservation(class_id: str) -> tuple[Response, int]:
    """Hold a temporary seat in a capacity-constrained class."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
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


@reservations_bp.route(
    "/classes/<class_id>/reservations/<reservation_id>/confirm",
    methods=["POST"],
)
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_confirm_reservation(class_id: str, reservation_id: str) -> tuple[Response, int]:
    """Confirm a held seat before TTL expiration."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]

    result = SeatReservationService.confirm_reservation(
        actor=actor,
        class_id=class_id,
        reservation_id=reservation_id,
        store=store,
    )
    return jsonify(result), 200


@reservations_bp.route(
    "/classes/<class_id>/reservations/<reservation_id>/cancel",
    methods=["POST"],
)
@require_role("STUDENT", "student", "ADMIN", "admin")
def post_cancel_reservation(class_id: str, reservation_id: str) -> tuple[Response, int]:
    """Cancel a seat reservation or registration, releasing seat capacity."""
    actor = getattr(g, "actor", None)
    if not actor or not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    store: Store = current_app.config["STORE"]

    result = SeatReservationService.cancel_reservation(
        actor=actor,
        class_id=class_id,
        reservation_id=reservation_id,
        store=store,
    )
    return jsonify(result), 200
