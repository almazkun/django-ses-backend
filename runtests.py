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
)

django.setup()

# Start the test suite now that the settings are configured.
call_command("test", "tests", verbosity=3)
