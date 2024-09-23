# django-ses-backend
Django AWS SES (Amazon Simple Email Service) email backend. 

# Features
- Send email using AWS SES
- No need to install boto3 or any other AWS SDK
- No need to configure SMTP settings
- Minimal configuration

# Installation
```bash
pip install django-ses-backend
```
```python
# settings.py
EMAIL_BACKEND = 'django_ses_backend.backends.SESEmailBackend'

SES_ACCESS_KEY_ID='YOUR_AWS_ACCESS_KEY_ID'
SES_SECRET_ACCESS_KEY='YOUR_AWS_SECRET_ACCESS_KEY'
SES_AWS_REGION='YOUR_AWS_REGION'
```
