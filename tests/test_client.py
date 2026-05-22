import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from django.test import TestCase


from src.django_ses_backend.client import SESClient
from src.django_ses_backend.exceptions import SESClientError


class TestSESClientErrors(TestCase):
    def setUp(self):
        self.client = SESClient(
            "key", "secret", "us-west-2", max_retries=2, retry_delay=0
        )

    @patch("src.django_ses_backend.client.urlopen")
    def test_rate_limit_error_429(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.read.return_value = b'{"error": "rate limit"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.client.urlopen")
    def test_retryable_errors_500_502_503_504_408(self, mock_urlopen):
        statuses = [500, 502, 503, 504, 408]
        for status in statuses:
            with self.subTest(status=status):
                mock_resp = MagicMock()
                mock_resp.status = status
                mock_resp.read.return_value = b'{"error": "server"}'
                mock_urlopen.return_value.__enter__.return_value = mock_resp

                with self.assertRaises(SESClientError):
                    self.client._post({"data": "x"})

    @patch("src.django_ses_backend.client.urlopen")
    def test_non_retryable_client_error_400(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b'{"error": "bad request"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.client.urlopen")
    def test_url_error_raises_client_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Failed connection")
        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.client.urlopen")
    def test_json_decode_error_raises_client_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"invalid json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})


class TestSESClient(TestCase):
    def setUp(self):
        self.client = SESClient("test_access_key", "test_secret_key", "us-west-2")

    def test_sign_and_keys(self):
        key = b"key"
        msg = "msg"
        signature = self.client._sign(key, msg)
        self.assertIsInstance(signature, bytes)
        self.assertIsInstance(self.client._get_signing_key("20240101"), bytes)
        self.assertIsInstance(self.client._signature("20240101", "string"), str)

    def test_headers_and_hash(self):
        payload = {"test": "data"}
        encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
        payload_hash = self.client._get_payload_hash(encoded)
        self.assertEqual(len(payload_hash), 64)
        headers = self.client._canonical_headers_template.format(
            amz_date="20240101T120000Z"
        )
        self.assertIn("content-type:application/json", headers)

    def test_canonical_request_and_scope(self):
        cr = self.client._canonical_request("headers", "hash")
        self.assertEqual(len(cr), 64)
        scope = self.client._get_credential_scope("20240101")
        self.assertEqual(scope, "20240101/us-west-2/ses/aws4_request")

    def test_string_to_sign_and_timestamp(self):
        s = self.client._get_string_to_sign("alg", "amz", "scope", "hash")
        self.assertIn("alg", s)
        amz, date = self.client._get_timestamp_data()
        self.assertEqual(len(amz), 16)
        self.assertEqual(len(date), 8)

    @patch("src.django_ses_backend.client.urlopen")
    def test_handle_response_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"MessageId":"id"}'
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        result = self.client._handle_response(MagicMock(), 1)
        self.assertEqual(result, {"MessageId": "id"})

    @patch("src.django_ses_backend.client.urlopen")
    def test_post_behavior(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"MessageId":"id"}'
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        self.assertEqual(self.client._post({"data": "x"}), {"MessageId": "id"})
        mock_urlopen.side_effect = SESClientError
        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})
