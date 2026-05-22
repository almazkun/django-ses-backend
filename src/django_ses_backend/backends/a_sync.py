import asyncio
import json
import logging
from typing import List, Optional

from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

from .base import BaseSESBackend
from ..converters import msg_to_data
from ..client import SESClient
from ..exceptions import (
    SESClientError,
    SESRateLimitError,
    SESRetryableClientError,
)

try:
    import aiohttp
except ImportError as exc:
    raise ImportError(
        "aiohttp is required for async SES support. "
        "Install it with: pip install django-ses-backend[async]"
    ) from exc

logger = logging.getLogger("django_ses_backend.backends.async")


class AsyncSESClient:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        region: str,
        endpoint_url: Optional[str] = None,
        endpoint_path: Optional[str] = None,
        timeout: int = 10,
        connect_timeout: int = 5,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        connector_limit: int = 100,
        connector_limit_per_host: int = 10,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.endpoint_url = endpoint_url
        self.host = endpoint_url or f"email.{region}.amazonaws.com"
        self.path = endpoint_path or "/v2/email/outbound-emails"
        self.url = f"https://{self.host}{self.path}"
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.connector_limit = connector_limit
        self.connector_limit_per_host = connector_limit_per_host

        self._session: Optional[aiohttp.ClientSession] = None
        self._sync_client = None

    @property
    def sync_client(self):
        if self._sync_client is None:

            self._sync_client = SESClient(
                self.access_key,
                self.secret_key,
                self.region,
                self.endpoint_url,
                self.path,
                self.timeout,
                self.max_retries,
                self.retry_delay,
            )
        return self._sync_client

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    async def open(self):
        if self._session is None:
            connector = aiohttp.TCPConnector(
                limit=self.connector_limit,
                limit_per_host=self.connector_limit_per_host,
            )
            timeout = aiohttp.ClientTimeout(total=self.timeout, connect=self.connect_timeout)
            self._session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    def _should_retry(self, status_code: int, attempt: int) -> bool:
        return self.sync_client._should_retry(status_code, attempt)

    def _get_retry_delay(self, attempt: int) -> float:
        return self.sync_client._get_retry_delay(attempt)

    async def _post(self, data: dict) -> dict:
        if not self._session:
            await self.open()

        logger.debug(f"AsyncSESClient._post: {self.url}")
        encoded_data = json.dumps(data, sort_keys=True).encode("utf-8")
        payload_hash = self.sync_client._get_payload_hash(encoded_data)

        for attempt in range(self.max_retries + 1):
            try:
                headers = self.sync_client._headers(payload_hash)
                return await self._handle_response(encoded_data, headers, attempt)
            except (SESRetryableClientError, SESRateLimitError) as e:
                if attempt < self.max_retries:
                    delay = self._get_retry_delay(attempt)
                    logger.warning(
                        f"{e.__class__.__name__}, retrying in {delay}s (attempt {attempt + 1}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
            except aiohttp.ClientError as e:
                logger.exception(f"AsyncSESClient._post: ClientError {e}")
                raise SESClientError(f"Failed to connect to SES: {e}") from e
            except json.JSONDecodeError as e:
                logger.exception(f"AsyncSESClient._post: JSONDecodeError {e}")
                raise SESClientError(f"Failed to parse SES response: {e}") from e
            except SESClientError:
                raise
            except Exception as e:
                logger.exception(f"AsyncSESClient._post: Unexpected error {e}")
                raise SESClientError(f"Unexpected error when sending email: {e}") from e

    async def _handle_response(
        self, encoded_data: bytes, headers: dict, attempt: int
    ) -> dict:
        async with self._session.post(
            self.url, data=encoded_data, headers=headers
        ) as response:
            body = await response.text()

            if response.status == 429:
                raise SESRateLimitError(f"Rate limit exceeded: {body}")

            if response.status >= 500 or response.status == 408:
                if self._should_retry(response.status, attempt):
                    raise SESRetryableClientError(
                        f"Server error {response.status}, retrying: {body}"
                    )
                else:
                    raise SESClientError(f"Server error {response.status}: {body}")

            if response.status >= 400:
                logger.error(f"SES error {response.status}: {body}")
                raise SESClientError(f"SES request failed: {response.status} {body}")

            return json.loads(body)

    async def send_email(self, data: dict) -> dict:
        return await self._post(data)


class AsyncSESEmailBackend(BaseEmailBackend, BaseSESBackend):
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
        self.connection: Optional[AsyncSESClient] = None

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()

    async def _send(self, email_message: EmailMessage) -> bool:
        if not email_message.recipients():
            logger.warning("Skipping email with no recipients")
            return False

        self._check_attachments(email_message)
        data = msg_to_data(email_message)
        try:
            logger.info(
                f"Sending email to {email_message.to} with subject '{email_message.subject}'"
            )
            await self.connection.send_email(data)
            return True
        except SESClientError as e:
            logger.error(f"Failed to send email: {e}")
            if not self.fail_silently:
                raise
        return False

    async def open(self) -> bool:
        if self.connection is not None:
            return False
        try:
            self.connection = AsyncSESClient(
                access_key=self.access_key,
                secret_key=self.secret_key,
                region=self.region,
                endpoint_url=self.endpoint_url,
                endpoint_path=self.endpoint_path,
                timeout=self.timeout,
                connect_timeout=self.connect_timeout,
                max_retries=self.max_retries,
                retry_delay=self.retry_delay,
                connector_limit=self.connector_limit,
                connector_limit_per_host=self.connector_limit_per_host,
            )
            await self.connection.open()
            return True
        except Exception as e:
            logger.exception(
                f"AsyncSESEmailBackend.open: Failed to open SES connection: {e}"
            )
            if not self.fail_silently:
                raise
        return False

    async def close(self) -> None:
        if self.connection:
            await self.connection.close()
            self.connection = None

    async def send_messages(self, email_messages: List[EmailMessage]) -> int:
        if not email_messages:
            return 0

        new_conn_created = await self.open()
        if not self.connection:
            return 0

        semaphore = asyncio.Semaphore(self.concurrency_limit)

        async def _send_with_semaphore(message: EmailMessage) -> bool:
            async with semaphore:
                return await self._send(message)

        tasks: List[asyncio.Task] = []
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(_send_with_semaphore(m)) for m in email_messages
                ]
        except* SESClientError as eg:
            raise eg.exceptions[0]
        finally:
            if new_conn_created:
                await self.close()

        return sum(1 for t in tasks if t.result() is True)
