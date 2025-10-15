from fastapi import APIRouter, Body, HTTPException
from datetime import datetime
from models import FollowUpRequest
from services.storage import load_leads, save_leads
from services.gmail_send import send_gmail_email, get_gmail_service
from services.ai_writer import generate_followup

router = APIRouter(prefix="/lead", tags=["Leads"])

@router.post("/followup")
async def followup_lead(req: FollowUpRequest = Body(None)):
    """
    ✅ Follow-up:
    - Agar body hai → ek lead ko email bhejo
    - Agar empty hai → sab "new" leads ko bhejo
    """
    leads = load_leads()
    updated_count = 0
    service = get_gmail_service()

    if not service:
        raise HTTPException(status_code=401, detail="Login with Google first at /auth/login")

    if req:  
        try:
            body = await generate_followup(req.name or "there", req.company)
            subject = f"Following up with you, {req.name or ''}".strip()

            send_gmail_email(service, req.email, subject, body)

            for i, lead in enumerate(leads):
                if lead["email"] == req.email:
                    lead["status"] = "contacted"
                    lead["last_contacted"] = str(datetime.utcnow())
                    leads[i] = lead
                    break

            save_leads(leads)
            return {"ok": True, "message": f"Follow-up sent to {req.email}"}

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    else:
        for i, lead in enumerate(leads):
            if lead["status"] == "new":
                subject = f"Hi {lead.get('name','')}, just following up"
                body = await generate_followup(lead.get("name","there"), lead.get("company"))

                send_gmail_email(service, lead["email"], subject, body)

                lead["status"] = "contacted"
                lead["last_contacted"] = str(datetime.utcnow())
                leads[i] = lead
                updated_count += 1

        save_leads(leads)
        return {"ok": True, "updated_count": updated_count}
