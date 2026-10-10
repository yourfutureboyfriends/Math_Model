"""AI research assistant (api/ai/assistant.py): answers from the terminal's own data via tools."""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["ai"])


class Msg(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: List[Msg]
    context: Optional[str] = None
    model: Optional[str] = None


@router.get("/api/v1/ai/status")
async def ai_status():
    from api.ai import assistant
    cfg = await asyncio.to_thread(assistant.config)
    return {k: v for k, v in cfg.items() if k not in ("key", "base_url")} | {"tools": list(assistant.TOOLS)}


@router.post("/api/v1/ai/chat")
async def ai_chat(body: ChatIn, request: Request):
    from api.ai import assistant
    from api.core.access import require_roles
    require_roles(request, {"pm", "quant", "analyst", "risk"})
    if not body.messages or body.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be from the user.")
    try:
        return await asyncio.wait_for(asyncio.to_thread(assistant.chat, [m.model_dump() for m in body.messages], body.context, body.model),
                                      timeout=600)
    except asyncio.TimeoutError:
        raise HTTPException(504, "The model took too long — try the fast model or a narrower question.")
    except RuntimeError as e:
        raise HTTPException(503, str(e))
