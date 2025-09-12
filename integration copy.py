import asyncio
import django
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from src.django_ses_backend.backends.a_sync import AsyncSESEmailBackend
import os

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


async def test_send_single_email():
    backend = AsyncSESEmailBackend(fail_silently=False)

    subject = "Async Integration Email"
    body = "Plain text body sent asynchronously."
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
    <h1>Hello Async World!</h1>
    <p>This is a minimal HTML email body sent asynchronously.</p>
  </body>
</html>"""

    msg = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.SENDER_EMAIL,
        to=[settings.RECIPIENT_EMAIL],
    )
    msg.attach_alternative(html_body, "text/html")

    sent = await backend.send_messages([msg])
    print(f"Sent {sent} email(s)")


async def test_send_multiple_emails():
    backend = AsyncSESEmailBackend(fail_silently=False)

    messages = []
    for i in range(5):
        subject = f"Async Email #{i + 1}"
        body = f"This is async email number {i + 1}."
        html_body = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8">
    <title>Email #{i + 1}</title>
    <style>
      body {{ font-family: 'Arial', sans-serif; font-size: 14px; color: #444; }}
      h2 {{ color: #2196f3; }}
    </style>
  </head>
  <body>
    <h2>Concurrent Email #{i + 1}</h2>
    <p>This email was sent concurrently with others!</p>
  </body>
</html>"""

        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.SENDER_EMAIL,
            to=[settings.RECIPIENT_EMAIL],
        )
        msg.attach_alternative(html_body, "text/html")
        messages.append(msg)

    sent = await backend.send_messages(messages)
    print(f"Sent {sent} out of {len(messages)} emails concurrently")


async def test_with_context_manager():
    async with AsyncSESEmailBackend(fail_silently=False) as backend:
        msg = EmailMultiAlternatives(
            subject="Context Manager Test",
            body="Testing async context manager.",
            from_email=settings.SENDER_EMAIL,
            to=[settings.RECIPIENT_EMAIL],
        )
        
        sent = await backend.send_messages([msg])
        print(f"Sent {sent} email(s) using context manager")


async def test_performance_comparison():
    import time
    
    messages = []
    for i in range(10):
        msg = EmailMultiAlternatives(
            subject=f"Performance Test #{i + 1}",
            body=f"Performance test email {i + 1}",
            from_email=settings.SENDER_EMAIL,
            to=[settings.RECIPIENT_EMAIL],
        )
        messages.append(msg)

    backend = AsyncSESEmailBackend(fail_silently=False)
    
    start_time = time.time()
    sent = await backend.send_messages(messages)
    end_time = time.time()
    
    print(f"Sent {sent} emails in {end_time - start_time:.2f} seconds (async concurrent)")


async def main():
    print("Testing Async SES Email Backend")
    print("=" * 40)
    
    print("\n1. Single Email Test:")
    await test_send_single_email()
    
    #print("\n2. Multiple Emails Test:")
    #await test_send_multiple_emails()
    
    #print("\n3. Context Manager Test:")
    #await test_with_context_manager()
    
    #print("\n4. Performance Test:")
    #await test_performance_comparison()


if __name__ == "__main__":
    asyncio.run(main())