from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import base64
from email.mime.text import MIMEText
from datetime import datetime
from services.gmail_auth import get_gmail_service
from services import email_storage
from services.ai_writer import generate_email

router = APIRouter()

class SendReq(BaseModel):
    to: str
    subject: str
    body: str

class GenerateReq(BaseModel):
    subject: str
    body: str
    to: str

def _create_message(to: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}

@router.post("/send")
def api_send(req: SendReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        message = _create_message(req.to, req.subject, req.body)
        sent = service.users().messages().send(userId="me", body=message).execute()
        thread_id = sent.get("threadId")

        email_storage.save_email({
            "to": req.to,
            "subject": req.subject,
            "body": req.body,
            "threadId": thread_id,
            "timestamp": str(datetime.utcnow())
        })
        return {"ok": True, "threadId": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-reply")
async def api_generate_reply(req: GenerateReq):
    try:
        reply = await generate_email(req.subject, req.body)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/replies-latest")
def get_latest_replies():
    try:
        emails = email_storage.load_emails()
        latest = sorted(emails, key=lambda x: x.get("timestamp", ""), reverse=True)
        return {"items": latest[:10]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from fastapi import APIRouter, HTTPException
import os, json

router = APIRouter()

STORAGE_FILE = "sent_emails.json"

def load_emails():
    if os.path.exists(STORAGE_FILE):
        with open(STORAGE_FILE, "r") as f:
            return json.load(f)
    return []

def save_emails(data):
    with open(STORAGE_FILE, "w") as f:
        json.dump(data, f, indent=4)

@router.get("/emails")
def get_emails():
    return load_emails()

@router.delete("/emails/{thread_id}")
def delete_email(thread_id: str):
    emails = load_emails()
    new_emails = [e for e in emails if e["threadId"] != thread_id]
    if len(emails) == len(new_emails):
        raise HTTPException(status_code=404, detail="Email not found")
    save_emails(new_emails)
    return {"message": "Deleted successfully"}
