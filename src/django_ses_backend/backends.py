import hashlib
import hmac
import json
import logging
import time
from datetime import UTC, datetime
from typing import Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("django_ses_backend.backends.")


class SESClientError(Exception):
    pass


class SESRateLimitError(SESClientError):
    pass


class SESClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        endpoint_url: Optional[str] = None,
        endpoint_path: Optional[str] = None,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.host = endpoint_url or f"email.{region}.amazonaws.com"
        self.path = endpoint_path or "/v2/email/outbound-emails"
        self.url = f"https://{self.host}{self.path}"
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _sign(self, key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signing_key(self, date_stamp: str) -> bytes:
        k_date = self._sign(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.region)
        k_service = self._sign(k_region, "ses")
        return self._sign(k_service, "aws4_request")

    def _signature(self, date_stamp: str, string_to_sign: str) -> str:
        k_signing = self._get_signing_key(date_stamp)
        return hmac.new(
            k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    def _get_canonical_headers(self, amz_date: str) -> str:
        return (
            f"content-type:application/json\nhost:{self.host}\nx-amz-date:{amz_date}\n"
        )

    def _get_payload_hash(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload).encode("utf-8")).hexdigest()

    def _canonical_request(self, canonical_headers: str, payload_hash: str) -> str:
        canonical_request = f"POST\n{self.path}\n\n{canonical_headers}\ncontent-type;host;x-amz-date\n{payload_hash}"
        return hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()

    def _get_credential_scope(self, date_stamp: str) -> str:
        return f"{date_stamp}/{self.region}/ses/aws4_request"

    def _get_string_to_sign(
        self, algorithm: str, amz_date: str, credential_scope: str, hashed_request: str
    ) -> str:
        return f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashed_request}"

    def _authorization_headers(
        self, amz_date: str, date_stamp: str, payload: dict
    ) -> str:
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = self._get_credential_scope(date_stamp)
        canonical_headers = self._get_canonical_headers(amz_date)
        payload_hash = self._get_payload_hash(payload)
        hashed_request = self._canonical_request(canonical_headers, payload_hash)
        string_to_sign = self._get_string_to_sign(
            algorithm, amz_date, credential_scope, hashed_request
        )
        signature = self._signature(date_stamp, string_to_sign)
        return (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders=content-type;host;x-amz-date, Signature={signature}"
        )

    def _get_timestamp_data(self) -> Tuple[str, str]:
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        return amz_date, date_stamp

    def _headers(self, data: dict) -> dict:
        amz_date, date_stamp = self._get_timestamp_data()
        return {
            "Content-Type": "application/json",
            "X-Amz-Date": amz_date,
            "Authorization": self._authorization_headers(amz_date, date_stamp, data),
        }

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        if attempt >= self.max_retries:
            return False
        return status_code in [429, 500, 502, 503, 504]

    def _get_retry_delay(self, attempt: int) -> float:
        return self.retry_delay * (2**attempt)

    def _post(self, data: dict) -> dict:
        logger.debug(f"SESClient._post: {self.url}")

        for attempt in range(self.max_retries + 1):
            try:
                req = Request(
                    self.url,
                    data=json.dumps(data).encode("utf-8"),
                    headers=self._headers(data),
                )
                return self._handle_response(req, attempt)
            except SESRateLimitError:
                if attempt < self.max_retries:
                    delay = self._get_retry_delay(attempt)
                    logger.warning(
                        f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    time.sleep(delay)
                    continue
                raise
            except URLError as e:
                logger.exception(f"SESClient._post: URLError {e}")
                raise SESClientError(f"Failed to connect to SES: {e}") from e
            except json.JSONDecodeError as e:
                logger.exception(f"SESClient._post: JSONDecodeError {e}")
                raise SESClientError(f"Failed to parse SES response: {e}") from e
            except Exception as e:
                logger.exception(f"SESClient._post: Unexpected error {e}")
                raise SESClientError(f"Unexpected error when sending email: {e}") from e

    def _handle_response(self, req: Request, attempt: int) -> dict:
        with urlopen(req, timeout=self.timeout) as res:
            body = res.read().decode("utf-8")

            if res.status == 429:
                raise SESRateLimitError(f"Rate limit exceeded: {body}")

            if res.status >= 500 and self._should_retry(res.status, attempt):
                raise SESClientError(f"Server error {res.status}, retrying: {body}")

            if res.status >= 400:
                logger.error(f"SES error {res.status}: {body}")
                raise SESClientError(f"SES request failed: {res.status} {body}")

            return json.loads(body)

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

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

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
            logger.exception(
                f"SESEmailBackend.open: Failed to open SES connection: {e}"
            )
            if not self.fail_silently:
                raise
        return False

    def close(self) -> None:
        self.connection = None

    def _build_destination(self, email_message: EmailMessage) -> Dict[str, List[str]]:
        destination = {"ToAddresses": email_message.to or []}
        if email_message.cc:
            destination["CcAddresses"] = email_message.cc
        if email_message.bcc:
            destination["BccAddresses"] = email_message.bcc
        return destination

    def _extract_alternatives(
        self, email_message: EmailMessage
    ) -> Tuple[Optional[str], Optional[str]]:
        text_content = None
        html_content = None

        if isinstance(email_message, EmailMultiAlternatives):
            for content, content_type in email_message.alternatives:
                if content_type == "text/html":
                    html_content = content
                elif content_type == "text/plain":
                    text_content = content

        if email_message.body:
            if email_message.content_subtype == "html":
                html_content = html_content or email_message.body
                # This is here for backward compatibility
                text_content = text_content or email_message.body 
            else:
                text_content = text_content or email_message.body

        return text_content, html_content

    def _build_content_body(
        self, email_message: EmailMessage
    ) -> Dict[str, Dict[str, str]]:
        body: Dict[str, Dict[str, str]] = {}
        text_content, html_content = self._extract_alternatives(email_message)

        if text_content:
            body["Text"] = {"Data": text_content}
        if html_content:
            body["Html"] = {"Data": html_content}

        return body

    def _check_attachments(self, email_message: EmailMessage) -> None:
        if hasattr(email_message, "attachments") and email_message.attachments:
            logger.warning(
                f"Email to {email_message.to} contains {len(email_message.attachments)} attachment(s) which will be ignored"
            )

    def _msg_to_data(self, email_message: EmailMessage) -> dict:
        self._check_attachments(email_message)

        data = {
            "FromEmailAddress": email_message.from_email,
            "Destination": self._build_destination(email_message),
            "Content": {
                "Simple": {
                    "Subject": {"Data": email_message.subject},
                    "Body": self._build_content_body(email_message),
                }
            },
        }

        headers = []
        if email_message.reply_to:
            for addr in email_message.reply_to:
                headers.append({"Name": "Reply-To", "Value": addr})
        if email_message.extra_headers:
            for name, value in email_message.extra_headers.items():
                headers.append({"Name": name, "Value": value})
        if headers:
            data["EmailHeaders"] = headers

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
