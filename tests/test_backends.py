from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.mail import EmailMessage

from src.django_ses_backend.backends import SESClient, SESClientError, SESEmailBackend

SES_AWS_ACCESS_KEY_ID = "test_access_key"
SES_AWS_SECRET_ACCESS_KEY = "test_secret_key"
SES_AWS_REGION = "us-west-2"


class TestSESClient(TestCase):
    def setUp(self):
        self.client = SESClient("test_access_key", "test_secret_key", "us-west-2")

    def test_sign(self):
        key = b"test_key"
        msg = "test_message"
        signature = self.client._sign(key, msg)
        self.assertIsInstance(signature, bytes)

    def test_get_signing_key(self):
        date_stamp = "20240101"
        key = self.client._get_signing_key(date_stamp)
        self.assertIsInstance(key, bytes)

    def test_signature(self):
        date_stamp = "20240101"
        string_to_sign = "test_string_to_sign"
        signature = self.client._signature(date_stamp, string_to_sign)
        self.assertIsInstance(signature, str)
        self.assertEqual(len(signature), 64)  # SHA256 hexdigest is 64 characters long

    def test_get_canonical_headers(self):
        amz_date = "20240101T120000Z"
        headers = self.client._get_canonical_headers(amz_date)
        self.assertIn("content-type:application/json", headers)
        self.assertIn("host:email.us-west-2.amazonaws.com", headers)
        self.assertIn(f"x-amz-date:{amz_date}", headers)

    def test_get_payload_hash(self):
        payload = {"test": "data"}
        payload_hash = self.client._get_payload_hash(payload)
        self.assertIsInstance(payload_hash, str)
        self.assertEqual(
            len(payload_hash), 64
        )  # SHA256 hexdigest is 64 characters long

    def test_canonical_request(self):
        canonical_headers = "content-type:application/json\nhost:test.com\nx-amz-date:20240101T120000Z\n"
        payload_hash = "abcdef1234567890"
        hashed_request = self.client._canonical_request(canonical_headers, payload_hash)
        self.assertIsInstance(hashed_request, str)
        self.assertEqual(
            len(hashed_request), 64
        )  # SHA256 hexdigest is 64 characters long

    def test_get_credential_scope(self):
        date_stamp = "20240101"
        scope = self.client._get_credential_scope(date_stamp)
        self.assertEqual(scope, "20240101/us-west-2/ses/aws4_request")

    def test_get_string_to_sign(self):
        algorithm = "AWS4-HMAC-SHA256"
        amz_date = "20240101T120000Z"
        credential_scope = "20240101/us-west-2/ses/aws4_request"
        hashed_request = "abcdef1234567890"

        string = self.client._get_string_to_sign(
            algorithm, amz_date, credential_scope, hashed_request
        )
        self.assertEqual(
            string, f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashed_request}"
        )

    def test_get_timestamp_data(self):
        amz_date, date_stamp = self.client._get_timestamp_data()
        self.assertIsInstance(amz_date, str)
        self.assertIsInstance(date_stamp, str)
        self.assertEqual(len(amz_date), 16)  # Format: YYYYMMDDTHHMMSSZs
        self.assertEqual(len(date_stamp), 8)  # Format: YYYYMMDD

    @patch("src.django_ses_backend.backends.urlopen")
    def test_handle_response(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"MessageId": "test_message_id"}'
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        mock_request = MagicMock()
        result = self.client._handle_response(mock_request, 1)
        self.assertEqual(result, {"MessageId": "test_message_id"})

    @patch("src.django_ses_backend.backends.urlopen")
    def test_post_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"MessageId": "test_message_id"}'
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response

        data = {"test": "data"}
        result = self.client._post(data)

        self.assertEqual(result, {"MessageId": "test_message_id"})
        mock_urlopen.assert_called_once()

    @patch("src.django_ses_backend.backends.urlopen")
    def test_post_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = SESClientError("Connection error")

        with self.assertRaises(SESClientError):
            self.client._post({"test": "data"})


