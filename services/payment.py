import os
import httpx
from dotenv import load_dotenv

load_dotenv()

POLAR_API_KEY = os.getenv("POLAR_API_KEY")
POLAR_ORG_ID = os.getenv("POLAR_ORGANIZATION_ID")

BASE_URL = "https://api.polar.sh/v1"


async def create_checkout(product_id: str, customer_email: str):
    """
    Create a checkout link via Polar.sh API
    """
    url = f"{BASE_URL}/checkouts"

    payload = {
        "organization_id": POLAR_ORG_ID,
        "product_id": product_id,
        "customer_email": customer_email,
        "success_url": "http://localhost:3000/success",   # frontend success page
        "cancel_url": "http://localhost:3000/cancel" ,     # frontend cancel page
        "checkout_url":"https://checkout.polar.sh/session/abcd1234"
}
  
        
    

    headers = {
        "Authorization": f"Bearer {POLAR_API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
