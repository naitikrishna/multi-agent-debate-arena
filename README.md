# Multi-agent-debate-arena

LLMs are good at arguing. This project pits two of them against each other.

Give it a topic. PRO argues for it, CON argues against it, a judge scores the full transcript and picks a winner. Arguments stream word by word so you can watch them think in real time — no waiting for a round to finish before the next one starts.

Built as a portfolio project to explore multi-agent orchestration, streaming APIs, and how prompt engineering alone can give distinct personalities to the same underlying model.

---

## What it does

You type any topic — "remote work is better than office work", "tabs vs spaces", "Virat Kohli vs Rohit Sharma" — and the system runs a structured debate:

- **PRO agent** opens with an argument for the topic
- **CON agent** rebuts directly, then makes its own case
- This repeats for however many rounds you pick (1–5)
- **Judge agent** reads the entire transcript and scores both sides on logic, evidence quality, rebuttal effectiveness, and clarity — then declares a winner with reasoning

Every token streams live to the browser. You can see the model mid-sentence, which makes it feel like watching two people actually think through a problem.

---

## Why these tools

**FastAPI** over Flask because it handles async generators natively, which is exactly what SSE streaming needs. With Flask you'd need workarounds; with FastAPI `StreamingResponse` wraps a Python generator directly.

**Groq** over OpenAI because the inference speed is noticeably faster for a streaming use case — slower generation breaks the "live" feel. The free tier is also generous enough to run this without a credit card.

**SSE over WebSockets** because the communication here is one-directional — server pushes tokens, browser just displays them. WebSockets add handshake complexity for no benefit when you don't need the browser to push data back mid-stream.

**No frontend framework** because the UI is simple enough that React would add build tooling overhead for zero gain. The whole frontend is one HTML file with about 150 lines of JS.

---

## How the agents work

All three agents are the same model (`llama-3.3-70b-versatile`) with different system prompts and different views of conversation history.

The key design decision is how history is passed to each debater. PRO sees its own past arguments as `assistant` messages and CON's arguments as `user` messages — and CON sees the mirror image. This means each agent experiences the debate from its own perspective, which keeps it in character and makes rebuttals feel direct rather than generic.

```python
for entry in transcript:
    if entry["side"] == role:
        messages.append({"role": "assistant", "content": entry["argument"]})
    else:
        messages.append({"role": "user", "content": f"[Opponent]: {entry['argument']}"})
```

The judge gets the full transcript formatted as a single prompt — no role-playing, just evaluation. It's instructed to score before concluding, which forces it to actually weigh both sides rather than defaulting to whoever argued last.

The orchestrator in `app.py` manages turn order, feeds each agent the right slice of history, accumulates the transcript, and finally hands everything to the judge.

---

## Stack

- **Backend** — FastAPI, Python 3.10+
- **Streaming** — Server-Sent Events via `StreamingResponse`
- **LLM** — Groq API (`llama-3.3-70b-versatile` for all three agents)
- **Frontend** — Vanilla HTML/CSS/JS, `EventSource` API
- **Config** — `python-dotenv` for API key management

---

## How to run it

```bash
git clone https://github.com/yourname/debate-arena
cd debate-arena

python -m venv venv
venv\Scripts\activate        # windows
source venv/bin/activate     # mac/linux

pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com) — no credit card needed.

```bash
uvicorn app:app --reload --port 8000
```

Open `http://localhost:8000`. Auto-generated API docs at `http://localhost:8000/docs`.

---

## Endpoints

```
POST   /debate/start               create a session, returns debate_id
GET    /debate/{id}/stream         SSE stream — tokens, round events, verdict
GET    /debate/{id}/transcript     full transcript after completion
GET    /debate/{id}/status         current round, status (running/done/error)
DELETE /debate/{id}                remove session from memory
GET    /debates                    list all active sessions
```

### Example

```bash
curl -X POST http://localhost:8000/debate/start \
  -H "Content-Type: application/json" \
  -d '{"topic": "Python is better than JavaScript", "num_rounds": 3}'
```

```json
{
  "debate_id": "A3F9C1",
  "topic": "Python is better than JavaScript",
  "num_rounds": 3,
  "message": "Debate created. Stream it at GET /debate/A3F9C1/stream"
}
```

### SSE event flow

```
meta → round_start → token token token ... → round_end
     → round_start → token token token ... → round_end   (x N rounds)
     → judge_start → verdict_token ...     → verdict_end
     → done
```

---

## Project Structure

```
├── app.py              FastAPI app — all routes and the orchestrator loop
├── agents/
│   ├── debater.py      PRO / CON agent — streaming generator, history builder
│   └── judge.py        judge agent — scores transcript, declares winner
├── static/
│   └── index.html      frontend — chat-style UI, EventSource listener
├── .env                API key (not committed)
└── requirements.txt
```

---

## Limitations

- Sessions live in memory — restarting the server clears everything
- No persistence, no database, no auth
- One debate per ID can run at a time — starting the same ID twice returns 409
- Model occasionally breaks character on very short `max_tokens` limits — increase to 350+ if arguments feel cut off

---
