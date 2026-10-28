"""Funds: list the ones you can open, create one (each gets its own database), manage its name and members."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["funds"])


class FundIn(BaseModel):
    """A new fund: id, name, members and initial settings."""
    id: str = Field(..., max_length=24)
    name: str = Field(..., max_length=80)
    members: Optional[List[str]] = None
    base_currency: Optional[str] = Field(None, max_length=3)
    benchmark: Optional[str] = Field(None, max_length=12)
    capital: Optional[float] = Field(None, gt=0)
    fund_name: Optional[str] = Field(None, max_length=80)


class FundUpdate(BaseModel):
    """A fund's new name and / or members."""
    name: Optional[str] = Field(None, max_length=80)
    members: Optional[List[str]] = None


@router.get("/api/v1/funds")
async def funds_list(request: Request):
    """The funds you can open and which one this request works on (X-Fund header)."""
    from api import fund_store, funds
    from api.core.access import require_roles
    u = require_roles(request, {"pm", "analyst", "risk", "quant"})
    rows = await asyncio.to_thread(funds.visible_to, u)
    out = []
    for f in rows:
        tok = funds.CURRENT.set(f["id"])
        try:
            st = await asyncio.to_thread(fund_store.get_settings)
        finally:
            funds.CURRENT.reset(tok)
        out.append({**f, "base_currency": st.get("base_currency"), "benchmark": st.get("benchmark"),
                    "fund_name": st.get("fund_name"), "capital": st.get("capital"),
                    "members": f["members"] if u.get("role") == "admin" else None,
                    "logo": _logo_path(f["id"], "full").exists(), "logo_mark": _logo_path(f["id"], "mark").exists(),
                    "logo_masks": _logo_path(f["id"], "mark_mask").exists() and _logo_path(f["id"], "word_mask").exists(),
                    "brand": st.get("brand"), "logo_version": _logo_version(f["id"])})
    return {"funds": out, "current": funds.current()}


@router.post("/api/v1/funds")
async def funds_create(body: FundIn, request: Request):
    """A new fund with its own database; its settings (base currency, benchmark, capital) start from the body."""
    from api import funds, audit_store
    from api.core.access import require_roles
    u = require_roles(request, {"pm"})
    settings: Dict[str, Any] = {k: v for k, v in {"base_currency": (body.base_currency or "").upper() or None,
                                                  "benchmark": (body.benchmark or "").upper() or None,
                                                  "capital": body.capital, "fund_name": body.fund_name or body.name}.items()
                                if v is not None}
    if "benchmark" in settings:
        from api.calculations.benchmark import BENCHMARKS
        if settings["benchmark"] not in BENCHMARKS:
            raise HTTPException(400, f"benchmark must be one of {', '.join(BENCHMARKS)}")
    try:
        f = await asyncio.to_thread(funds.create, body.id, body.name, u["username"], body.members, settings)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(lambda: audit_store.add_decision("fund_created", f"Fund '{f['name']}' ({f['id']}) created",
                                                              user=u["username"], target=f"fund:{f['id']}", after_state=f))
    return f


@router.put("/api/v1/funds/{fund_id}")
async def funds_update(fund_id: str, body: FundUpdate, request: Request):
    """Rename a fund or set who may open it (admin)."""
    from api import funds
    from api.core.access import require_roles
    require_roles(request, set())                                # admin only
    try:
        return await asyncio.to_thread(funds.update, fund_id, body.name, body.members)
    except LookupError as e:
        raise HTTPException(404, str(e))


# ── logos ────────────────────────────────────────────────────────────────────
# Each fund's logo (full lock-up) and mark (small emblem for the top bar), stored beside the fund databases
# (api/funds/logos/, not in the repository). Uploads are re-encoded as PNG by Pillow (nothing else in the file is kept).
LOGO_VARIANTS = ("full", "mark", "mark_mask", "word_mask")    # *_mask: white shapes on transparent, drawn
                                                               # in the theme's colours (CSS mask) by the app
MAX_LOGO_BYTES = 2_000_000


def _logo_path(fund_id: str, variant: str):
    from api import funds
    if not funds.ID_RE.match(fund_id) and fund_id != funds.MAIN:
        raise HTTPException(400, "invalid fund id")
    if variant not in LOGO_VARIANTS:
        raise HTTPException(400, f"variant is one of {', '.join(LOGO_VARIANTS)}")
    return funds.FUNDS_DIR / "logos" / (f"{fund_id}.png" if variant == "full" else f"{fund_id}_{variant}.png")


def _logo_version(fund_id: str) -> int:
    """Changes whenever any of the fund's logo files changes (cache-busting for the app)."""
    ts = [int(_logo_path(fund_id, v).stat().st_mtime) for v in LOGO_VARIANTS if _logo_path(fund_id, v).exists()]
    return max(ts) if ts else 0


def save_logo(fund_id: str, variant: str, data: bytes) -> dict:
    """Validate an uploaded logo (PNG / JPEG / WebP, under 2 MB), normalise it to RGBA PNG and store it as the fund's
    `variant`.

    Raises:
        ValueError: the file is too large, not an image, or an unsupported format.
    """
    import io
    from PIL import Image
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError("the logo must be under 2 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:                                                          # noqa: BLE001 — not an image
        raise ValueError("not a PNG / JPEG image")
    if img.format not in ("PNG", "JPEG", "WEBP"):
        raise ValueError("use a PNG, JPEG or WebP image")
    img = img.convert("RGBA")
    if max(img.size) > 1200:
        img.thumbnail((1200, 1200))
    p = _logo_path(fund_id, variant)
    p.parent.mkdir(parents=True, exist_ok=True)
    img.save(p, "PNG", optimize=True)
    return {"fund": fund_id, "variant": variant, "size": list(img.size)}


class LogoIn(BaseModel):
    """A logo upload: variant and the image as base64."""
    variant: str = Field("full", pattern="^(full|mark|mark_mask|word_mask)$")
    data_base64: str = Field(..., max_length=3_000_000)


@router.get("/api/v1/funds/{fund_id}/logo")
async def funds_logo(fund_id: str, request: Request, variant: str = "full"):
    """The fund's logo as PNG (the mark falls back to the full logo); 404 when none is set."""
    from fastapi.responses import FileResponse
    from api import funds
    from api.core.access import current_user
    u = current_user(request)
    f = await asyncio.to_thread(funds.get, fund_id)
    if not u or not f or not funds.can_open(u, f):
        raise HTTPException(404, "no logo")
    for v in ((variant, "full") if variant == "mark" else (variant,)):
        p = _logo_path(fund_id, v)
        if p.exists():
            return FileResponse(p, media_type="image/png", headers={"Cache-Control": "private, no-cache"})  # ETag revalidation
    raise HTTPException(404, "no logo")


@router.put("/api/v1/funds/{fund_id}/logo")
async def funds_logo_set(fund_id: str, body: LogoIn, request: Request):
    """Set a fund's logo or mark (admin): a base64 PNG / JPEG / WebP."""
    import base64
    from api import audit_store, funds
    from api.core.access import require_roles
    u = require_roles(request, set())
    if not await asyncio.to_thread(funds.get, fund_id):
        raise HTTPException(404, "fund not found")
    try:
        raw = base64.b64decode(body.data_base64.split(",", 1)[-1], validate=False)
        r = await asyncio.to_thread(save_logo, fund_id, body.variant, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await asyncio.to_thread(lambda: audit_store.add_decision("fund_logo_set", f"Logo ({body.variant}) set for fund {fund_id}",
                                                              user=u["username"], target=f"fund:{fund_id}"))
    return r
