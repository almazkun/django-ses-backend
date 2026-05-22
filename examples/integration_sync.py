import os

import django
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from django_ses_backend import SESEmailBackend

settings.configure(
    DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
    INSTALLED_APPS=[
        "django.contrib.contenttypes",
        "django.contrib.auth",
    ],
    SECRET_KEY="not-secret",
    SENDER_EMAIL=os.getenv("SENDER_EMAIL"),
    RECIPIENT_EMAIL=os.getenv("RECIPIENT_EMAIL"),
    SES_AWS_ACCESS_KEY_ID=os.getenv("SES_AWS_ACCESS_KEY_ID"),
    SES_AWS_SECRET_ACCESS_KEY=os.getenv("SES_AWS_SECRET_ACCESS_KEY"),
    SES_AWS_REGION=os.getenv("SES_AWS_REGION"),
    SES_ENDPOINT_URL=None,
    SES_ENDPOINT_PATH=None,
    SES_TIMEOUT=10,
    SES_MAX_RETRIES=3,
    SES_RETRY_DELAY=1.0,
    LOGGING={
        "version": 1,
        "disable_existing_loggers": False,
        "handlers": {"console": {"class": "logging.StreamHandler"}},
        "root": {"handlers": ["console"], "level": "DEBUG"},
    },
)

django.setup()


def test_send_email():
    backend = SESEmailBackend(fail_silently=False)

    subject = "Integration Email"
    body = "Plain text body."
    html_body = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Dear Reader</title>
    <style>
      body { font-family: 'Open Sans', sans-serif; font-size: 16px; color: #333; }
      h1 { color: #1a73e8; }
      p { line-height: 1.5; }
      a { color: #1a73e8; text-decoration: none; }
    </style>
  </head>
  <body>
    <h1>Hello!</h1>
    <p>This is a minimal HTML email body that needs to look wonderful.</p>
  </body>
</html>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.SENDER_EMAIL,
        to=[settings.RECIPIENT_EMAIL],
    )
    msg.attach_alternative(html_body, "text/html")

    sent = backend.send_messages([msg])
    print(f"Sent {sent} email(s)")


if __name__ == "__main__":
    test_send_email()
