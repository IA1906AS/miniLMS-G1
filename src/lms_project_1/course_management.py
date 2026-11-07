"""Course catalog, authoring, curriculum and governance vertical slice."""

from __future__ import annotations

import math
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from flask import Blueprint, Response, current_app, g, jsonify, request, send_file

from lms_project_1.errors import Conflict, Forbidden, NotFound, Unauthenticated, ValidationError
from lms_project_1.guards import require_role
from lms_project_1.models import (
    Course,
    CourseCategory,
    CourseChapter,
    CourseRoadmapItem,
    Lesson,
    LessonResource,
)

course_bp = Blueprint("course_management", __name__)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _store() -> Any:
    return current_app.config["STORE"]


def _actor() -> dict[str, Any]:
    actor = getattr(g, "actor", None)
    if not isinstance(actor, dict):
        raise Unauthenticated("Unauthenticated")
    return actor


def _json() -> dict[str, Any]:
    if not request.is_json:
        raise ValidationError("Request body must be JSON")
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValidationError("Request body must be a JSON object")
    return value


def _text(value: Any, field: str, *, maximum: int = 255, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValidationError(f"'{field}' is required")
    if len(result) > maximum:
        raise ValidationError(f"'{field}' is too long")
    return result


def _positive_int(value: Any, field: str, *, minimum: int = 1, maximum: int = 10000) -> int:
    if isinstance(value, bool):
        raise ValidationError(f"'{field}' must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"'{field}' must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValidationError(f"'{field}' is out of range")
    return parsed


def _safe_url(value: Any, field: str, *, required: bool = False) -> str:
    result = _text(value, field, maximum=1000, required=required)
    if not result:
        return ""
    parsed = urlparse(result)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValidationError(f"'{field}' must be an absolute HTTP(S) URL")
    return result


def _commit(row: Any) -> None:
    store = _store()
    if store.db_session is None:
        return
    try:
        store.db_session.add(row)
        store.db_session.commit()
    except Exception:
        store.db_session.rollback()
        raise


def _delete_row(model: Any, row_id: str) -> None:
    store = _store()
    if store.db_session is None:
        return
    row = store.db_session.get(model, row_id)
    if row is not None:
        store.db_session.delete(row)
        store.db_session.commit()


def _course(course_id: str) -> dict[str, Any]:
    course = _store().courses.get(course_id)
    if course is None:
        raise NotFound(f"Course '{course_id}' not found")
    return cast(dict[str, Any], course)


def _require_owner(course_id: str) -> dict[str, Any]:
    course = _course(course_id)
    actor = _actor()
    role = str(actor.get("role", "")).upper()
    if role != "ADMIN" and not (
        role in {"TEACHER", "INSTRUCTOR"} and course.get("instructorId") == actor.get("id")
    ):
        raise Forbidden("Only the assigned instructor or admin may manage this course")
    return course


def _curriculum(course_id: str) -> list[dict[str, Any]]:
    store = _store()
    course = _course(course_id)
    chapters = sorted(
        (dict(item) for item in store.course_chapters.values() if item["courseId"] == course_id),
        key=lambda item: (item["orderIndex"], item["id"]),
    )
    assigned_ids: set[str] = set()
    for chapter in chapters:
        lessons = sorted(
            (
                dict(item)
                for item in course.get("lessons", [])
                if item.get("chapterId") == chapter["id"]
            ),
            key=lambda item: (item.get("orderIndex", 1), item["id"]),
        )
        chapter["lessons"] = lessons
        assigned_ids.update(item["id"] for item in lessons)
    unassigned = [
        dict(item) for item in course.get("lessons", []) if item["id"] not in assigned_ids
    ]
    if unassigned:
        chapters.insert(
            0,
            {
                "id": None,
                "courseId": course_id,
                "title": "Course content",
                "orderIndex": 0,
                "lessons": unassigned,
            },
        )
    return chapters


def _roadmap(course_id: str) -> list[dict[str, Any]]:
    return sorted(
        (dict(item) for item in _store().course_roadmap.values() if item["courseId"] == course_id),
        key=lambda item: (item["orderIndex"], item["id"]),
    )


def _detail(course: dict[str, Any]) -> dict[str, Any]:
    store = _store()
    result = dict(course)
    instructor = store.get_user_by_id(str(course.get("instructorId", "")))
    result["instructor"] = (
        {
            "id": instructor["id"],
            "name": instructor.get("fullName") or instructor.get("full_name") or "",
            "email": instructor.get("email", ""),
        }
        if instructor
        else None
    )
    result["category"] = store.course_categories.get(str(course.get("categoryId", "")))
    result["curriculum"] = _curriculum(course["id"])
    result["roadmap"] = _roadmap(course["id"])
    return result


@course_bp.get("/api/public/categories")
def list_public_categories() -> tuple[Response, int]:
    items = sorted(
        (dict(item) for item in _store().course_categories.values()), key=lambda x: x["name"]
    )
    return jsonify(items), 200


@course_bp.get("/api/public/courses/<course_id>")
def public_course_detail(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    if course.get("status") != "PUBLISHED" or not course.get("isVisible", False):
        raise NotFound(f"Course '{course_id}' not found")
    return jsonify(_detail(course)), 200


@course_bp.get("/api/admin/categories")
@require_role("ADMIN")
def list_admin_categories() -> tuple[Response, int]:
    return list_public_categories()


@course_bp.post("/api/admin/categories")
@require_role("ADMIN")
def create_category() -> tuple[Response, int]:
    body = _json()
    name = _text(body.get("name"), "name", maximum=100)
    slug = _text(body.get("slug"), "slug", maximum=100).lower()
    if not _SLUG_RE.fullmatch(slug):
        raise ValidationError("'slug' is invalid")
    store = _store()
    if any(
        x["name"].casefold() == name.casefold() or x["slug"] == slug
        for x in store.course_categories.values()
    ):
        raise Conflict("Category already exists")
    item = {"id": str(uuid.uuid4()), "name": name, "slug": slug}
    _commit(CourseCategory(**item))
    store.course_categories[item["id"]] = item
    return jsonify(item), 201


@course_bp.put("/api/admin/categories/<category_id>")
@require_role("ADMIN")
def update_category(category_id: str) -> tuple[Response, int]:
    store = _store()
    item = store.course_categories.get(category_id)
    if item is None:
        raise NotFound("Category not found")
    body = _json()
    name = _text(body.get("name", item["name"]), "name", maximum=100)
    slug = _text(body.get("slug", item["slug"]), "slug", maximum=100).lower()
    if not _SLUG_RE.fullmatch(slug):
        raise ValidationError("'slug' is invalid")
    if any(
        x["id"] != category_id and (x["name"].casefold() == name.casefold() or x["slug"] == slug)
        for x in store.course_categories.values()
    ):
        raise Conflict("Category already exists")
    if store.db_session is not None:
        row = store.db_session.get(CourseCategory, category_id)
        if row is not None:
            row.name, row.slug = name, slug
            store.db_session.commit()
    item.update(name=name, slug=slug)
    return jsonify(dict(item)), 200


@course_bp.delete("/api/admin/categories/<category_id>")
@require_role("ADMIN")
def delete_category(category_id: str) -> tuple[str, int]:
    store = _store()
    if category_id not in store.course_categories:
        raise NotFound("Category not found")
    if any(course.get("categoryId") == category_id for course in store.courses.values()):
        raise Conflict("Category is in use")
    _delete_row(CourseCategory, category_id)
    del store.course_categories[category_id]
    return "", 204


@course_bp.post("/api/courses")
@require_role("TEACHER", "INSTRUCTOR", "ADMIN")
def create_course() -> tuple[Response, int]:
    actor = _actor()
    body = _json()
    title = _text(body.get("title"), "title")
    description = _text(body.get("description", ""), "description", maximum=5000, required=False)
    category_id = _text(body.get("categoryId", "cat-general"), "categoryId", maximum=36)
    if category_id not in _store().course_categories:
        raise ValidationError("Unknown category")
    price = float(body.get("price", 0))
    if not math.isfinite(price) or price < 0 or price > 1_000_000_000:
        raise ValidationError("'price' is out of range")
    duration = _positive_int(body.get("durationHours", 1), "durationHours")
    thumbnail = _safe_url(body.get("thumbnail", ""), "thumbnail")
    instructor_id = str(actor["id"])
    if str(actor.get("role", "")).upper() == "ADMIN" and body.get("instructorId"):
        instructor_id = _text(body["instructorId"], "instructorId", maximum=36)
    item = {
        "id": str(uuid.uuid4()),
        "title": title,
        "instructorId": instructor_id,
        "categoryId": category_id,
        "description": description,
        "thumbnail": thumbnail,
        "durationHours": duration,
        "price": price,
        "status": "DRAFT",
        "isVisible": False,
        "rejectionReason": None,
        "isFeatured": False,
        "lessons": [],
    }
    _commit(
        Course(
            id=item["id"],
            title=title,
            instructor_id=instructor_id,
            category_id=category_id,
            description=description,
            thumbnail=thumbnail,
            duration_hours=duration,
            price=price,
            status="DRAFT",
            is_visible=False,
        )
    )
    _store().courses[item["id"]] = item
    return jsonify(item), 201


@course_bp.put("/api/courses/<course_id>")
def update_course(course_id: str) -> tuple[Response, int]:
    course = _require_owner(course_id)
    if course.get("status") in {"PENDING", "ARCHIVED"}:
        raise Conflict("Course cannot be edited in its current state")
    body = _json()
    if "title" in body:
        course["title"] = _text(body["title"], "title")
    if "description" in body:
        course["description"] = _text(
            body["description"], "description", maximum=5000, required=False
        )
    if "thumbnail" in body:
        course["thumbnail"] = _safe_url(body["thumbnail"], "thumbnail")
    if "durationHours" in body:
        course["durationHours"] = _positive_int(body["durationHours"], "durationHours")
    if "price" in body:
        price = float(body["price"])
        if not math.isfinite(price) or price < 0 or price > 1_000_000_000:
            raise ValidationError("'price' is out of range")
        course["price"] = price
    if "categoryId" in body:
        category_id = _text(body["categoryId"], "categoryId", maximum=36)
        if category_id not in _store().course_categories:
            raise ValidationError("Unknown category")
        course["categoryId"] = category_id
    course["status"], course["isVisible"], course["rejectionReason"] = "DRAFT", False, None
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(Course, course_id)
        if row is not None:
            row.title = course["title"]
            row.description = course["description"]
            row.thumbnail = course["thumbnail"]
            row.duration_hours = course["durationHours"]
            row.price = course["price"]
            row.category_id = course["categoryId"]
            row.status, row.is_visible, row.rejection_reason = "DRAFT", False, None
            row.updated_at = datetime.now(UTC)
            store.db_session.commit()
    return jsonify(dict(course)), 200


@course_bp.post("/api/courses/<course_id>/chapters")
def create_chapter(course_id: str) -> tuple[Response, int]:
    _require_owner(course_id)
    body = _json()
    item = {
        "id": str(uuid.uuid4()),
        "courseId": course_id,
        "title": _text(body.get("title"), "title"),
        "orderIndex": _positive_int(body.get("orderIndex", 1), "orderIndex"),
    }
    _commit(
        CourseChapter(
            id=item["id"], course_id=course_id, title=item["title"], order_index=item["orderIndex"]
        )
    )
    _store().course_chapters[item["id"]] = item
    return jsonify(item), 201


@course_bp.put("/api/chapters/<chapter_id>")
def update_chapter(chapter_id: str) -> tuple[Response, int]:
    item = _store().course_chapters.get(chapter_id)
    if item is None:
        raise NotFound("Chapter not found")
    _require_owner(item["courseId"])
    body = _json()
    item["title"] = _text(body.get("title", item["title"]), "title")
    item["orderIndex"] = _positive_int(body.get("orderIndex", item["orderIndex"]), "orderIndex")
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(CourseChapter, chapter_id)
        if row is not None:
            row.title, row.order_index = item["title"], item["orderIndex"]
            store.db_session.commit()
    return jsonify(dict(item)), 200


@course_bp.delete("/api/chapters/<chapter_id>")
def delete_chapter(chapter_id: str) -> tuple[str, int]:
    store = _store()
    item = store.course_chapters.get(chapter_id)
    if item is None:
        raise NotFound("Chapter not found")
    _require_owner(item["courseId"])
    _delete_row(CourseChapter, chapter_id)
    course = _course(item["courseId"])
    course["lessons"] = [x for x in course.get("lessons", []) if x.get("chapterId") != chapter_id]
    del store.course_chapters[chapter_id]
    return "", 204


@course_bp.post("/api/chapters/<chapter_id>/lessons")
def create_lesson(chapter_id: str) -> tuple[Response, int]:
    chapter = _store().course_chapters.get(chapter_id)
    if chapter is None:
        raise NotFound("Chapter not found")
    _require_owner(chapter["courseId"])
    body = _json()
    content_type = _text(body.get("contentType", "TEXT"), "contentType", maximum=20).upper()
    if content_type not in {"TEXT", "VIDEO", "MIXED"}:
        raise ValidationError("Unsupported content type")
    video_url = _safe_url(body.get("videoUrl", ""), "videoUrl") or None
    if content_type == "VIDEO" and video_url is None:
        raise ValidationError("Video lessons require 'videoUrl'")
    item = {
        "id": str(uuid.uuid4()),
        "courseId": chapter["courseId"],
        "chapterId": chapter_id,
        "title": _text(body.get("title"), "title"),
        "content": _text(body.get("content", ""), "content", maximum=20000, required=False),
        "contentType": content_type,
        "videoUrl": video_url,
        "orderIndex": _positive_int(body.get("orderIndex", 1), "orderIndex"),
    }
    _commit(
        Lesson(
            id=item["id"],
            course_id=item["courseId"],
            chapter_id=chapter_id,
            title=item["title"],
            content=item["content"],
            content_type=content_type,
            video_url=video_url,
            order_index=item["orderIndex"],
        )
    )
    _course(item["courseId"]).setdefault("lessons", []).append(item)
    return jsonify(item), 201


def _find_lesson(lesson_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    for course in _store().courses.values():
        for lesson in course.get("lessons", []):
            if lesson["id"] == lesson_id:
                return course, lesson
    raise NotFound("Lesson not found")


@course_bp.put("/api/lessons/<lesson_id>")
def update_lesson(lesson_id: str) -> tuple[Response, int]:
    course, lesson = _find_lesson(lesson_id)
    _require_owner(course["id"])
    body = _json()
    lesson["title"] = _text(body.get("title", lesson.get("title")), "title")
    lesson["content"] = _text(
        body.get("content", lesson.get("content", "")), "content", maximum=20000, required=False
    )
    lesson["orderIndex"] = _positive_int(
        body.get("orderIndex", lesson.get("orderIndex", 1)), "orderIndex"
    )
    if "videoUrl" in body:
        lesson["videoUrl"] = _safe_url(body["videoUrl"], "videoUrl") or None
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(Lesson, lesson_id)
        if row is not None:
            row.title, row.content, row.order_index = (
                lesson["title"],
                lesson["content"],
                lesson["orderIndex"],
            )
            row.video_url = lesson.get("videoUrl")
            store.db_session.commit()
    return jsonify(dict(lesson)), 200


@course_bp.delete("/api/lessons/<lesson_id>")
def delete_lesson(lesson_id: str) -> tuple[str, int]:
    course, _lesson = _find_lesson(lesson_id)
    _require_owner(course["id"])
    _delete_row(Lesson, lesson_id)
    course["lessons"] = [x for x in course.get("lessons", []) if x["id"] != lesson_id]
    return "", 204


@course_bp.get("/api/courses/<course_id>/roadmap")
def list_roadmap(course_id: str) -> tuple[Response, int]:
    _require_owner(course_id)
    return jsonify(_roadmap(course_id)), 200


@course_bp.post("/api/courses/<course_id>/roadmap")
def create_roadmap_item(course_id: str) -> tuple[Response, int]:
    _require_owner(course_id)
    body = _json()
    item = {
        "id": str(uuid.uuid4()),
        "courseId": course_id,
        "title": _text(body.get("title"), "title"),
        "description": _text(
            body.get("description", ""), "description", maximum=2000, required=False
        ),
        "orderIndex": _positive_int(body.get("orderIndex", 1), "orderIndex"),
    }
    _commit(
        CourseRoadmapItem(
            id=item["id"],
            course_id=course_id,
            title=item["title"],
            description=item["description"],
            order_index=item["orderIndex"],
        )
    )
    _store().course_roadmap[item["id"]] = item
    return jsonify(item), 201


@course_bp.put("/api/roadmap/<item_id>")
def update_roadmap_item(item_id: str) -> tuple[Response, int]:
    item = _store().course_roadmap.get(item_id)
    if item is None:
        raise NotFound("Roadmap item not found")
    _require_owner(item["courseId"])
    body = _json()
    item["title"] = _text(body.get("title", item["title"]), "title")
    item["description"] = _text(
        body.get("description", item["description"]), "description", maximum=2000, required=False
    )
    item["orderIndex"] = _positive_int(body.get("orderIndex", item["orderIndex"]), "orderIndex")
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(CourseRoadmapItem, item_id)
        if row is not None:
            row.title, row.description, row.order_index = (
                item["title"],
                item["description"],
                item["orderIndex"],
            )
            store.db_session.commit()
    return jsonify(dict(item)), 200


@course_bp.delete("/api/roadmap/<item_id>")
def delete_roadmap_item(item_id: str) -> tuple[str, int]:
    item = _store().course_roadmap.get(item_id)
    if item is None:
        raise NotFound("Roadmap item not found")
    _require_owner(item["courseId"])
    _delete_row(CourseRoadmapItem, item_id)
    del _store().course_roadmap[item_id]
    return "", 204


@course_bp.get("/api/lessons/<lesson_id>/resources")
def list_resources(lesson_id: str) -> tuple[Response, int]:
    course, _lesson = _find_lesson(lesson_id)
    actor = _actor()
    enrolled = _store().get_enrollment(course["id"], str(actor["id"])) is not None
    owner = (
        course.get("instructorId") == actor.get("id")
        or str(actor.get("role", "")).upper() == "ADMIN"
    )
    if not enrolled and not owner:
        raise Forbidden("Lesson resources require enrollment")
    items = [dict(x) for x in _store().lesson_resources.values() if x["lessonId"] == lesson_id]
    return jsonify(items), 200


def _require_resource_access(item: dict[str, Any]) -> dict[str, Any]:
    course, _lesson = _find_lesson(item["lessonId"])
    actor = _actor()
    enrolled = _store().get_enrollment(course["id"], str(actor["id"])) is not None
    if not enrolled and not _is_course_owner(actor, course):
        raise Forbidden("Lesson resources require enrollment")
    return course


def _is_course_owner(actor: dict[str, Any], course: dict[str, Any]) -> bool:
    role = str(actor.get("role", "")).upper()
    return role == "ADMIN" or (
        role in {"TEACHER", "INSTRUCTOR"} and course.get("instructorId") == actor.get("id")
    )


@course_bp.post("/api/lessons/<lesson_id>/resources")
def create_resource(lesson_id: str) -> tuple[Response, int]:
    course, _lesson = _find_lesson(lesson_id)
    _require_owner(course["id"])
    body = _json()
    size = _positive_int(body.get("sizeBytes", 0), "sizeBytes", minimum=0, maximum=104_857_600)
    item = {
        "id": str(uuid.uuid4()),
        "lessonId": lesson_id,
        "title": _text(body.get("title"), "title"),
        "resourceUrl": _safe_url(body.get("resourceUrl"), "resourceUrl", required=True),
        "mimeType": _text(
            body.get("mimeType", "application/octet-stream"), "mimeType", maximum=100
        ),
        "sizeBytes": size,
    }
    _commit(
        LessonResource(
            id=item["id"],
            lesson_id=lesson_id,
            title=item["title"],
            resource_url=item["resourceUrl"],
            mime_type=item["mimeType"],
            size_bytes=size,
        )
    )
    _store().lesson_resources[item["id"]] = item
    return jsonify(item), 201


@course_bp.post("/api/lessons/<lesson_id>/resources/upload")
def upload_resource(lesson_id: str) -> tuple[Response, int]:
    course, _lesson = _find_lesson(lesson_id)
    _require_owner(course["id"])
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ValidationError("A file is required")
    allowed = {
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }
    suffix = allowed.get(str(upload.mimetype).lower())
    if suffix is None:
        raise ValidationError("Unsupported file type")
    maximum = 10 * 1024 * 1024
    payload = upload.stream.read(maximum + 1)
    if not payload or len(payload) > maximum:
        raise ValidationError("File is empty or exceeds 10 MiB")
    storage_key = f"{uuid.uuid4()}{suffix}"
    root = Path(
        current_app.config.get("UPLOAD_ROOT") or Path(current_app.instance_path) / "uploads"
    )
    root.mkdir(parents=True, exist_ok=True)
    target = (root / storage_key).resolve()
    if root.resolve() not in target.parents:
        raise ValidationError("Invalid upload target")
    target.write_bytes(payload)
    item = {
        "id": str(uuid.uuid4()),
        "lessonId": lesson_id,
        "title": str(request.form.get("title") or upload.filename).strip()[:255],
        "resourceUrl": f"internal://{storage_key}",
        "mimeType": str(upload.mimetype).lower(),
        "sizeBytes": len(payload),
    }
    _commit(
        LessonResource(
            id=item["id"],
            lesson_id=lesson_id,
            title=item["title"],
            resource_url=item["resourceUrl"],
            mime_type=item["mimeType"],
            size_bytes=item["sizeBytes"],
        )
    )
    _store().lesson_resources[item["id"]] = item
    return jsonify(item), 201


@course_bp.get("/api/resources/<resource_id>/download")
def download_resource(resource_id: str) -> Response:
    item = _store().lesson_resources.get(resource_id)
    if item is None:
        raise NotFound("Resource not found")
    _require_resource_access(item)
    resource_url = str(item["resourceUrl"])
    if not resource_url.startswith("internal://"):
        raise Conflict("External resources must be opened at their validated URL")
    storage_key = resource_url.removeprefix("internal://")
    root = Path(
        current_app.config.get("UPLOAD_ROOT") or Path(current_app.instance_path) / "uploads"
    )
    target = (root / storage_key).resolve()
    if root.resolve() not in target.parents or not target.is_file():
        raise NotFound("Resource file not found")
    return send_file(
        target,
        mimetype=item["mimeType"],
        as_attachment=True,
        download_name=item["title"],
    )


@course_bp.delete("/api/resources/<resource_id>")
def delete_resource(resource_id: str) -> tuple[str, int]:
    item = _store().lesson_resources.get(resource_id)
    if item is None:
        raise NotFound("Resource not found")
    course, _lesson = _find_lesson(item["lessonId"])
    _require_owner(course["id"])
    _delete_row(LessonResource, resource_id)
    del _store().lesson_resources[resource_id]
    return "", 204


@course_bp.post("/api/courses/<course_id>/submit")
def submit_course(course_id: str) -> tuple[Response, int]:
    course = _require_owner(course_id)
    if course.get("status") not in {"DRAFT", "REJECTED"}:
        raise Conflict("Only draft or rejected courses can be submitted")
    if not course.get("title") or not course.get("description") or not course.get("lessons"):
        raise ValidationError("Course title, description and at least one lesson are required")
    course["status"], course["isVisible"], course["rejectionReason"] = "PENDING", False, None
    _persist_governance(course)
    return jsonify(dict(course)), 200


def _persist_governance(course: dict[str, Any]) -> None:
    store = _store()
    if store.db_session is not None:
        row = store.db_session.get(Course, course["id"])
        if row is not None:
            row.status = course["status"]
            row.is_visible = course["isVisible"]
            row.rejection_reason = course.get("rejectionReason")
            row.updated_at = datetime.now(UTC)
            store.db_session.commit()


@course_bp.post("/api/admin/courses/<course_id>/decision")
@require_role("ADMIN")
def decide_course(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    if course.get("status") != "PENDING":
        raise Conflict("Only pending courses can be reviewed")
    body = _json()
    decision = _text(body.get("decision"), "decision", maximum=20).upper()
    if decision == "APPROVE":
        course["status"], course["isVisible"], course["rejectionReason"] = "PUBLISHED", True, None
    elif decision == "REJECT":
        reason = _text(body.get("reason"), "reason", maximum=500)
        course["status"], course["isVisible"], course["rejectionReason"] = "REJECTED", False, reason
    else:
        raise ValidationError("Decision must be APPROVE or REJECT")
    _persist_governance(course)
    return jsonify(dict(course)), 200


@course_bp.patch("/api/admin/courses/<course_id>/visibility")
@require_role("ADMIN")
def set_course_visibility(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    body = _json()
    visible = body.get("visible")
    if not isinstance(visible, bool):
        raise ValidationError("'visible' must be boolean")
    if visible and course.get("status") != "PUBLISHED":
        raise Conflict("Only published courses can be visible")
    course["isVisible"] = visible
    _persist_governance(course)
    return jsonify(dict(course)), 200


@course_bp.delete("/api/admin/courses/<course_id>")
@require_role("ADMIN")
def archive_course(course_id: str) -> tuple[Response, int]:
    course = _course(course_id)
    course["status"], course["isVisible"] = "ARCHIVED", False
    _persist_governance(course)
    return jsonify({"id": course_id, "status": "ARCHIVED"}), 200
