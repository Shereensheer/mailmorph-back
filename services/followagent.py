import os
from dotenv import load_dotenv
from agents import Agent, OpenAIChatCompletionsModel, Runner
from agents.run import RunConfig
from openai import AsyncOpenAI

load_dotenv()

openai_api = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=openai_api)

model = OpenAIChatCompletionsModel(
    model="gpt-4o-mini",
    openai_client=client
)

config = RunConfig(
    model=model,
    model_provider=client,
    tracing_disabled=True,
    model_settings={
        "temperature": 0.7,
        "max_tokens": 400,
        "top_p": 0.9,
    }
)

async def generate_followup(name: str, company: str | None = None) -> str:
    prompt = f"""
    Write a polite and professional follow-up email to {name} from {company or "our company"}.
    Keep it under 100 words.
    """
    agent = Agent(
        name="followup-writer",
        instructions="You are an AI that writes short professional follow-up emails.",
        model=model,
    )
    result = await Runner.run(agent, prompt)
    return result.output_text.strip()
