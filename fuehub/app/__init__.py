from __future__ import annotations

from pathlib import Path

from flask import Flask

from app.config import Config
from app.extensions import db, login_manager, scheduler


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    Path(app.config["UPLOAD_DIR"]).mkdir(parents=True, exist_ok=True)
    _ensure_sqlite_dir(app.config["SQLALCHEMY_DATABASE_URI"])

    db.init_app(app)
    login_manager.init_app(app)

    from app.models import StaffUser

    @login_manager.user_loader
    def load_user(user_id: str):
        return StaffUser.query.get(int(user_id))

    from app.dashboard import dashboard_bp
    from app.webhooks import webhooks_bp

    app.register_blueprint(webhooks_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        # create_all(), not a migration tool -- fine for a single-clinic
        # MVP; a second clinic/production deployment should move to
        # Alembic before the schema needs to evolve under live data.
        db.create_all()

    if app.config.get("SCHEDULER_ENABLED") and not scheduler.running:
        from app.scheduler_jobs import register_jobs

        register_jobs(app)
        scheduler.start()

    return app


def _ensure_sqlite_dir(uri: str) -> None:
    prefix = "sqlite:///"
    if not uri.startswith(prefix):
        return
    path = uri[len(prefix):]
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
