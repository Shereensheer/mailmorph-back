from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel
import pickle, os
from datetime import datetime
from services.gmail_auth import get_gmail_service
from services.ai_writer import generate_email
from email import _create_message  # reuse message creator

LEADS_FILE = "leads.pkl"
router = APIRouter()

class Lead(BaseModel):
    name: str | None = None
    email: str
    company: str | None = None
    role: str | None = None
    score: float = 0.0
    last_contacted: str | None = None
    status: str = "new"

def save_leads(leads: list):
    with open(LEADS_FILE, "wb") as f:
        pickle.dump(leads, f)

def load_leads():
    if os.path.exists(LEADS_FILE):
        with open(LEADS_FILE, "rb") as f:
            return pickle.load(f)
    return []

@router.post("/add")
def add_lead(lead: Lead):
    leads = load_leads()
    leads.append(lead.dict())
    save_leads(leads)
    return {"ok": True, "message": "Lead added successfully"}

@router.get("/list")
def list_leads():
    return {"items": load_leads()}

@router.post("/delete")
def delete_lead(lead: dict = Body(...)):
    email_to_delete = lead.get("email")
    if not email_to_delete:
        raise HTTPException(status_code=400, detail="Email required")

    leads = load_leads()
    new_leads = [l for l in leads if l.get("email") != email_to_delete]

    if len(new_leads) == len(leads):
        return {"ok": False, "message": "Lead not found"}

    save_leads(new_leads)
    return {"ok": True, "message": f"Lead {email_to_delete} deleted"}

@router.post("/followup")
async def lead_followup():
    leads = load_leads()
    updated_count = 0

    for i, lead in enumerate(leads):
        if lead['status'] == "new":
            subject = f"Hi {lead.get('name','')}, Just following up"
            body = await generate_email(subject, "Original body content here")

            service = get_gmail_service()
            if service:
                message = _create_message(lead['email'], subject, body)
                service.users().messages().send(userId="me", body=message).execute()

            lead['status'] = "contacted"
            lead['last_contacted'] = str(datetime.utcnow())
            leads[i] = lead
            updated_count += 1

    save_leads(leads)
    return {"ok": True, "updated_count": updated_count}
