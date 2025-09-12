import logging
from typing import List, Optional
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from ..client import SESClient
from ..exceptions import SESClientError
from ..converters import msg_to_data
from .base import BaseSESBackend

logger = logging.getLogger("django_ses_backend.backends.sync")


class SESEmailBackend(BaseEmailBackend, BaseSESBackend):
    def __init__(
        self,
        fail_silently: bool = False,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        **kwargs,
    ):
        BaseEmailBackend.__init__(self, fail_silently=fail_silently, **kwargs)
        BaseSESBackend.__init__(self, fail_silently, access_key, secret_key, region)
        self.connection: Optional[SESClient] = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def _send(self, email_message: EmailMessage) -> bool:
        if not email_message.recipients():
            logger.warning("Skipping email with no recipients")
            return False

        self._check_attachments(email_message)
        data = msg_to_data(email_message)
        try:
            logger.info(
                f"Sending email to {email_message.to} with subject '{email_message.subject}'"
            )
            self.connection.send_email(data)
            return True
        except SESClientError as e:
            logger.error(f"Failed to send email: {e}")
            if not self.fail_silently:
                raise
        return False

    def open(self) -> bool:
        if self.connection is not None:
            return False
        try:
            self.connection = SESClient(
                access_key=self.access_key,
                secret_key=self.secret_key,
                region=self.region,
                endpoint_url=self.endpoint_url,
                endpoint_path=self.endpoint_path,
                timeout=self.timeout,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
            )
            return True
        except Exception as e:
            logger.exception(f"SESEmailBackend.open: Failed to open SES connection: {e}")
            if not self.fail_silently:
                raise
        return False

    def close(self) -> None:
        self.connection = None

    def send_messages(self, email_messages: List[EmailMessage]) -> int:
        if not email_messages:
            return 0

        new_conn_created = self.open()
        if not self.connection:
            return 0

        num_sent = 0
        try:
            for message in email_messages:
                if self._send(message):
                    num_sent += 1
        finally:
            if new_conn_created:
                self.close()
        return num_sent