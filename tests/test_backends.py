import unittest
from unittest.mock import patch, MagicMock
from django.core.mail import EmailMessage
from django.test import override_settings

# Assuming the SES backend code is in a file named ses_backend.py
from src.django_ses_backend.backends import SESClient, SESClientError, SESEmailBackend


class TestSESClient(unittest.TestCase):
    def setUp(self):
        self.client = SESClient("test_access_key", "test_secret_key", "us-west-2")

    def test_sign(self):
        key = b"test_key"
        msg = "test_message"
        signature = self.client._sign(key, msg)
        self.assertIsInstance(signature, bytes)

    def test_signature(self):
        date_stamp = "20240101"
        string_to_sign = "test_string_to_sign"
        signature = self.client._signature(date_stamp, string_to_sign)
        self.assertIsInstance(signature, str)
        self.assertEqual(len(signature), 64)  # SHA256 hexdigest is 64 characters long

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


class TestSESEmailBackend(unittest.TestCase):
    @override_settings(
        SES_AWS_ACCESS_KEY_ID="test_access_key",
        SES_AWS_SECRET_ACCESS_KEY="test_secret_key",
        SES_AWS_REGION="us-west-2",
    )
    def setUp(self):
        self.backend = SESEmailBackend()

    def test_init_with_settings(self):
        self.assertEqual(self.backend.access_key, "test_access_key")
        self.assertEqual(self.backend.secret_key, "test_secret_key")
        self.assertEqual(self.backend.region, "us-west-2")

    def test_init_with_parameters(self):
        backend = SESEmailBackend(
            access_key="custom_access_key",
            secret_key="custom_secret_key",
            region="eu-west-1",
        )
        self.assertEqual(backend.access_key, "custom_access_key")
        self.assertEqual(backend.secret_key, "custom_secret_key")
        self.assertEqual(backend.region, "eu-west-1")

    def test_init_missing_config(self):
        with self.assertRaises(ValueError):
            SESEmailBackend(access_key=None, secret_key=None, region=None)

    @patch("src.django_ses_backend.backends.SESClient")
    def test_open(self, mock_ses_client):
        result = self.backend.open()
        self.assertTrue(result)
        self.assertIsNotNone(self.backend.connection)
        mock_ses_client.assert_called_once_with(
            access_key="test_access_key",
            secret_key="test_secret_key",
            region="us-west-2",
        )

    def test_close(self):
        self.backend.connection = MagicMock()
        self.backend.close()
        self.assertIsNone(self.backend.connection)

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
    def test_send_messages(self, mock_send):
        mock_send.side_effect = [True, False, True]
        emails = [MagicMock() for _ in range(3)]
        self.backend.connection = MagicMock()
        sent = self.backend.send_messages(emails)
        self.assertEqual(sent, 2)
        self.assertEqual(mock_send.call_count, 3)


if __name__ == "__main__":
    unittest.main()
