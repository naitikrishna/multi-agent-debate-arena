import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.debater import stream_argument
from agents.judge import stream_verdict

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Multi-Agent Debate System",
    description="Two AI agents debate a topic. A judge declares a winner.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# ── In-memory debate store ────────────────────────────────────────────────────
# debate_id → { topic, num_rounds, transcript, status }
debates: dict[str, dict] = {}


# ── Schemas ───────────────────────────────────────────────────────────────────

class StartDebateRequest(BaseModel):
    topic: str = Field(..., example="AI will replace human creativity")
    num_rounds: int = Field(default=3, ge=1, le=5)


class StartDebateResponse(BaseModel):
    debate_id: str
    topic: str
    num_rounds: int
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_sse(event: str, data: dict | str) -> str:
    """Format a Server-Sent Event string."""
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


import uuid

def new_debate_id() -> str:
    return str(uuid.uuid4())[:8].upper()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.post("/debate/start", response_model=StartDebateResponse)
async def start_debate(req: StartDebateRequest):
    """
    Create a new debate session.
    Returns a debate_id to use in subsequent calls.
    """
    debate_id = new_debate_id()
    debates[debate_id] = {
        "topic": req.topic,
        "num_rounds": req.num_rounds,
        "transcript": [],
        "status": "ready",       # ready | running | judging | done | error
    }
    return StartDebateResponse(
        debate_id=debate_id,
        topic=req.topic,
        num_rounds=req.num_rounds,
        message=f"Debate created. Stream it at GET /debate/{debate_id}/stream",
    )


@app.get("/debate/{debate_id}/stream")
async def stream_debate(debate_id: str):
    """
    SSE endpoint. Streams the full debate round by round, then the verdict.

    Event types:
      - meta         → { debate_id, topic, num_rounds }
      - round_start  → { round, side }
      - token        → "chunk of text..."
      - round_end    → { round, side, argument: full text }
      - judge_start  → {}
      - verdict_token→ "chunk..."
      - verdict_end  → { verdict: full text }
      - done         → { message }
      - error        → { message }
    """
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="Debate not found")

    debate = debates[debate_id]

    if debate["status"] == "running":
        raise HTTPException(status_code=409, detail="Debate already in progress")

    async def event_generator():
        debate["status"] = "running"
        debate["transcript"] = []

        topic = debate["topic"]
        num_rounds = debate["num_rounds"]

        yield make_sse("meta", {
            "debate_id": debate_id,
            "topic": topic,
            "num_rounds": num_rounds,
        })

        try:
            for round_num in range(1, num_rounds + 1):
                for side in ["PRO", "CON"]:
                    yield make_sse("round_start", {"round": round_num, "side": side})

                    # Stream the argument token by token
                    full_argument = ""
                    for chunk in stream_argument(side, topic, debate["transcript"], round_num):
                        full_argument += chunk
                        yield make_sse("token", chunk)
                        await asyncio.sleep(0)   # yield control to event loop

                    # Save completed argument to transcript
                    debate["transcript"].append({
                        "round": round_num,
                        "side": side,
                        "argument": full_argument,
                    })

                    yield make_sse("round_end", {
                        "round": round_num,
                        "side": side,
                        "argument": full_argument,
                    })

            # Judge phase
            debate["status"] = "judging"
            yield make_sse("judge_start", {})

            full_verdict = ""
            for chunk in stream_verdict(topic, debate["transcript"]):
                full_verdict += chunk
                yield make_sse("verdict_token", chunk)
                await asyncio.sleep(0)

            debate["transcript"].append({
                "round": "verdict",
                "side": "JUDGE",
                "argument": full_verdict,
            })

            yield make_sse("verdict_end", {"verdict": full_verdict})
            debate["status"] = "done"
            yield make_sse("done", {"message": "Debate complete"})

        except Exception as e:
            debate["status"] = "error"
            yield make_sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/debate/{debate_id}/transcript")
async def get_transcript(debate_id: str):
    """Get the full transcript of a completed debate."""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="Debate not found")
    return debates[debate_id]


@app.get("/debate/{debate_id}/status")
async def get_status(debate_id: str):
    """Check the current status of a debate."""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="Debate not found")
    d = debates[debate_id]
    return {
        "debate_id": debate_id,
        "status": d["status"],
        "rounds_completed": len([e for e in d["transcript"] if e["side"] != "JUDGE"]) // 2,
        "num_rounds": d["num_rounds"],
    }


@app.delete("/debate/{debate_id}")
async def delete_debate(debate_id: str):
    """Remove a debate session from memory."""
    if debate_id not in debates:
        raise HTTPException(status_code=404, detail="Debate not found")
    del debates[debate_id]
    return {"message": f"Debate {debate_id} deleted"}


@app.get("/debates")
async def list_debates():
    """List all debate sessions."""
    return {
        "debates": [
            {
                "debate_id": did,
                "topic": d["topic"],
                "status": d["status"],
                "num_rounds": d["num_rounds"],
            }
            for did, d in debates.items()
        ]
    }