@override_settings(
    SES_AWS_ACCESS_KEY_ID=SES_AWS_ACCESS_KEY_ID,
    SES_AWS_SECRET_ACCESS_KEY=SES_AWS_SECRET_ACCESS_KEY,
    SES_AWS_REGION=SES_AWS_REGION,
)
class TestSESEmailBackend(TestCase):
    def setUp(self):
        self.backend = SESEmailBackend()

    def test_load_configuration_from_settings(self):
        self.backend._load_configuration(None, None, None)
        self.assertEqual(self.backend.access_key, SES_AWS_ACCESS_KEY_ID)
        self.assertEqual(self.backend.secret_key, SES_AWS_SECRET_ACCESS_KEY)
        self.assertEqual(self.backend.region, SES_AWS_REGION)

    def test_load_configuration_from_params(self):
        self.backend._load_configuration(
            "custom_access_key", "custom_secret_key", "eu-west-1"
        )
        self.assertEqual(self.backend.access_key, "custom_access_key")
        self.assertEqual(self.backend.secret_key, "custom_secret_key")
        self.assertEqual(self.backend.region, "eu-west-1")

    @override_settings(
        SES_AWS_ACCESS_KEY_ID=None,
        SES_AWS_SECRET_ACCESS_KEY=None,
        SES_AWS_REGION=None,
    )
    def test_load_configuration_missing_config(self):
        with self.assertRaises(ValueError):
            self.backend._load_configuration(None, None, None)

    def test_build_destination_with_to_only(self):
        email = EmailMessage(
            subject="Test",
            body="Test",
            from_email="from@example.com",
            to=["to@example.com"],
        )
        destination = self.backend._build_destination(email)
        self.assertEqual(destination, {"ToAddresses": ["to@example.com"]})

    def test_build_destination_with_cc_bcc(self):
        email = EmailMessage(
            subject="Test",
            body="Test",
            from_email="from@example.com",
            to=["to@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
        )
        destination = self.backend._build_destination(email)
        self.assertEqual(
            destination,
            {
                "ToAddresses": ["to@example.com"],
                "CcAddresses": ["cc@example.com"],
                "BccAddresses": ["bcc@example.com"],
            },
        )

    def test_build_content_body_text(self):
        email = EmailMessage(
            subject="Test",
            body="Test Body",
            from_email="from@example.com",
            to=["to@example.com"],
        )
        body = self.backend._build_content_body(email)
        self.assertEqual(body, {"Text": {"Data": "Test Body"}})

    def test_build_content_body_html(self):
        email = EmailMessage(
            subject="Test",
            body="<p>Test Body</p>",
            from_email="from@example.com",
            to=["to@example.com"],
        )
        email.content_subtype = "html"
        body = self.backend._build_content_body(email)
        self.assertEqual(
            body,
            {
                "Html": {"Data": "<p>Test Body</p>"},
                "Text": {"Data": "<p>Test Body</p>"},
            },
        )

    def test_msg_to_data_text(self):
        email = EmailMessage(
            subject="Test Subject",
            body="Test Body",
            from_email="sender@example.com",
            to=["recipient@example.com"],
        )
        data = self.backend._msg_to_data(email)
        self.assertEqual(data["FromEmailAddress"], "sender@example.com")
        self.assertEqual(data["Destination"]["ToAddresses"], ["recipient@example.com"])
        self.assertEqual(data["Content"]["Simple"]["Subject"]["Data"], "Test Subject")
        self.assertEqual(data["Content"]["Simple"]["Body"]["Text"]["Data"], "Test Body")

    def test_msg_to_data_html(self):
        email = EmailMessage(
            subject="Test Subject",
            body="<p>Test Body</p>",
            from_email="sender@example.com",
            to=["recipient@example.com"],
        )
        email.content_subtype = "html"
        data = self.backend._msg_to_data(email)
        self.assertEqual(
            data["Content"]["Simple"]["Body"]["Html"]["Data"], "<p>Test Body</p>"
        )

    @patch("src.django_ses_backend.backends.SESClient")
    def test_open(self, mock_ses_client):
        result = self.backend.open()
        self.assertTrue(result)
        self.assertIsNotNone(self.backend.connection)
        mock_ses_client.assert_called_once_with(
            access_key="test_access_key",
            secret_key="test_secret_key",
            region="us-west-2", endpoint_url=None, endpoint_path=None, timeout=10, max_retries=3, retry_delay=1.0
        )

    def test_close(self):
        self.backend.connection = MagicMock()
        self.backend.close()
        self.assertIsNone(self.backend.connection)

    def test_send_no_recipients(self):
        email = EmailMessage(
            subject="Test Subject",
            body="Test Body",
            from_email="sender@example.com",
            to=[],
        )
        result = self.backend._send(email)
        self.assertFalse(result)

    @patch.object(SESClient, "send_email")
    def test_send_success(self, mock_send_email):
        self.backend.connection = SESClient(
            "test_access_key", "test_secret_key", "us-west-2"
        )
        email = EmailMessage(
            subject="Test Subject",
            body="Test Body",
            from_email="sender@example.com",
            to=["recipient@example.com"],
        )
        result = self.backend._send(email)
        self.assertTrue(result)
        mock_send_email.assert_called_once()

    @patch.object(SESClient, "send_email")
    def test_send_failure(self, mock_send_email):
        self.backend.connection = SESClient(
            "test_access_key", "test_secret_key", "us-west-2"
        )
        mock_send_email.side_effect = SESClientError("Test error")
        email = EmailMessage(
            subject="Test Subject",
            body="Test Body",
            from_email="sender@example.com",
            to=["recipient@example.com"],
        )
        self.backend.fail_silently = True
        result = self.backend._send(email)
        self.assertFalse(result)

    @patch.object(SESEmailBackend, "_send")
    def test_send_messages_empty(self, mock_send):
        sent = self.backend.send_messages([])
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()

    @patch.object(SESEmailBackend, "open")
    @patch.object(SESEmailBackend, "_send")
    def test_send_messages_connection_failure(self, mock_send, mock_open):
        mock_open.return_value = True
        self.backend.connection = None
        sent = self.backend.send_messages([MagicMock()])
        self.assertEqual(sent, 0)
        mock_send.assert_not_called()

    @patch.object(SESEmailBackend, "_send")
    def test_send_messages(self, mock_send):
        mock_send.side_effect = [True, False, True]
        emails = [MagicMock() for _ in range(3)]
        self.backend.connection = MagicMock()
        sent = self.backend.send_messages(emails)
        self.assertEqual(sent, 2)
        self.assertEqual(mock_send.call_count, 3)
