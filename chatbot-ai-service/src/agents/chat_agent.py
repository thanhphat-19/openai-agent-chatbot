from pathlib import Path

from agents import Agent

_prompt = (Path(__file__).parent.parent / "prompts" / "chat_system.md").read_text()

chat_agent = Agent(
    name="Assistant",
    instructions=_prompt,
    model="gpt-4o-mini",
)
