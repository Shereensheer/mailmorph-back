import os
import pickle
import json
import base64
import re
from uuid import uuid4
from datetime import datetime
from typing import Optional, List
import uuid

from fastapi import FastAPI, HTTPException, Request, Body, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from services.gmail_auth import get_gmail_service
from services import email_storage
from services.ai_writer import generate_email, generate_smart_email, score_lead

# ------------------- Config -------------------
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # for localhost dev
TOKEN_PATH = "token.pkl"
CLIENT_SECRET_FILE = "client_secret.json"
FRONTEND_URL = "http://localhost:3000"
LEADS_FILE = "leads.pkl"
USERS_FILE = "users.json"
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------- App Init -------------------
app = FastAPI(title="MailMorph API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- Models -------------------
class GenerateReq(BaseModel):
    subject: str
    body: str
    to: str

class SendReq(BaseModel):
    to: str
    subject: str
    body: str

class ReplyReq(BaseModel):
    threadId: str
    to: str
    body: str

class Lead(BaseModel):
    id: int | None = None
    name: str | None = None
    email: str
    company: str | None = None
    role: str | None = None
    score: float | str = 0.0          # kept flexible: float (old) or string label (new)
    last_contacted: str | None = None
    status: str = "new"
    opened: int | None = 0            # optional tracking fields (if you want to update)
    clicked: int | None = 0
    replied: bool | None = False

class User(BaseModel):
    id: int | None = None
    name: str | None = None
    email: str
    bio: str | None = None
    profile_pic: str | None = None
    status: str = "active"

# ------------------- Storage Helpers -------------------
def save_pickle(path, data):
    with open(path, "wb") as f:
        pickle.dump(data, f)

def load_pickle(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return []

def save_leads(leads: list): save_pickle(LEADS_FILE, leads)
def load_leads(): return load_pickle(LEADS_FILE)

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ------------------- Health -------------------
@app.get("/health")
def health():
    return {"ok": True}

# ------------------- Gmail OAuth -------------------
@app.get("/auth/login")
def auth_login():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        redirect_uri="http://localhost:8000/auth/callback",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        redirect_uri="http://localhost:8000/auth/callback",
    )
    try:
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")

        users = load_users()
        if not any(u["email"] == email for u in users):
            new_user = {
                "id": len(users) + 1,
                "name": email.split("@")[0],
                "email": email,
                "bio": "",
                "profile_pic": None,
                "status": "active",
            }
            users.append(new_user)
            save_users(users)

        return RedirectResponse(FRONTEND_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth Callback Error: {str(e)}")

@app.get("/auth/me")
def auth_me():
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")

        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        return {"user": user}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/logout")
def auth_logout():
    try:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
        return {"ok": True, "message": "Logged out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Gmail Helpers -------------------
from email.mime.text import MIMEText
def _create_message(to: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}

def _get_header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

# ------------------- Email Send -------------------
@app.post("/send")
def api_send(req: SendReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        message = _create_message(req.to, req.subject, req.body)
        sent = service.users().messages().send(userId="me", body=message).execute()
        thread_id = sent.get("threadId")

        email_storage.save_email({
            "id": str(uuid4()),
            "to": req.to,
            "subject": req.subject,
            "body": req.body,
            "threadId": thread_id,
            "timestamp": str(datetime.utcnow())
        })
        return {"ok": True, "threadId": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Reply -------------------
@app.post("/reply")
def api_reply(req: ReplyReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        thread = service.users().threads().get(userId="me", id=req.threadId).execute()
        msgs = thread.get("messages", [])
        subject = "Re:"
        if msgs:
            headers = msgs[0]["payload"].get("headers", [])
            original_subject = _get_header(headers, "Subject") or ""
            subject = f"Re: {original_subject}".strip()

        message = _create_message(req.to, subject, req.body)
        message["threadId"] = req.threadId
        service.users().messages().send(userId="me", body=message).execute()

        existing = email_storage.load_replies()
        existing.append({
            "from": "me",
            "subject": subject,
            "body": req.body,
            "threadId": req.threadId,
            "timestamp": str(datetime.utcnow())
        })
        email_storage.save_replies(existing)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- AI Email -------------------
@app.post("/generate-reply")
async def api_generate_reply(req: GenerateReq):
    try:
        reply = await generate_email(req.subject, req.body)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-smart-email")
async def api_generate_smart_email(req: GenerateReq):
    try:
        result = await generate_smart_email(req.subject, req.body, req.to)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Sent / Replies -------------------
@app.get("/sent")
def api_sent():
    try:
        return {"items": email_storage.load_emails()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/replies")
def api_replies():
    try:
        return {"items": email_storage.load_replies()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Leads API -------------------
@app.post("/lead/add")
def add_lead(lead: Lead):
    leads = load_leads()
    lead.id = len(leads) + 1
    # ensure these tracking fields exist if not provided
    lead_dict = lead.dict()
    if "opened" not in lead_dict: lead_dict["opened"] = 0
    if "clicked" not in lead_dict: lead_dict["clicked"] = 0
    if "replied" not in lead_dict: lead_dict["replied"] = False
    leads.append(lead_dict)
    save_leads(leads)
    return {"ok": True, "message": "Lead added successfully"}

@app.get("/lead/list")
def list_leads():
    return {"items": load_leads()}

@app.post("/lead/delete")
def delete_lead(lead: dict = Body(...)):
    lead_id = lead.get("id")
    if not lead_id:
        raise HTTPException(status_code=400, detail="Lead ID required")

    leads = load_leads()
    new_leads = [l for l in leads if l.get("id") != lead_id]

    if len(new_leads) == len(leads):
        return {"ok": False, "message": "Lead not found"}

    for i, l in enumerate(new_leads, start=1):
        l["id"] = i

    save_leads(new_leads)
    return {"ok": True, "message": f"Lead {lead_id} deleted successfully"}



@app.post("/lead/followup")
async def lead_followup():
    leads = load_leads()
    updated_count = 0

    for i, lead in enumerate(leads):
        if lead['status'] == "new":
            # Personalized subject
            subject = f"Hi {lead.get('name','') or 'there'}, just following up"

            # Personalized email body with AI
            service_offer = f"services we can offer to {lead.get('company','your company')}"
            body = await generate_email(lead.get("company", "your company"), service_offer)

            # Send email if Gmail authenticated
            service = get_gmail_service()
            if service:
                message = _create_message(lead['email'], subject, body)
                service.users().messages().send(userId="me", body=message).execute()

            # Update lead status
            lead['status'] = "contacted"
            lead['last_contacted'] = str(datetime.utcnow())
            leads[i] = lead
            updated_count += 1

    save_leads(leads)
    return {"ok": True, "updated_count": updated_count}



# ------------------- NEW: Smart Lead Scoring -------------------
def _calculate_label_for_lead(lead: dict) -> str:
    """
    Simple rule-based scoring:
    - If replied == True -> Hot 🔥
    - Else if status == 'contacted' or opened >= 1 or clicked >= 1 -> Warm 🙂
    - Else -> Cold ❄️
    """
    try:
        if lead.get("replied", False):
            return "Hot 🔥"
        # if status explicitly 'contacted' => warm
        if lead.get("status", "") == "contacted":
            return "Warm 🙂"
        # if opened or clicked counts exist
        if int(lead.get("opened", 0)) >= 1 or int(lead.get("clicked", 0)) >= 1:
            return "Warm 🙂"
    except Exception:
        # fallback default
        pass
    return "Cold ❄️"

@app.post("/lead/score")
def lead_score():
    """
    Compute and persist score labels for all leads and return updated list.
    This uses a free rule-based approach. You can later replace this with AI scoring.
    """
    leads = load_leads()
    updated = []
    for i, lead in enumerate(leads):
        label = _calculate_label_for_lead(lead)
        # store label in 'score' field (overwrites numeric) for frontend readability
        lead["score"] = label
        # optional: keep numeric score field separate if you want later
        leads[i] = lead
        updated.append(lead)
    save_leads(leads)
    return {"ok": True, "items": updated}

# ------------------- User API -------------------
@app.patch("/user/update")
async def update_user(
    id: int = Form(...),
    name: str = Form(...),
    bio: Optional[str] = Form(None),
    profilePic: Optional[UploadFile] = File(None),
):
    users = load_users()
    updated_user = None

    for i, u in enumerate(users):
        if u.get("id") == id:
            u["name"] = name
            u["bio"] = bio

            if profilePic:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                file_location = f"{UPLOAD_DIR}/{u['id']}_{profilePic.filename}"
                with open(file_location, "wb") as f:
                    f.write(await profilePic.read())
                u["profile_pic"] = f"/{file_location}"

            users[i] = u
            updated_user = u
            break

    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    save_users(users)
    return {"ok": True, "user": updated_user}

# ------------------- Bulk Email Send -------------------
class BulkSendReq(BaseModel):
    to: List[str]
    subject: str
    body: str

@app.post("/send-bulk")
def api_send_bulk(req: BulkSendReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        sent_threads = []
        for recipient in req.to:
            message = _create_message(recipient, req.subject, req.body)
            sent = service.users().messages().send(userId="me", body=message).execute()
            thread_id = sent.get("threadId")

            email_storage.save_email({
                "id": str(uuid4()),
                "to": recipient,
                "subject": req.subject,
                "body": req.body,
                "threadId": thread_id,
                "timestamp": str(datetime.utcnow())
            })
            sent_threads.append({"to": recipient, "threadId": thread_id})

        return {"ok": True, "sent": sent_threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Stripe Checkout -------------------
import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class Item(BaseModel):
    id: int
    title: str
    price: float
    quantity: int

class CheckoutRequest(BaseModel):
    name: str
    email: str
    address: str
    items: List[Item]

@app.post("/checkout")
async def create_checkout(data: CheckoutRequest):
    try:
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": item.title},
                    "unit_amount": int(item.price * 100),
                },
                "quantity": item.quantity,
            }
            for item in data.items
        ]

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url="http://localhost:3000/success",
            cancel_url="http://localhost:3000/cart",
            customer_email=data.email,
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# from services.ai_writer import predict_inbox


# @app.post("/predict-inbox")
# async def predict_inbox_route(payload: dict = Body(...)):
#     subject = payload.get("subject", "")
#     body = payload.get("body", "")
#     return await predict_inbox(subject, body)


import os
import pickle
import json
import base64
from uuid import uuid4
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request, Body, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from services.gmail_auth import get_gmail_service
from services import email_storage
from services.ai_writer import generate_email, generate_smart_email, score_lead

# ------------------- Config -------------------
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # for localhost dev
TOKEN_PATH = "token.pkl"
CLIENT_SECRET_FILE = "client_secret.json"
FRONTEND_URL = "http://localhost:3000"
LEADS_FILE = "leads.pkl"
USERS_FILE = "users.json"
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ------------------- App Init -------------------
app = FastAPI(title="MailMorph API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------- Models -------------------
class GenerateReq(BaseModel):
    subject: str
    body: str
    to: str

class SendReq(BaseModel):
    to: str
    subject: str
    body: str

class ReplyReq(BaseModel):
    threadId: str
    to: str
    body: str

class Lead(BaseModel):
    id: int | None = None
    name: str | None = None
    email: str
    company: str | None = None
    role: str | None = None
    score: float | str = 0.0
    last_contacted: str | None = None
    status: str = "new"
    opened: int | None = 0
    clicked: int | None = 0
    replied: bool | None = False

class User(BaseModel):
    id: int | None = None
    name: str | None = None
    email: str
    bio: str | None = None
    profile_pic: str | None = None
    status: str = "active"

# ------------------- Storage Helpers -------------------
def save_pickle(path, data):
    with open(path, "wb") as f:
        pickle.dump(data, f)

def load_pickle(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return []

def save_leads(leads: list): save_pickle(LEADS_FILE, leads)
def load_leads(): return load_pickle(LEADS_FILE)

def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

# ------------------- Health -------------------
@app.get("/health")
def health():
    return {"ok": True}

# ------------------- Gmail OAuth -------------------
@app.get("/auth/login")
def auth_login():
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        redirect_uri="http://localhost:8000/auth/callback",
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true"
    )
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send",
        ],
        redirect_uri="http://localhost:8000/auth/callback",
    )
    try:
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

        service = get_gmail_service()
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")

        users = load_users()
        if not any(u["email"] == email for u in users):
            new_user = {
                "id": len(users) + 1,
                "name": email.split("@")[0],
                "email": email,
                "bio": "",
                "profile_pic": None,
                "status": "active",
            }
            users.append(new_user)
            save_users(users)

        return RedirectResponse(FRONTEND_URL)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth Callback Error: {str(e)}")

@app.get("/auth/me")
def auth_me():
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")

        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        return {"user": user}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/logout")
def auth_logout():
    try:
        if os.path.exists(TOKEN_PATH):
            os.remove(TOKEN_PATH)
        return {"ok": True, "message": "Logged out"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Gmail Helpers -------------------
from email.mime.text import MIMEText
def _create_message(to: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["to"] = to
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    return {"raw": raw}

def _get_header(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value")
    return None

# ------------------- Email Send -------------------
@app.post("/send")
def api_send(req: SendReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        message = _create_message(req.to, req.subject, req.body)
        sent = service.users().messages().send(userId="me", body=message).execute()
        thread_id = sent.get("threadId")

        email_storage.save_email({
            "id": str(uuid4()),
            "to": req.to,
            "subject": req.subject,
            "body": req.body,
            "threadId": thread_id,
            "timestamp": str(datetime.utcnow()),
            "tags": []   # <-- new tagging support
        })
        return {"ok": True, "threadId": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Reply -------------------
@app.post("/reply")
def api_reply(req: ReplyReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        thread = service.users().threads().get(userId="me", id=req.threadId).execute()
        msgs = thread.get("messages", [])
        subject = "Re:"
        if msgs:
            headers = msgs[0]["payload"].get("headers", [])
            original_subject = _get_header(headers, "Subject") or ""
            subject = f"Re: {original_subject}".strip()

        message = _create_message(req.to, subject, req.body)
        message["threadId"] = req.threadId
        service.users().messages().send(userId="me", body=message).execute()

        existing = email_storage.load_replies()
        existing.append({
            "from": "me",
            "subject": subject,
            "body": req.body,
            "threadId": req.threadId,
            "timestamp": str(datetime.utcnow())
        })
        email_storage.save_replies(existing)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- AI Email -------------------
@app.post("/generate-reply")
async def api_generate_reply(req: GenerateReq):
    try:
        reply = await generate_email(req.subject, req.body)
        return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-smart-email")
async def api_generate_smart_email(req: GenerateReq):
    try:
        result = await generate_smart_email(req.subject, req.body, req.to)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Sent / Replies -------------------
@app.get("/sent")
def api_sent():
    try:
        return {"items": email_storage.load_emails()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/replies")
def api_replies():
    try:
        return {"items": email_storage.load_replies()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Email Tagging -------------------
class TagReq(BaseModel):
    threadId: str
    tags: List[str]

@app.post("/email/tag")
def set_email_tags(req: TagReq):
    emails = email_storage.load_emails()
    updated = None
    for e in emails:
        if e.get("threadId") == req.threadId:
            e["tags"] = req.tags
            updated = e
            break
    if not updated:
        raise HTTPException(status_code=404, detail="Email not found")

    email_storage.save_emails(emails)
    return {"ok": True, "email": updated}

# ------------------- Leads API -------------------
@app.post("/lead/add")
def add_lead(lead: Lead):
    leads = load_leads()
    lead.id = len(leads) + 1
    lead_dict = lead.dict()
    if "opened" not in lead_dict: lead_dict["opened"] = 0
    if "clicked" not in lead_dict: lead_dict["clicked"] = 0
    if "replied" not in lead_dict: lead_dict["replied"] = False
    leads.append(lead_dict)
    save_leads(leads)
    return {"ok": True, "message": "Lead added successfully"}

@app.get("/lead/list")
def list_leads():
    return {"items": load_leads()}

@app.post("/lead/delete")
def delete_lead(lead: dict = Body(...)):
    lead_id = lead.get("id")
    if not lead_id:
        raise HTTPException(status_code=400, detail="Lead ID required")

    leads = load_leads()
    new_leads = [l for l in leads if l.get("id") != lead_id]

    if len(new_leads) == len(leads):
        return {"ok": False, "message": "Lead not found"}

    for i, l in enumerate(new_leads, start=1):
        l["id"] = i

    save_leads(new_leads)
    return {"ok": True, "message": f"Lead {lead_id} deleted successfully"}

@app.post("/lead/followup")
async def lead_followup():
    leads = load_leads()
    updated_count = 0

    for i, lead in enumerate(leads):
        if lead["status"] == "new":
            subject = f"Hi {lead.get('name','') or 'there'}, just following up"
            service_offer = f"services we can offer to {lead.get('company','your company')}"
            body = await generate_email(lead.get("company", "your company"), service_offer)

            service = get_gmail_service()
            if service:
                message = _create_message(lead["email"], subject, body)
                service.users().messages().send(userId="me", body=message).execute()

            lead["status"] = "contacted"
            lead["last_contacted"] = str(datetime.utcnow())
            leads[i] = lead
            updated_count += 1

    save_leads(leads)
    return {"ok": True, "updated_count": updated_count}

# ------------------- Smart Lead Scoring -------------------
def _calculate_label_for_lead(lead: dict) -> str:
    try:
        if lead.get("replied", False):
            return "Hot 🔥"
        if lead.get("status", "") == "contacted":
            return "Warm 🙂"
        if int(lead.get("opened", 0)) >= 1 or int(lead.get("clicked", 0)) >= 1:
            return "Warm 🙂"
    except Exception:
        pass
    return "Cold ❄️"

@app.post("/lead/score")
def lead_score():
    leads = load_leads()
    updated = []
    for i, lead in enumerate(leads):
        label = _calculate_label_for_lead(lead)
        lead["score"] = label
        leads[i] = lead
        updated.append(lead)
    save_leads(leads)
    return {"ok": True, "items": updated}

# ------------------- User API -------------------
@app.patch("/user/update")
async def update_user(
    id: int = Form(...),
    name: str = Form(...),
    bio: Optional[str] = Form(None),
    profilePic: Optional[UploadFile] = File(None),
):
    users = load_users()
    updated_user = None

    for i, u in enumerate(users):
        if u.get("id") == id:
            u["name"] = name
            u["bio"] = bio

            if profilePic:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                file_location = f"{UPLOAD_DIR}/{u['id']}_{profilePic.filename}"
                with open(file_location, "wb") as f:
                    f.write(await profilePic.read())
                u["profile_pic"] = f"/{file_location}"

            users[i] = u
            updated_user = u
            break

    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    save_users(users)
    return {"ok": True, "user": updated_user}

# ------------------- Bulk Email Send -------------------
class BulkSendReq(BaseModel):
    to: List[str]
    subject: str
    body: str

@app.post("/send-bulk")
def api_send_bulk(req: BulkSendReq):
    try:
        service = get_gmail_service()
        if not service:
            raise HTTPException(status_code=401, detail="Not authenticated")

        sent_threads = []
        for recipient in req.to:
            message = _create_message(recipient, req.subject, req.body)
            sent = service.users().messages().send(userId="me", body=message).execute()
            thread_id = sent.get("threadId")

            email_storage.save_email({
                "id": str(uuid4()),
                "to": recipient,
                "subject": req.subject,
                "body": req.body,
                "threadId": thread_id,
                "timestamp": str(datetime.utcnow()),
                "tags": []
            })
            sent_threads.append({"to": recipient, "threadId": thread_id})

        return {"ok": True, "sent": sent_threads}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ------------------- Stripe Checkout -------------------
import stripe
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

class Item(BaseModel):
    id: int
    title: str
    price: float
    quantity: int

class CheckoutRequest(BaseModel):
    name: str
    email: str
    address: str
    items: List[Item]

@app.post("/checkout")
async def create_checkout(data: CheckoutRequest):
    try:
        line_items = [
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": item.title},
                    "unit_amount": int(item.price * 100),
                },
                "quantity": item.quantity,
            }
            for item in data.items
        ]

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url="http://localhost:3000/success",
            cancel_url="http://localhost:3000/cart",
            customer_email=data.email,
        )
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# ------------------------
# Models
# ------------------------
class EmailContent(BaseModel):
    subject: str
    body: str

class PredictionResult(BaseModel):
    verdict: str  # Inbox / Promotions / Spam
    score: float  # 0-1
    risky_words: List[str] = []
    suggestion: str

# ------------------------
# Simple keyword-based predictor
# ------------------------
RISKY_WORDS = [
    "free", "winner", "buy now", "click here", "limited offer", "discount",
    "urgent", "prize", "act now", "exclusive deal", "offer expires", "congratulations",
    "cash bonus", "earn money", "risk-free", "guaranteed", "credit card", "save big",
    "deal of the day", "special promotion", "claim now", "limited time", "hot offer",
    "cheap", "amazing", "bonus", "promotion", "investment opportunity", "double your income"
]


def predict_inbox(subject: str, body: str) -> PredictionResult:
    text = f"{subject} {body}".lower()

    # Detect risky words
    detected = [word for word in RISKY_WORDS if re.search(r"\b" + re.escape(word) + r"\b", text)]

    # Scoring: simple heuristic
    score = max(0.0, 1.0 - 0.15 * len(detected))  # reduce score for each risky word

    # Determine verdict
    if score > 0.7:
        verdict = "Inbox"
        suggestion = "Looks safe! Minimal risky words detected."
    elif 0.4 < score <= 0.7:
        verdict = "Promotions"
        suggestion = "Contains some promotional/risky words. Consider rephrasing."
    else:
        verdict = "Spam"
        suggestion = "High risk of going to spam. Avoid risky words and clickbait."

    return PredictionResult(
        verdict=verdict,
        score=round(score, 2),
        risky_words=detected,
        suggestion=suggestion
    )

# ------------------------
# API Endpoint
# ------------------------
@app.post("/predict-inbox", response_model=PredictionResult)
def api_predict(email: EmailContent):
    try:
        result = predict_inbox(email.subject, email.body)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





class Reply(BaseModel):
    from_: str
    subject: str
    body: str
    threadId: str = None

    def generate_thread_id(self):
        if not self.threadId:
            self.threadId = str(uuid.uuid4())

class ReplyList(BaseModel):
    items: List[Reply]


    # ------------------------
DATA_FILE = "data/replies.json"
os.makedirs("data", exist_ok=True)
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w") as f:
        json.dump([], f)

# ------------------------
# Helpers
# ------------------------
def load_replies() -> List[Reply]:
    with open(DATA_FILE, "r") as f:
        data = json.load(f)
    return [Reply(**item) for item in data]

def save_replies(replies: List[Reply]):
    with open(DATA_FILE, "w") as f:
        json.dump([r.dict() for r in replies], f, indent=2)

# ------------------------
# API Endpoints
# ------------------------

# Get all replies
@app.get("/replies", response_model=List[Reply])
def get_replies():
    return load_replies()

# Add a reply
@app.post("/replies", response_model=Reply)
def add_reply(reply: Reply):
    reply.generate_thread_id()
    replies = load_replies()
    replies.append(reply)
    save_replies(replies)
    return reply

# Delete a reply by threadId
@app.delete("/replies/{thread_id}", response_model=dict)
def delete_reply(thread_id: str):
    replies = load_replies()
    updated = [r for r in replies if r.threadId != thread_id]
    if len(updated) == len(replies):
        raise HTTPException(status_code=404, detail="Thread not found")
    save_replies(updated)
    return {"detail": "Deleted successfully"}

# Clear all replies
@app.delete("/replies", response_model=dict)
def clear_replies():
    save_replies([])
    return {"detail": "All replies cleared"}




# import os
# import uvicorn
# from fastapi import FastAPI

# app = FastAPI()

# @app.get("/")
# def home():
#     return {"message": "MailMorph backend running successfully on Railway!"}

# if __name__ == "__main__":
#     port = int(os.environ.get("PORT", 8000))
#     uvicorn.run("main:app", host="0.0.0.0", port=port)   


import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {"message": "✅ MailMorph backend running successfully on Railway!"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))  # Railway uses 8080
    uvicorn.run(app, host="0.0.0.0", port=port)

