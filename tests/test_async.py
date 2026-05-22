import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch, MagicMock, call

from django.core.mail import EmailMessage

from src.django_ses_backend import AsyncSESClient, AsyncSESEmailBackend
from src.django_ses_backend.exceptions import (
    SESClientError,
    SESRateLimitError,
    SESRetryableClientError,
)


class AsyncSESClientResponseTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncSESClient(access_key="k", secret_key="s", region="us-east-1")
        self.client._session = AsyncMock()

    async def test_handle_response_success(self):
        response = AsyncMock()
        response.status = 200
        response.text = AsyncMock(return_value=json.dumps({"ok": True}))

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = response
        mock_cm.__aexit__.return_value = None
        self.client._session.post = MagicMock(return_value=mock_cm)

        result = await self.client._handle_response(b"{}", {}, 0)
        self.assertEqual(result, {"ok": True})

    async def test_handle_response_rate_limit(self):
        response = AsyncMock()
        response.status = 429
        response.text.return_value = "too many"

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = response
        mock_cm.__aexit__.return_value = None
        self.client._session.post = MagicMock(return_value=mock_cm)

        with self.assertRaises(SESRateLimitError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_retryable(self):
        response = AsyncMock()
        response.status = 500
        response.text.return_value = "server down"

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = response
        mock_cm.__aexit__.return_value = None
        self.client._session.post = MagicMock(return_value=mock_cm)

        self.client._should_retry = MagicMock(return_value=True)

        with self.assertRaises(SESRetryableClientError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_non_retryable(self):
        response = AsyncMock()
        response.status = 500
        response.text.return_value = "server error"

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = response
        mock_cm.__aexit__.return_value = None
        self.client._session.post = MagicMock(return_value=mock_cm)

        self.client._should_retry = MagicMock(return_value=False)

        with self.assertRaises(SESClientError):
            await self.client._handle_response(b"{}", {}, 0)

    async def test_handle_response_bad_json(self):
        response = AsyncMock()
        response.status = 200
        response.text.return_value = "not-json"

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = response
        mock_cm.__aexit__.return_value = None
        self.client._session.post = MagicMock(return_value=mock_cm)

        with patch("json.loads", side_effect=json.JSONDecodeError("x", "y", 0)):
            with self.assertRaises(json.JSONDecodeError):
                await self.client._handle_response(b"{}", {}, 0)


class AsyncSESEmailBackendFailureTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = AsyncSESEmailBackend(
            access_key="k", secret_key="s", region="us-east-1"
        )

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

    async def test_send_logs_warning_for_attachments(self):
        email = EmailMessage("x", "b", "from@example.com", ["to@example.com"])
        email.attach("file.txt", b"data", "text/plain")
        self.backend.connection = AsyncMock()
        self.backend.connection.send_email.return_value = {"MessageId": "1"}

        with self.assertLogs("django_ses_backend.backends.base", level="WARNING") as cm:
            result = await self.backend._send(email)

        self.assertTrue(result)
        self.assertTrue(any("attachment" in line.lower() for line in cm.output))


class AsyncSESClientRetryTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = AsyncSESClient(access_key="k", secret_key="s", region="us-east-1")
        self.client._session = AsyncMock()
        self.client._sync_client = MagicMock()
        self.client._sync_client._get_payload_hash.return_value = "deadbeef"
        self.client._sync_client._headers.return_value = {"Authorization": "test"}
        self.client._sync_client._get_retry_delay.return_value = 0.0

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_post_retries_on_retryable_error_then_succeeds(self, mock_sleep):
        self.client._handle_response = AsyncMock(
            side_effect=[SESRetryableClientError("retry"), {"MessageId": "ok"}]
        )
        result = await self.client._post({"key": "val"})
        self.assertEqual(result, {"MessageId": "ok"})
        mock_sleep.assert_called_once_with(0.0)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_post_retries_on_rate_limit_then_succeeds(self, mock_sleep):
        self.client._handle_response = AsyncMock(
            side_effect=[SESRateLimitError("slow down"), {"MessageId": "ok"}]
        )
        result = await self.client._post({"key": "val"})
        self.assertEqual(result, {"MessageId": "ok"})
        mock_sleep.assert_called_once()

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_post_raises_after_exhausting_retries(self, mock_sleep):
        self.client.max_retries = 2
        self.client._handle_response = AsyncMock(
            side_effect=SESRetryableClientError("always fails")
        )
        with self.assertRaises(SESRetryableClientError):
            await self.client._post({"key": "val"})
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_post_exponential_backoff_delays(self, mock_sleep):
        self.client.max_retries = 2
        self.client._sync_client._get_retry_delay.side_effect = lambda attempt: float(
            attempt + 1
        )
        self.client._handle_response = AsyncMock(
            side_effect=SESRetryableClientError("fail")
        )
        with self.assertRaises(SESRetryableClientError):
            await self.client._post({"key": "val"})
        self.assertEqual(mock_sleep.call_args_list, [call(1.0), call(2.0)])

    async def test_post_json_decode_error_wrapped_as_ses_client_error(self):
        self.client._handle_response = AsyncMock(
            side_effect=json.JSONDecodeError("bad json", "doc", 0)
        )
        with self.assertRaises(SESClientError):
            await self.client._post({"key": "val"})

    async def test_post_unexpected_exception_wrapped_as_ses_client_error(self):
        self.client._handle_response = AsyncMock(side_effect=RuntimeError("surprise"))
        with self.assertRaises(SESClientError):
            await self.client._post({"key": "val"})


class AsyncSESClientContextManagerTest(IsolatedAsyncioTestCase):
    async def test_aenter_calls_open_and_returns_self(self):
        client = AsyncSESClient(access_key="k", secret_key="s", region="us-east-1")
        with (
            patch.object(client, "open", new_callable=AsyncMock) as mock_open,
            patch.object(client, "close", new_callable=AsyncMock),
        ):
            async with client as c:
                self.assertIs(c, client)
            mock_open.assert_called_once()

    async def test_aexit_calls_close(self):
        client = AsyncSESClient(access_key="k", secret_key="s", region="us-east-1")
        with (
            patch.object(client, "open", new_callable=AsyncMock),
            patch.object(client, "close", new_callable=AsyncMock) as mock_close,
        ):
            async with client:
                pass
            mock_close.assert_called_once()

    async def test_aexit_calls_close_on_exception(self):
        client = AsyncSESClient(access_key="k", secret_key="s", region="us-east-1")
        with (
            patch.object(client, "open", new_callable=AsyncMock),
            patch.object(client, "close", new_callable=AsyncMock) as mock_close,
        ):
            with self.assertRaises(ValueError):
                async with client:
                    raise ValueError("inner error")
            mock_close.assert_called_once()


class AsyncSESEmailBackendSendMessagesTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.backend = AsyncSESEmailBackend(
            access_key="k", secret_key="s", region="us-east-1"
        )
        self.mock_connection = AsyncMock()
        self.mock_connection.send_email.return_value = {"MessageId": "abc"}
        self.backend.connection = self.mock_connection

    async def test_send_messages_empty_returns_zero(self):
        self.assertEqual(await self.backend.send_messages([]), 0)

    async def test_send_messages_single_email(self):
        email = EmailMessage("s", "b", "from@e.com", ["to@e.com"])
        result = await self.backend.send_messages([email])
        self.assertEqual(result, 1)
        self.mock_connection.send_email.assert_called_once()

    async def test_send_messages_multiple_emails_all_succeed(self):
        emails = [
            EmailMessage("s", "b", "from@e.com", [f"to{i}@e.com"]) for i in range(5)
        ]
        result = await self.backend.send_messages(emails)
        self.assertEqual(result, 5)
        self.assertEqual(self.mock_connection.send_email.call_count, 5)

    async def test_send_messages_respects_concurrency_limit(self):
        # concurrency_limit=2 with 6 emails — all should still be sent
        self.backend.concurrency_limit = 2
        emails = [
            EmailMessage("s", "b", "from@e.com", [f"to{i}@e.com"]) for i in range(6)
        ]
        result = await self.backend.send_messages(emails)
        self.assertEqual(result, 6)

    async def test_send_messages_partial_failure_fail_silently(self):
        self.backend.fail_silently = True
        self.mock_connection.send_email.side_effect = [
            {"MessageId": "1"},
            SESClientError("boom"),
            {"MessageId": "3"},
        ]
        emails = [
            EmailMessage("s", "b", "from@e.com", [f"to{i}@e.com"]) for i in range(3)
        ]
        result = await self.backend.send_messages(emails)
        self.assertEqual(result, 2)

    async def test_send_messages_skips_no_recipient_emails(self):
        emails = [
            EmailMessage("s", "b", "from@e.com", []),
            EmailMessage("s", "b", "from@e.com", ["to@e.com"]),
        ]
        result = await self.backend.send_messages(emails)
        self.assertEqual(result, 1)
        self.mock_connection.send_email.assert_called_once()


class AsyncSESEmailBackendContextManagerTest(IsolatedAsyncioTestCase):
    async def test_aenter_calls_open_and_returns_self(self):
        backend = AsyncSESEmailBackend(
            access_key="k", secret_key="s", region="us-east-1"
        )
        with (
            patch.object(
                backend, "open", new_callable=AsyncMock, return_value=True
            ) as mock_open,
            patch.object(backend, "close", new_callable=AsyncMock),
        ):
            async with backend as b:
                self.assertIs(b, backend)
            mock_open.assert_called_once()

    async def test_aexit_calls_close(self):
        backend = AsyncSESEmailBackend(
            access_key="k", secret_key="s", region="us-east-1"
        )
        with (
            patch.object(backend, "open", new_callable=AsyncMock, return_value=True),
            patch.object(backend, "close", new_callable=AsyncMock) as mock_close,
        ):
            async with backend:
                pass
            mock_close.assert_called_once()

    async def test_aexit_calls_close_on_exception(self):
        backend = AsyncSESEmailBackend(
            access_key="k", secret_key="s", region="us-east-1"
        )
        with (
            patch.object(backend, "open", new_callable=AsyncMock, return_value=True),
            patch.object(backend, "close", new_callable=AsyncMock) as mock_close,
        ):
            with self.assertRaises(RuntimeError):
                async with backend:
                    raise RuntimeError("inner")
            mock_close.assert_called_once()
