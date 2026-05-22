import django
from django.conf import settings
from django.core.management import call_command

settings.configure(
    DATABASES={
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    },
    MIDDLEWARE_CLASSES=(
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
    ),
    SECRET_KEY="not-secret",
    LOGGING={
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"null": {"class": "logging.NullHandler"}},
        "loggers": {
            "django_ses_backend": {"handlers": ["null"], "propagate": False},
        },
    },
)

django.setup()

call_command("test", "tests", verbosity=3)
