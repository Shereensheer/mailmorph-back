from services.gmail_auth import get_gmail_service
from services import email_storage
from datetime import datetime
import base64
from email.mime.text import MIMEText
import re

def fetch_replies():
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q="in:inbox newer_than:30d"  # fetch inbox replies in last 30 days
    ).execute()

    messages = results.get("messages", [])
    for msg in messages:
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = msg_data.get("payload", {}).get("headers", [])
        
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        from_email = next((h["value"] for h in headers if h["name"] == "From"), "")
        date = next((h["value"] for h in headers if h["name"] == "Date"), "")

        body_data = ""
        parts = msg_data.get("payload", {}).get("parts", [])
        if parts:
            body_data = base64.urlsafe_b64decode(parts[0]["body"].get("data", "")).decode("utf-8")

        # Try to find which sent email it replies to
        match = re.search(r"<(.+?)>", subject)
        sent_id = match.group(1) if match else None
        
        if sent_id:
            email_storage.save_reply(sent_id, {
                "from": from_email,
                "subject": subject,
                "body": body_data,
                "date": date
            })
