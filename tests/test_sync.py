from unittest.mock import patch, MagicMock

from django.test import override_settings, TestCase
from django.core.mail import EmailMessage, EmailMultiAlternatives

from src.django_ses_backend import SESEmailBackend
from src.django_ses_backend.converters import (
    msg_to_data,
    build_content_body,
    build_destination,
)

SES_AWS_ACCESS_KEY_ID = "test_access_key"
SES_AWS_SECRET_ACCESS_KEY = "test_secret_key"
SES_AWS_REGION = "us-west-2"


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

    def test_load_configuration_async_defaults(self):
        self.assertEqual(self.backend.concurrency_limit, 10)
        self.assertEqual(self.backend.connector_limit, 100)
        self.assertEqual(self.backend.connector_limit_per_host, 10)
        self.assertEqual(self.backend.connect_timeout, 5)

    def test_load_configuration_async_settings_override(self):
        with override_settings(
            SES_CONCURRENCY_LIMIT=5,
            SES_CONNECTOR_LIMIT=50,
            SES_CONNECTOR_LIMIT_PER_HOST=3,
            SES_CONNECT_TIMEOUT=2,
        ):
            self.backend._load_configuration(None, None, None)
        self.assertEqual(self.backend.concurrency_limit, 5)
        self.assertEqual(self.backend.connector_limit, 50)
        self.assertEqual(self.backend.connector_limit_per_host, 3)
        self.assertEqual(self.backend.connect_timeout, 2)

    def test_build_destination_varieties(self):
        email = EmailMessage(
            "Subj", "Body", "from@x.com", ["to@x.com"], cc=["cc"], bcc=["bcc"]
        )
        dest = build_destination(email)
        self.assertIn("CcAddresses", dest)
        email2 = EmailMessage("Subj", "Body", "from@x.com", ["to@x.com"])
        self.assertEqual(build_destination(email2), {"ToAddresses": ["to@x.com"]})

    def test_build_content_body_cases(self):
        body = build_content_body(self.email_text)
        self.assertEqual(body, {"Text": {"Data": "Body"}})
        body = build_content_body(self.email_html)
        self.assertEqual(body, {"Html": {"Data": "<p>Body</p>"}})

        email_alt = EmailMultiAlternatives("Subj", "Text", "from@x.com", ["to@x.com"])
        email_alt.attach_alternative("<p>HTML</p>", "text/html")
        body = build_content_body(email_alt)
        self.assertIn("Html", body)
        self.assertIn("Text", body)

    def test_msg_to_data(self):
        data = msg_to_data(self.email_text)
        self.assertEqual(data["FromEmailAddress"], "from@x.com")
        self.assertEqual(data["Destination"]["ToAddresses"], ["to@x.com"])

    @patch("src.django_ses_backend.backends.sync.SESClient")
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
