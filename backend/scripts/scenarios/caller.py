"""The simulated caller: an LLM that plays a persona against the agent under test."""

from __future__ import annotations

from scripts.scenarios.model import Persona, Turn
from scripts.scenarios.openai_chat import OpenAIChat

HANGUP = "[HANGUP]"

RULES = """You are role-playing a person who phoned (or is chatting with) a business. You are NOT an assistant.
Speak only as the caller: output exactly what you say next, nothing else — no stage directions, no quotes, no labels.
Answer what the agent asks using your facts; if it asks for something not in your facts, make up a plausible answer.
Stay in character and pursue your goal. Play every curveball at the moment it describes, once.
Never invent business details for the agent, and never agree to something that contradicts your goal or facts.
Reply exactly [HANGUP] only when the agent has said goodbye, or your goal is done and you've said goodbye yourself, or the agent clearly can't help after you asked twice. Never hang up in the middle of a booking you still want.
If some of your earlier lines look like noise or nonsense, the phone line was bad — ignore them and carry on toward your goal."""


class CallerBot:
    def __init__(self, chat: OpenAIChat, *, business: str, persona: Persona, channel: str) -> None:
        self.chat = chat
        facts = "\n".join(f"- {key}: {value}" for key, value in persona.facts.items()) or "- (none)"
        curveballs = "\n".join(f"- {item}" for item in persona.curveballs) or "- (none)"
        medium = "a text chat on their website" if channel == "chat" else "a phone call (your words are transcribed speech)"
        self.system = (
            f"{RULES}\n\nBusiness: {business}\nMedium: {medium}\nWho you are: {persona.who}\nYour goal: {persona.goal}\n"
            f"How you talk: {persona.style}\nYour facts:\n{facts}\nCurveballs:\n{curveballs}"
        )

    async def next_line(self, turns: list[Turn]) -> str:
        messages = [{"role": "system", "content": self.system}]
        for turn in turns:
            # The agent's words are what "the other side" says to the caller.
            messages.append({"role": "user" if turn.role == "agent" else "assistant", "content": turn.text})
        if messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "(silence — the agent is waiting for you)"})
        text = await self.chat.complete(messages, effort="none", max_tokens=300)
        return text.strip().strip('"').strip()
