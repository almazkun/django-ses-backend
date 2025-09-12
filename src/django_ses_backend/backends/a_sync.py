import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch, MagicMock

from django.core.mail import EmailMessage

from src.django_ses_backend import AsyncSESClient, AsyncSESEmailBackend
from src.django_ses_backend.exceptions import (
    SESClientError,
    SESRateLimitError,
    SESRetryableClientError,
)


class AsyncSESClientResponseTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncSESClient("k", "s", "us-east-1")
        self.client._session = AsyncMock()

    async def test_handle_response_success(self):
        response = AsyncMock()
        response.status = 200
        response.text.return_value = json.dumps({"ok": True})
        self.client._session.post.return_value.__aenter__.return_value = response

        result = await self.client._handle_response(b"{}", {}, 0)
        self.assertEqual(result, {"ok": True})

    async def test_handle_response_rate_limit(self):
        response = AsyncMock()
        response.status = 429
        response.text.return_value = "too many"
        self.client._session.post.return_value.__aenter__.return_value = response

        with self.assertRaises(SESRateLimitError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_retryable(self):
        response = AsyncMock()
        response.status = 500
        response.text.return_value = "server down"
        self.client._session.post.return_value.__aenter__.return_value = response
        self.client._should_retry = MagicMock(return_value=True)

        with self.assertRaises(SESRetryableClientError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_non_retryable(self):
        response = AsyncMock()
        response.status = 500
        response.text.return_value = "server error"
        self.client._session.post.return_value.__aenter__.return_value = response
        self.client._should_retry = MagicMock(return_value=False)

        with self.assertRaises(SESClientError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_bad_json(self):
        response = AsyncMock()
        response.status = 200
        response.text.return_value = "not-json"
        self.client._session.post.return_value.__aenter__.return_value = response

        with patch("json.loads", side_effect=json.JSONDecodeError("x","y",0)):
            with self.assertRaises(json.JSONDecodeError):
                await self.client._handle_response(b"{}", {}, 0)


class AsyncSESEmailBackendFailureTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = AsyncSESEmailBackend("k", "s", "us-east-1")

    async def test_send_messages_fail_silently_false(self):
        email = EmailMessage("x", "b", "from@example.com", ["to@example.com"])
        mock_client = AsyncMock()
        mock_client.send_email.side_effect = SESClientError("boom")

        self.backend.connection = mock_client
        self.backend.fail_silently = False

        with self.assertRaises(SESClientError):
            await self.backend.send_messages([email])

    async def test_send_no_recipients_logs(self):
        email = EmailMessage("x", "b", "from@example.com", [])
        mock_client = AsyncMock()
        self.backend.connection = mock_client

        result = await self.backend._send(email)
        self.assertFalse(result)
