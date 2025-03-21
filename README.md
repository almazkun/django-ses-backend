# django-ses-backend

Django AWS SES (Amazon Simple Email Service) email backend.

## Features
- Send emails via AWS SES without needing `boto3` or any other AWS SDK.
- No SMTP configuration required and faster email sending.
- Supports sending TXT and HTML emails.
- Lightweight and easy to integrate.
- Supports `EmailMessage` from Django's built-in mail framework.
- Custom SES client implementation for signing and sending requests.

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
3. Attach the policy **AmazonSESFullAccess** (or create a custom policy with `ses:SendEmail` permissions).
4. Save the **Access Key ID** and **Secret Access Key**.

## Configuration

Update your Django settings:

```python
# settings.py
EMAIL_BACKEND = 'django_ses_backend.backends.SESEmailBackend'

SES_AWS_ACCESS_KEY_ID = 'YOUR_AWS_ACCESS_KEY_ID'
SES_AWS_SECRET_ACCESS_KEY = 'YOUR_AWS_SECRET_ACCESS_KEY'
SES_AWS_REGION = 'YOUR_AWS_REGION'
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

## Advanced Features

### Sending HTML Emails

```python
email = EmailMessage(
    subject="HTML Email Test",
    body="<h1>Hello from AWS SES</h1>",
    from_email="your-email@example.com",
    to=["recipient@example.com"],
)
email.content_subtype = "html"
email.send()
```

## Error Handling

If sending an email fails, a `SESClientError` is raised. You can handle errors gracefully:

```python
try:
    email.send()
except Exception as e:
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
- Ensure your AWS SES account is verified and out of sandbox mode to send emails to unverified addresses.
- Configure AWS IAM policies to grant `ses:SendEmail` permissions to your credentials.

## Contributing
Feel free to submit issues or pull requests on GitHub to improve this package.

---

This documentation provides a clear, structured, and practical guide for using `django-ses-backend`. Let me know if you need any refinements!

