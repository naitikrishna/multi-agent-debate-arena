from groq import Groq
import os

client = Groq(api_key=os.environ.get("GROQ_API_KEY", "your-key-here"))
JUDGE_MODEL = "llama-3.3-70b-versatile"


def stream_verdict(topic: str, transcript: list):
    """
    Generator that streams the judge's verdict after all rounds complete.
    Yields text chunks.
    """
    formatted = "\n\n".join(
        f"[Round {e['round']} | {e['side']}]:\n{e['argument']}"
        for e in transcript
    )

    prompt = f"""You are an impartial debate judge. Evaluate the following debate objectively.

Topic: "{topic}"

--- FULL TRANSCRIPT ---
{formatted}
--- END TRANSCRIPT ---

Evaluate both sides on these criteria:
1. Logic & reasoning
2. Use of evidence / examples
3. Effectiveness of rebuttals
4. Clarity and persuasiveness

Then declare a winner (PRO or CON) and explain your decision in 4-5 sentences.
Format:
SCORES:
PRO: X/10
CON: X/10

WINNER: [PRO/CON]

REASONING: [Your explanation]"""

    stream = client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
