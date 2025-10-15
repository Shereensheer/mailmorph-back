# services/replies_service.py
from typing import List, Dict
from .gmail_auth import get_gmail_service

def fetch_replies() -> List[Dict]:
    service = get_gmail_service()
    results = service.users().messages().list(userId="me", q="in:inbox").execute()
    messages = results.get("messages", [])

    replies = []
    for msg in messages[:10]:  # sirf last 10 replies fetch
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])

        from_ = subject = ""
        for h in headers:
            if h["name"] == "From":
                from_ = h["value"]
            elif h["name"] == "Subject":
                subject = h["value"]

        body = ""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    import base64
                    body = base64.urlsafe_b64decode(
                        part["body"]["data"].encode("UTF-8")
                    ).decode("utf-8")
                    break

        replies.append({
            "from": from_,
            "subject": subject,
            "body": body.strip(),
            "threadId": msg.get("threadId", "")
        })

    return replies
