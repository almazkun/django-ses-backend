import logging
from typing import Optional
from django.conf import settings

logger = logging.getLogger("django_ses_backend.backends.base")


class BaseSESBackend:
    def __init__(
        self,
        fail_silently: bool = False,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        **kwargs,
    ):
        self.fail_silently = fail_silently
        self._load_configuration(access_key, secret_key, region)

    def _load_configuration(
        self,
        access_key: Optional[str],
        secret_key: Optional[str],
        region: Optional[str],
    ) -> None:
        self.access_key = access_key or getattr(settings, "SES_AWS_ACCESS_KEY_ID", None)
        self.secret_key = secret_key or getattr(
            settings, "SES_AWS_SECRET_ACCESS_KEY", None
        )
        self.region = region or getattr(settings, "SES_AWS_REGION", None)
        self.endpoint_url = getattr(settings, "SES_ENDPOINT_URL", None)
        self.endpoint_path = getattr(settings, "SES_ENDPOINT_PATH", None)
        self.timeout = getattr(settings, "SES_TIMEOUT", 10)
        self.max_retries = getattr(settings, "SES_MAX_RETRIES", 3)
        self.retry_delay = getattr(settings, "SES_RETRY_DELAY", 1.0)

        if not all([self.access_key, self.secret_key, self.region]):
            raise ValueError(
                "Missing SES configuration.\n"
                "Provide SES_AWS_ACCESS_KEY_ID, SES_AWS_SECRET_ACCESS_KEY, and SES_AWS_REGION"
            )

    def _check_attachments(self, email_message):
        if hasattr(email_message, "attachments") and email_message.attachments:
            logger.warning(
                f"Email to {email_message.to} contains {len(email_message.attachments)} attachment(s) which will be ignored"
            )