from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()   # reads .env file in the project root

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError(
        "GROQ_API_KEY not found. Create a .env file with GROQ_API_KEY=your_key "
        "or run: export GROQ_API_KEY=your_key"
    )

client = Groq(api_key=api_key)
MODEL = "llama-3.3-70b-versatile"


def build_messages(role: str, topic: str, transcript: list, round_num: int) -> list:
    """Convert transcript history into alternating user/assistant messages for the debater."""
    opponent = "CON" if role == "PRO" else "PRO"
    messages = []

    for entry in transcript:
        if entry["side"] == role:
            messages.append({"role": "assistant", "content": entry["argument"]})
        else:
            messages.append({"role": "user", "content": f"[Opponent - {opponent}]: {entry['argument']}"})

    # If no history yet, seed with the opening prompt
    if not messages:
        messages.append({
            "role": "user",
            "content": f"Begin the debate. Make your opening argument for Round {round_num}."
        })
    else:
        messages.append({
            "role": "user",
            "content": f"Now make your Round {round_num} argument. Rebut the opponent's last point."
        })

    return messages


def stream_argument(role: str, topic: str, transcript: list, round_num: int):
    """
    Generator that yields text chunks for a debater's argument.
    Yields strings — call with `for chunk in stream_argument(...)`
    """
    system_prompt = f"""You are an expert debater. Your assigned position is: {role}.
Topic: "{topic}"
Round: {round_num} of the debate.

Rules:
- Stay firmly in your assigned position ({role}) regardless of the strength of opposing arguments.
- Be concise: 3-5 sentences max per response.
- Rebut the opponent's most recent point directly if one exists.
- Use logical reasoning and vivid examples.
- Do NOT switch sides or acknowledge your position is wrong."""

    messages = build_messages(role, topic, transcript, round_num)

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt}] + messages,
        max_tokens=250,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
