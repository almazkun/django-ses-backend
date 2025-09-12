import json
from unittest.mock import patch, MagicMock
from urllib.error import URLError
from django.test import TestCase
from src.django_ses_backend.backends import SESClient, SESClientError

from django.test import override_settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from src.django_ses_backend.backends import SESEmailBackend

SES_AWS_ACCESS_KEY_ID = "test_access_key"
SES_AWS_SECRET_ACCESS_KEY = "test_secret_key"
SES_AWS_REGION = "us-west-2"


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

    @patch("src.django_ses_backend.backends.urlopen")
    def test_handle_response_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"MessageId":"id"}'
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        result = self.client._handle_response(MagicMock(), 1)
        self.assertEqual(result, {"MessageId": "id"})

    @patch("src.django_ses_backend.backends.urlopen")
    def test_post_behavior(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"MessageId":"id"}'
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        self.assertEqual(self.client._post({"data": "x"}), {"MessageId": "id"})
        mock_urlopen.side_effect = SESClientError
        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})


@override_settings(
    SES_AWS_ACCESS_KEY_ID=SES_AWS_ACCESS_KEY_ID,
    SES_AWS_SECRET_ACCESS_KEY=SES_AWS_SECRET_ACCESS_KEY,
    SES_AWS_REGION=SES_AWS_REGION,
)
class TestSESEmailBackend(TestCase):
    def setUp(self):
        self.backend = SESEmailBackend()
        self.email_text = EmailMessage("Subj", "Body", "from@x.com", ["to@x.com"])
        self.email_html = EmailMessage(
            "Subj", "<p>Body</p>", "from@x.com", ["to@x.com"]
        )
        self.email_html.content_subtype = "html"

    def test_load_configuration(self):
        self.backend._load_configuration(None, None, None)
        self.assertEqual(self.backend.access_key, SES_AWS_ACCESS_KEY_ID)
        self.backend._load_configuration("k", "s", "r")
        self.assertEqual(self.backend.access_key, "k")
        with self.assertRaises(ValueError):
            with override_settings(
                SES_AWS_ACCESS_KEY_ID=None,
                SES_AWS_SECRET_ACCESS_KEY=None,
                SES_AWS_REGION=None,
            ):
                self.backend._load_configuration(None, None, None)

    def test_build_destination_varieties(self):
        email = EmailMessage(
            "Subj", "Body", "from@x.com", ["to@x.com"], cc=["cc"], bcc=["bcc"]
        )
        dest = self.backend._build_destination(email)
        self.assertIn("CcAddresses", dest)
        email2 = EmailMessage("Subj", "Body", "from@x.com", ["to@x.com"])
        self.assertEqual(
            self.backend._build_destination(email2), {"ToAddresses": ["to@x.com"]}
        )

    def test_build_content_body_cases(self):
        body = self.backend._build_content_body(self.email_text)
        self.assertEqual(body, {"Text": {"Data": "Body"}})
        body = self.backend._build_content_body(self.email_html)
        self.assertEqual(body, {"Html": {"Data": "<p>Body</p>"}})

        email_alt = EmailMultiAlternatives("Subj", "Text", "from@x.com", ["to@x.com"])
        email_alt.attach_alternative("<p>HTML</p>", "text/html")
        body = self.backend._build_content_body(email_alt)
        self.assertIn("Html", body)
        self.assertIn("Text", body)

    def test_msg_to_data(self):
        data = self.backend._msg_to_data(self.email_text)
        self.assertEqual(data["FromEmailAddress"], "from@x.com")
        self.assertEqual(data["Destination"]["ToAddresses"], ["to@x.com"])

    @patch("src.django_ses_backend.backends.SESClient")
    def test_open_and_close(self, mock_ses_client):
        self.assertTrue(self.backend.open())
        self.assertIsNotNone(self.backend.connection)
        self.backend.close()
        self.assertIsNone(self.backend.connection)

    def test_send_behavior(self):
        self.backend.connection = MagicMock()
        no_recipients = EmailMessage("Subj", "Body", "from@x.com", [])
        self.assertFalse(self.backend._send(no_recipients))
        self.backend._send(self.email_text)
        self.backend.connection.send_email.assert_called()

    @patch.object(SESEmailBackend, "_send")
    def test_send_messages_variants(self, mock_send):
        self.backend.connection = MagicMock()
        mock_send.side_effect = [True, False]
        emails = [MagicMock(), MagicMock()]
        count = self.backend.send_messages(emails)
        self.assertEqual(count, 1)
        self.assertEqual(mock_send.call_count, 2)


class TestSESClientErrors(TestCase):
    def setUp(self):
        self.client = SESClient(
            "key", "secret", "us-west-2", max_retries=2, retry_delay=0
        )

    @patch("src.django_ses_backend.backends.urlopen")
    def test_rate_limit_error_429(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 429
        mock_resp.read.return_value = b'{"error": "rate limit"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.backends.urlopen")
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

    @patch("src.django_ses_backend.backends.urlopen")
    def test_non_retryable_client_error_400(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 400
        mock_resp.read.return_value = b'{"error": "bad request"}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.backends.urlopen")
    def test_url_error_raises_client_error(self, mock_urlopen):
        mock_urlopen.side_effect = URLError("Failed connection")
        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})

    @patch("src.django_ses_backend.backends.urlopen")
    def test_json_decode_error_raises_client_error(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"invalid json"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with self.assertRaises(SESClientError):
            self.client._post({"data": "x"})
