# django-ses-backend

Django AWS SES (Amazon Simple Email Service) email backend.

## Features
- Send emails via AWS SES without needing `boto3` or any other AWS SDK.
- No SMTP configuration required and faster email sending.
- Supports sending plain text and HTML emails, including multi-part messages.
- Lightweight and easy to integrate.
- Supports Django's `EmailMessage` and `EmailMultiAlternatives`.
- Handles `Reply-To` and custom headers.
- Custom SES client implementation with AWS signature v4, rate-limit retries, and exponential backoff.
- Context manager support for use with `with SESEmailBackend() as connection:`.

## Requirements
- Python 3.11+
- Django 4.2+

## Installation

Install the package using pip:

```bash
pip install django-ses-backend
```

## AWS Setup

### Step 1: Create an AWS SES Account

1. Sign in to the [AWS Management Console](https://aws.amazon.com/console/).
2. Navigate to **Amazon SES** service.
3. Verify your email address or domain in the **Verified Identities** section.
4. Move your SES account out of **Sandbox Mode** (if needed) by requesting production access.

### Step 2: Create an IAM User for SES

1. Go to **IAM** in the AWS Console.
2. Create a new user and enable **Programmatic access**.
3. Attach the policy **AmazonSESFullAccess** (or a custom policy with `ses:SendEmail` permissions).
4. Save the **Access Key ID** and **Secret Access Key**.

## Configuration

Update your Django settings:

```python
# settings.py
EMAIL_BACKEND = 'django_ses_backend.backends.SESEmailBackend'

SES_AWS_ACCESS_KEY_ID = 'YOUR_AWS_ACCESS_KEY_ID'
SES_AWS_SECRET_ACCESS_KEY = 'YOUR_AWS_SECRET_ACCESS_KEY'
SES_AWS_REGION = 'YOUR_AWS_REGION'

# Optional advanced settings
SES_ENDPOINT_URL = None           # Custom endpoint URL
SES_ENDPOINT_PATH = None          # Custom endpoint path
SES_TIMEOUT = 10                  # HTTP request timeout in seconds
SES_MAX_RETRIES = 3               # Max retry attempts for rate-limits/server errors
SES_RETRY_DELAY = 1.0             # Base delay (seconds) for exponential backoff
```

## Usage

You can send emails using Django's built-in `send_mail` or `EmailMessage`:

```python
from django.core.mail import send_mail

send_mail(
    subject="Hello from AWS SES",
    message="This is a test email.",
    from_email="your-email@example.com",
    recipient_list=["recipient@example.com"],
)
```

Or using `EmailMessage` for more customization:

```python
from django.core.mail import EmailMessage

email = EmailMessage(
    subject="Hello from AWS SES",
    body="This is a test email.",
    from_email="your-email@example.com",
    to=["recipient@example.com"],
)
email.send()
```

### Sending HTML Emails

Supports both HTML and text content:

```python
from django.core.mail import EmailMultiAlternatives

email = EmailMultiAlternatives(
    subject="HTML Email Test",
    body="Fallback plain text content",
    from_email="your-email@example.com",
    to=["recipient@example.com"],
)
email.attach_alternative("<h1>Hello from AWS SES</h1>", "text/html")
email.send()
```

### Handling Reply-To and Custom Headers

```python
email = EmailMessage(
    subject="Email with Reply-To",
    body="Hello",
    from_email="your-email@example.com",
    to=["recipient@example.com"],
    reply_to=["replyto@example.com"],
    headers={"Message-ID": "<custom.id@example.com>"},
)
email.send()
```

## Error Handling

* `SESClientError` is raised for generic sending failures.
* `SESRatelimitError` is raised when AWS rate-limits are hit.
* Retries are performed automatically with exponential backoff for 429/5xx errors.

```python
try:
    email.send()
except SESClientError as e:
    print(f"Failed to send email: {e}")
```

## Logging

Enable logging to track email sending:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("django_ses_backend")
```

## Notes

* Always include both text and HTML versions for best deliverability.
* Attachments are ignored by this backend.
* Ensure your AWS SES account is verified and out of sandbox mode.
* Configure AWS IAM policies to grant `ses:SendEmail` permissions.

## Contributing

Feel free to submit issues or pull requests on GitHub to improve this package.
