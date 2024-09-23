import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import List, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("django_ses_backend.backends")


class SESClientError(Exception):
    """Custom exception for SES client errors."""

    pass


class SESClient:
    """Non Boto3 SES client for sending emails using Amazon SES.

    For direct interaction with AWS V2 API:
    https://docs.aws.amazon.com/ses/latest/APIReference-V2/API_SendEmail.html
    """

    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.host = f"email.{region}.amazonaws.com"
        self.path = "/v2/email/outbound-emails"
        self.url = f"https://{self.host}{self.path}"

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _signature(self, date_stamp: str, string_to_sign: str) -> str:
        k_date = self._sign(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, "ses")
        k_signing = self._sign(k_service, "aws4_request")
        return hmac.new(
            k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _canonical_request(self, canonical_headers: str, payload_hash: str) -> str:
        canonical_request = f"POST\n{self.path}\n\n{canonical_headers}\ncontent-type;host;x-amz-date\n{payload_hash}"
        return hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()

    def _authorization_headers(
        self, amz_date: str, date_stamp: str, payload: dict
    ) -> str:
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/ses/aws4_request"
        canonical_headers = (
            f"content-type:application/json\nhost:{self.host}\nx-amz-date:{amz_date}\n"
        )
        payload_hash = hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{self._canonical_request(canonical_headers, payload_hash)}"
        return f"{algorithm} Credential={self.access_key}/{credential_scope}, SignedHeaders=content-type;host;x-amz-date, Signature={self._signature(date_stamp, string_to_sign)}"

    def _headers(self, data: dict) -> dict:
        amz_date = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        date_stamp = datetime.now(UTC).strftime("%Y%m%d")
        return {
            "Content-Type": "application/json",
            "X-Amz-Date": amz_date,
            "Authorization": self._authorization_headers(amz_date, date_stamp, data),
        }

    def _post(self, data: dict) -> dict:
        logger.debug(f"SESClient._post: {self.url}")
        try:
            req = Request(
                self.url,
                data=json.dumps(data).encode("utf-8"),
                headers=self._headers(data),
            )
            with urlopen(req, timeout=10) as res:
                logger.debug(f"SESClient._post: response status {res.status}")
                return json.loads(res.read().decode("utf-8"))
        except URLError as e:
            logger.exception(f"URLError in SESClient._post: {e}")
            raise SESClientError(f"Failed to connect to SES: {e}") from e
        except json.JSONDecodeError as e:
            logger.exception(f"JSONDecodeError in SESClient._post: {e}")
            raise SESClientError(f"Failed to parse SES response: {e}") from e
        except Exception as e:
            logger.exception(f"Unexpected error in SESClient._post: {e}")
            raise SESClientError(f"Unexpected error when sending email: {e}") from e

    def send_email(self, data: dict) -> dict:
        return self._post(data)


class SESEmailBackend(BaseEmailBackend):
    def __init__(
        self,
        fail_silently: bool = False,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.connection: Optional[SESClient] = None
        self.access_key = access_key or getattr(settings, "SES_AWS_ACCESS_KEY_ID", None)
        self.secret_key = secret_key or getattr(
            settings, "SES_AWS_SECRET_ACCESS_KEY", None
        )
        self.region = region or getattr(settings, "SES_AWS_REGION", None)

        if not all([self.access_key, self.secret_key, self.region]):
            raise ValueError(
                "Missing SES configuration. Please provide SES_AWS_ACCESS_KEY_ID, SES_AWS_SECRET_ACCESS_KEY, and SES_AWS_REGION in settings.py"
            )

    def open(self) -> bool:
        if self.connection:
            return False
        try:
            self.connection = SESClient(
                access_key=self.access_key,
                secret_key=self.secret_key,
                region=self.region,
            )
            return True
        except Exception as e:
            logger.exception(f"Failed to open SES connection: {e}")
            if not self.fail_silently:
                raise
        return False

    def close(self) -> None:
        self.connection = None

    def _msg_to_data(self, email_message: EmailMessage) -> dict:
        data = {
            "FromEmailAddress": email_message.from_email,
            "Destination": {"ToAddresses": email_message.to},
            "Content": {
                "Simple": {
                    "Subject": {"Data": email_message.subject},
                    "Body": {},
                }
            },
        }
        if email_message.body:
            data["Content"]["Simple"]["Body"]["Text"] = {"Data": email_message.body}
        if email_message.content_subtype == "html":
            data["Content"]["Simple"]["Body"]["Html"] = {"Data": email_message.body}
        return data

    def _send(self, email_message: EmailMessage) -> bool:
        if not email_message.recipients():
            logger.warning("Skipping email with no recipients")
            return False
        data = self._msg_to_data(email_message)
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
