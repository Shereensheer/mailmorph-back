# # services/ai_writer.py
# import os
# import random  # for demo scoring
# from dotenv import load_dotenv

# from agents import Agent, OpenAIChatCompletionsModel, Runner
# from agents.run import RunConfig
# from openai import AsyncOpenAI

# load_dotenv()

# # ----------------- Setup OpenAI Client -----------------
# openai_api = os.getenv("OPENAI_API_KEY")

# client = AsyncOpenAI(api_key=openai_api)

# # ----------------- Model Setup -----------------
# model = OpenAIChatCompletionsModel(
#     model="gpt-4o-mini",   # ⚡ Fast & efficient OpenAI model
#     openai_client=client
# )

# # ----------------- RunConfig with only Model Settings -----------------
# config = RunConfig(
#     model=model,
#     model_provider=client,
#     tracing_disabled=True,
#     model_settings={
#         "temperature": 0.7,   # creativity vs focus
#         "max_tokens": 500,    # output length
#         "top_p": 0.9,         # nucleus sampling
#     }
# )

# # ----------------- AI Email Generator -----------------
# async def generate_email(company, service_offer):
#     """
#     Generate a cold email using OpenAI API (Agent SDK)
#     """
#     try:
#         prompt = f"""Write a professional cold email to {company} offering the following service: {service_offer}.
        
#         The email should:
#         - Be professional and engaging
#         - Be personalized to the company
#         - Clearly explain the value proposition
#         - Include a clear call to action
#         - Be under 200 words
#         """

#         agent = Agent(
#             name="email-writer",
#             instructions="You are a professional AI agent that specializes in writing cold outreach emails.",
#             model=model
#         )

#         result = await Runner.run(agent, prompt, config=config)
#         return result.output_text.strip()
    
#     except Exception as e:
#         print(f"Error generating email: {e}")
#         return (
#             f"Subject: Partnership Opportunity with {company}\n\n"
#             f"Dear {company} Team,\n\n"
#             f"I hope this email finds you well. I'm reaching out to discuss a potential partnership opportunity "
#             f"that could benefit {company}.\n\n"
#             f"We offer {service_offer}, which could help your organization achieve its goals more efficiently.\n\n"
#             f"Would you be interested in a brief call to discuss how we might work together?\n\n"
#             f"Best regards,\n[Your Name]"
#         )

# # ----------------- Lead Scoring Function -----------------
# async def score_lead(lead: dict) -> float:
#     """
#     Simple lead scoring:
#     - Email present: +50
#     - Name present: +30
#     - Random bonus: 0-20
#     """
#     score = 0.0
#     if lead.get("email"):
#         score += 50
#     if lead.get("name"):
#         score += 30
#     score += random.randint(0, 20)
#     return score







# services/ai_writer.py
import os
import random
from dotenv import load_dotenv

from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.run import RunConfig
from openai import AsyncOpenAI

load_dotenv()

# ----------------- Setup OpenAI Client -----------------
openai_api = os.getenv("OPENAI_API_KEY")
if not openai_api:
    raise ValueError("OPENAI_API_KEY not set in environment variables!")

client = AsyncOpenAI(api_key=openai_api)

# ----------------- Model Setup -----------------
model = OpenAIChatCompletionsModel(
    model="gpt-4o-mini",   # ⚡ Fast & efficient OpenAI model
    openai_client=client
)

# ----------------- RunConfig -----------------
config = RunConfig(
    model=model,
    model_provider=client,
    tracing_disabled=True,
    model_settings={
        "temperature": 0.7,
        "max_tokens": 500,
        "top_p": 0.9,
    }
)

# ----------------- AI Cold Email Generator -----------------
async def generate_email(company, service_offer):
    """
    Generate a cold email using OpenAI API (Agent SDK)
    """
    try:
        prompt = f"""
Write a professional cold email to {company} offering the following service: {service_offer}.

Requirements:
- Be professional and engaging
- Personalize to the company
- Clearly explain the value proposition
- Include a clear call to action
- Keep under 200 words
"""
        agent = Agent(
            name="email-writer",
            instructions="You are a professional AI agent specialized in writing cold outreach emails.",
            model=model
        )
        result = await Runner.run(agent, prompt, config=config)
        return result.output_text.strip()

    except Exception as e:
        print(f"[AI Writer] Error generating email: {e}")
        # Fallback plain template
        return (
            f"Subject: Partnership Opportunity with {company}\n\n"
            f"Dear {company} Team,\n\n"
            f"I hope this email finds you well. I'm reaching out to discuss a potential partnership opportunity "
            f"that could benefit {company}.\n\n"
            f"We offer {service_offer}, which could help your organization achieve its goals more efficiently.\n\n"
            f"Would you be interested in a brief call to discuss how we might work together?\n\n"
            f"Best regards,\n[Your Name]"
        )

# ----------------- AI Smart Email (Subject Hooks + Tone) -----------------
async def generate_smart_email(draft_subject: str, draft_body: str, recipient: str):
    """
    Returns 3 subject line suggestions and tone recommendation
    """
    try:
        prompt = f"""
You are an expert email strategist.

Draft subject: {draft_subject}
Draft body: {draft_body}
Recipient: {recipient}

Provide:
1. Three engaging subject line suggestions (short, catchy, <50 chars)
2. Recommended tone (formal, casual, friendly, persuasive)

Output format:
{{
  "subjects": ["...", "...", "..."],
  "tone": "..."
}}
"""
        agent = Agent(
            name="smart-email-generator",
            instructions="You generate 3 subject line options and tone recommendation for an email.",
            model=model
        )
        result = await Runner.run(agent, prompt, config=config)
        return result.output_text.strip()
    except Exception as e:
        print(f"[AI Writer] Error generating smart email: {e}")
        return {
            "subjects": [draft_subject, draft_subject, draft_subject],
            "tone": "formal"
        }

# ----------------- Lead Scoring -----------------
async def score_lead(lead: dict) -> float:
    """
    Simple lead scoring:
    - Email present: +50
    - Name present: +30
    - Random bonus: 0-20
    """
    score = 0.0
    if lead.get("email"):
        score += 50
    if lead.get("name"):
        score += 30
    score += random.randint(0, 20)
    return score
