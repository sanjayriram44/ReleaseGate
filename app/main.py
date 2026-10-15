from fastapi import FastAPI

from app.clock import Clock
from app.config import Settings
from app.db import Database
from app.errors import install_error_handlers
from app.routers import releases, sbom, test_support


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="CRA Vulnerability Response Service", version="1.0.0")
    app.state.settings = settings
    app.state.clock = Clock()
    app.state.db = Database(settings.db_path)
    app.state.db.init_schema()
    install_error_handlers(app)
    app.include_router(releases.router)
    app.include_router(sbom.router)
    if settings.enable_test_endpoints:
        app.include_router(test_support.router)
    return app
