"""Django settings for the project."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY environment variable must be set (see .env.example).")

DEBUG = os.getenv("DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "telegram_bot",
    "reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_ENGINE = os.getenv("DATABASE_ENGINE", "postgresql")

if DATABASE_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_NAME", str(BASE_DIR / "db.sqlite3")),
        }
    }
else:
    _pg_required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT")
    _pg_missing = [v for v in _pg_required if not os.getenv(v)]
    if _pg_missing:
        raise ImproperlyConfigured(
            "PostgreSQL configuration incomplete. Missing env vars: "
            + ", ".join(_pg_missing)
            + ". See .env.example."
        )
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("POSTGRES_DB"),
            "USER": os.getenv("POSTGRES_USER"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD"),
            "HOST": os.getenv("POSTGRES_HOST"),
            "PORT": os.getenv("POSTGRES_PORT"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TELEGRAM_CHAT_IDS = os.getenv("ADMIN_TELEGRAM_CHAT_IDS", "")
# ID канала-источника расписания (где x5_fort_bot публикует расписание)
SCHEDULE_SOURCE_CHAT_ID = int(os.getenv("SCHEDULE_SOURCE_CHAT_ID", "0"))
ALLIANCE_BOT_USERNAME = os.getenv("ALLIANCE_BOT_USERNAME", "")
CLAN_CHAT_ID = os.getenv("CLAN_CHAT_ID")
if CLAN_CHAT_ID:
    CLAN_CHAT_ID = int(CLAN_CHAT_ID)
# Prefixes to ignore when mirroring from schedule source channel (case-insensitive)
SCHEDULE_MIRROR_IGNORE_PREFIXES = [
    p.strip()
    for p in os.getenv("SCHEDULE_MIRROR_IGNORE_PREFIXES", "test,тест,/refresh,/fix").split(",")
    if p.strip()
]

# ID темы (forum topic / message_thread_id) в целевой группе, куда зеркалировать расписание.
# Если не задан — публикация в общую тему (по умолчанию).
SCHEDULE_MIRROR_TARGET_THREAD_ID = os.getenv("SCHEDULE_MIRROR_TARGET_THREAD_ID")
if SCHEDULE_MIRROR_TARGET_THREAD_ID:
    SCHEDULE_MIRROR_TARGET_THREAD_ID = int(SCHEDULE_MIRROR_TARGET_THREAD_ID)

# Yandex Disk backup
YANDEX_DISK_TOKEN = os.getenv("YANDEX_DISK_TOKEN", "")
YANDEX_DISK_BACKUP_DIR = os.getenv("YANDEX_DISK_BACKUP_DIR", "/project-backups/backups")
BACKUP_ENCRYPTION_PASSPHRASE = os.getenv("BACKUP_ENCRYPTION_PASSPHRASE", "")

# Email
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "True").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")

CSRF_TRUSTED_ORIGINS = [
    host.strip()
    for host in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if host.strip()
]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_COOKIE_SECURE = os.getenv("CSRF_COOKIE_SECURE", "False").lower() in ("1", "true", "yes")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "False").lower() in ("1", "true", "yes")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
            "class": "core.logging_utils.RedactingFormatter",
        },
    },
    "filters": {
        "secret_redact": {
            "()": "core.logging_utils.RedactingFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
        "filters": ["secret_redact"],
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
            "filters": ["secret_redact"],
        },
    },
}
