"""
CAPI Relay API — Forwards lead events to Meta's Conversions API server-side.

This is separate from the main ads automation backend so it can be deployed
independently (e.g. on Fly.io, Render, or Railway alongside the landing page).
"""

import hashlib
import time
import uuid
import logging
import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Meta CAPI Relay", docs_url=None, redoc_url=None)

# ── CORS — restrict to your landing page domain in production ─────────────────
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

# ── Config ────────────────────────────────────────────────────────────────────
PIXEL_ID        = os.getenv("META_PIXEL_ID")
ACCESS_TOKEN    = os.getenv("META_CAPI_ACCESS_TOKEN")   # System user / CAPI token
TEST_EVENT_CODE = os.getenv("META_TEST_EVENT_CODE", "") # From Events Manager test tool
FB_API_VERSION  = "v19.0"
CAPI_URL        = f"https://graph.facebook.com/{FB_API_VERSION}/{PIXEL_ID}/events"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha256(value: str) -> str:
    """Hash a PII field with SHA-256 as required by Meta."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()

def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


# ── Request schema ────────────────────────────────────────────────────────────

class LeadPayload(BaseModel):
    event_id: str = Field(default_factory=lambda: "evt_" + str(uuid.uuid4()))
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    company: Optional[str] = None
    monthly_spend: Optional[str] = None
    source_url: Optional[str] = None
    user_agent: Optional[str] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.post("/capi/lead")
async def capi_lead(payload: LeadPayload, request: Request):
    """
    Receive a lead event from the landing page and forward it to Meta CAPI.

    Uses the same event_id the pixel fired client-side so Meta can deduplicate
    and count it as a single conversion rather than two.
    """
    if not PIXEL_ID or not ACCESS_TOKEN:
        raise HTTPException(status_code=500, detail="CAPI not configured — check META_PIXEL_ID and META_CAPI_ACCESS_TOKEN env vars")

    # Build user data (all PII must be pre-hashed)
    user_data: dict = {
        "client_ip_address": request.client.host,
        "client_user_agent": payload.user_agent or request.headers.get("user-agent", ""),
    }
    if payload.email:
        user_data["em"] = [_sha256(payload.email)]
    if payload.first_name:
        user_data["fn"] = [_sha256(payload.first_name)]
    if payload.last_name:
        user_data["ln"] = [_sha256(payload.last_name)]
    if payload.phone:
        user_data["ph"] = [_sha256(_normalize_phone(payload.phone))]

    # Build the event
    event = {
        "event_name": "Lead",
        "event_time": int(time.time()),
        "event_id": payload.event_id,          # Deduplication key — matches pixel's eventID
        "event_source_url": payload.source_url or "",
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "content_name": "strategy_session",
            "company": payload.company or "",
            "monthly_spend": payload.monthly_spend or "",
        },
    }

    body: dict = {
        "data": [event],
        "access_token": ACCESS_TOKEN,
    }

    # Include test event code when testing via Events Manager
    if TEST_EVENT_CODE:
        body["test_event_code"] = TEST_EVENT_CODE

    logger.info(f"Forwarding CAPI Lead event | event_id={payload.event_id} | email={'yes' if payload.email else 'no'}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(CAPI_URL, json=body)

    if not response.is_success:
        logger.error(f"Meta CAPI error: {response.status_code} — {response.text}")
        raise HTTPException(status_code=502, detail=f"Meta CAPI returned {response.status_code}")

    result = response.json()
    logger.info(f"Meta CAPI response: events_received={result.get('events_received')}, fbe={result.get('fbe_info')}")

    return {"success": True, "events_received": result.get("events_received", 0)}


@app.get("/health")
async def health():
    return {"status": "ok", "pixel_configured": bool(PIXEL_ID)}
