from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException

from api.routes.agent import generate_followup
from api.schemas import FollowUpAgentResponse, LeadPayload

load_dotenv()

app = FastAPI(title="Smart Follow-up Agent", version="0.1.0")


@app.post("/agent/follow-up", response_model=FollowUpAgentResponse)
async def post_follow_up(payload: LeadPayload) -> FollowUpAgentResponse:
    """Accept a lead payload and return a follow-up draft from your AI Foundry deployment."""
    try:
        return await generate_followup(payload)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
