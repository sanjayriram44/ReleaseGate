from typing import Any

from fastapi import FastAPI

from app.clock import Clock
from app.config import Settings
from app.db import Database
from app.errors import install_error_handlers
from app.harness import build_router as build_harness_router
from app.routers import audit, health, releases, sbom, test_support
from tester.harness import CollapseSlashes


def _align_schema_with_contract(app: FastAPI) -> None:
    """Make the generated OpenAPI say what the app does, as the shared contract does.

    X-User-Id is enforced by our own dependency (to return 400, not 422), so declare it as
    required. Invalid input is 400 with the shared Error shape, so drop FastAPI's default 422
    responses and their HTTPValidationError/ValidationError schemas.
    """
    original = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = original()  # FastAPI caches this same dict in app.openapi_schema
        for item in schema["paths"].values():
            for op in item.values():
                op.get("responses", {}).pop("422", None)
                for param in op.get("parameters", []):
                    if param.get("name") == "X-User-Id":
                        param["required"] = True
                        param["schema"] = {"type": "string", "minLength": 1}
        schemas = schema.get("components", {}).get("schemas", {})
        for name in ("HTTPValidationError", "ValidationError"):
            schemas.pop(name, None)
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
    _align_schema_with_contract(app)
    app.include_router(health.router)
    app.include_router(releases.router)
    app.include_router(sbom.router)
    app.include_router(audit.router)
    if settings.enable_test_endpoints:
        app.include_router(test_support.router)
        app.include_router(build_harness_router(app))
    return app
