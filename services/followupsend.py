# services/gmail_send.py
import base64
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def send_gmail_email(user_token: dict, to: str, subject: str, body: str):
    creds = Credentials(
        token=user_token["access_token"],
        refresh_token=user_token.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=user_token["client_id"],
        client_secret=user_token["client_secret"],
        scopes=["https://www.googleapis.com/auth/gmail.send"]
    )
    service = build("gmail", "v1", credentials=creds)

    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent
