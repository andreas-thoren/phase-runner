"""Development settings — SQLite, DEBUG=True, console email."""

from .base import *  # noqa: F401, F403

SECRET_KEY = "django-insecure-@_#8)l38twrta2z@9+6dqi#=q53r4^3bxi+s2fc(i!9%e=&(ls"

DEBUG = True

ALLOWED_HOSTS = ["*"]  # Allow all hosts in development

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
