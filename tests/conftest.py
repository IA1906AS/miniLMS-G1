"""Global pytest configuration and compatibility aliasing."""

from __future__ import annotations

import sys

import lms_project_1
from lms_project_1 import (
    audit,
    auth,
    database,
    errors,
    gate,
    guards,
    models,
    schemas,
    services,
    store,
)

# Alias `app` package namespace in memory for any legacy test referencing `app`
sys.modules.setdefault("app", lms_project_1)
sys.modules.setdefault("app.audit", audit)
sys.modules.setdefault("app.auth", auth)
sys.modules.setdefault("app.database", database)
sys.modules.setdefault("app.errors", errors)
sys.modules.setdefault("app.gate", gate)
sys.modules.setdefault("app.guards", guards)
sys.modules.setdefault("app.models", models)
sys.modules.setdefault("app.schemas", schemas)
sys.modules.setdefault("app.services", services)
sys.modules.setdefault("app.store", store)
