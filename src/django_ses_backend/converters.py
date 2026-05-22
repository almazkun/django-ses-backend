from typing import Dict, List, Optional, Tuple
from django.core.mail import EmailMessage, EmailMultiAlternatives


def build_destination(email_message: EmailMessage) -> Dict[str, List[str]]:
    destination = {"ToAddresses": email_message.to or []}
    if email_message.cc:
        destination["CcAddresses"] = email_message.cc
    if email_message.bcc:
        destination["BccAddresses"] = email_message.bcc
    return destination


def extract_alternatives(
    email_message: EmailMessage,
) -> Tuple[Optional[str], Optional[str]]:
    text_content, html_content = None, None

    if email_message.body:
        if email_message.content_subtype == "html":
            html_content = email_message.body
        else:
            text_content = email_message.body

    if isinstance(email_message, EmailMultiAlternatives):
        for content, content_type in email_message.alternatives:
            if content_type == "text/html" and not html_content:
                html_content = content
            elif content_type == "text/plain" and not text_content:
                text_content = content

    return text_content, html_content


def build_content_body(email_message: EmailMessage) -> Dict[str, Dict[str, str]]:
    body: Dict[str, Dict[str, str]] = {}
    text_content, html_content = extract_alternatives(email_message)

    if text_content:
        body["Text"] = {"Data": text_content}
    if html_content:
        body["Html"] = {"Data": html_content}

    return body


def msg_to_data(email_message: EmailMessage) -> dict:
    data = {
        "FromEmailAddress": email_message.from_email,
        "Destination": build_destination(email_message),
        "Content": {
            "Simple": {
                "Subject": {"Data": email_message.subject},
                "Body": build_content_body(email_message),
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
