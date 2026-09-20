"""Shared extension instances, created here (unbound) and initialized on the
app in app/__init__.py, so every module can import them without circular
imports."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "dashboard.login"
scheduler = BackgroundScheduler(daemon=True)
