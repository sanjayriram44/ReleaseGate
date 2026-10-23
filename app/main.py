from typing import Any

from fastapi import FastAPI

from app.clock import Clock
from app.config import Settings
from app.db import Database
from app.errors import install_error_handlers
from app.harness import build_router as build_harness_router
from app.routers import audit, health, releases, sbom, test_support
from tester.harness import CollapseSlashes


def _require_user_id_in_schema(app: FastAPI) -> None:
    """X-User-Id is enforced by our own dependency (to return 400, not 422); declare it
    as required in the generated OpenAPI so it matches the shared contract."""
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original()  # FastAPI caches this same dict in app.openapi_schema
        for item in schema["paths"].values():
            for op in item.values():
                for param in op.get("parameters", []):
                    if param.get("name") == "X-User-Id":
                        param["required"] = True
                        param["schema"] = {"type": "string", "minLength": 1}
        return schema

    app.openapi = openapi  # type: ignore[method-assign]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="CRA Vulnerability Response Service", version="1.0.0")
    app.state.settings = settings
    app.state.clock = Clock()
    app.state.db = Database(settings.db_path)
    app.state.db.init_schema()
    app.add_middleware(CollapseSlashes)
    install_error_handlers(app)
    _require_user_id_in_schema(app)
    app.include_router(health.router)
    app.include_router(releases.router)
    app.include_router(sbom.router)
    app.include_router(audit.router)
    if settings.enable_test_endpoints:
        app.include_router(test_support.router)
        app.include_router(build_harness_router(app))
    return app
