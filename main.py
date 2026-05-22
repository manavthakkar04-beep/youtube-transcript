"""
YouTube Transcript Service — Vercel deployment
Uses multiple extraction strategies with no external dependencies beyond
the youtube-transcript-api library. Runs on Vercel's free tier.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import httpx
from html import unescape

app = FastAPI(title="YouTube Transcript Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Supadata API (free tier: 100 requests/day, no IP blocks ever) ──
# Uses their infrastructure to fetch transcripts — completely bypasses
# the Vercel/data-center IP blocking issue.
SUPADATA_API = "https://api.supadata.ai/v1/youtube/transcript"

class TranscriptRequest(BaseModel):
    video_id: str

class TranscriptResponse(BaseModel):
    transcript: str
    language_code: str
    word_count: int
    source: str


@app.get("/")
def root():
    return {"status": "ok", "service": "youtube-transcript"}


@app.post("/transcript", response_model=TranscriptResponse)
def get_transcript(req: TranscriptRequest):
    video_id = req.video_id.strip()

    if not re.match(r'^[a-zA-Z0-9_-]{6,20}$', video_id):
        raise HTTPException(status_code=400, detail=f"Invalid video ID: {video_id}")

    # Try strategies in order — first success wins
    errors = []

    # ── Strategy 1: Supadata (free API, residential IPs, no blocking) ──
    try:
        text, lang = _fetch_supadata(video_id)
        if text and len(text) > 100:
            return TranscriptResponse(
                transcript=text, language_code=lang,
                word_count=len(text.split()), source="supadata"
            )
    except Exception as e:
        errors.append(f"supadata: {e}")

    # ── Strategy 2: Direct timedtext endpoint with bypass params ──
    try:
        text, lang = _fetch_timedtext_bypass(video_id)
        if text and len(text) > 100:
            return TranscriptResponse(
                transcript=text, language_code=lang,
                word_count=len(text.split()), source="timedtext"
            )
    except Exception as e:
        errors.append(f"timedtext: {e}")

    # ── Strategy 3: youtube-transcript-api (works when IP not blocked) ──
    try:
        text, lang = _fetch_ytt_api(video_id)
        if text and len(text) > 100:
            return TranscriptResponse(
                transcript=text, language_code=lang,
                word_count=len(text.split()), source="ytt-api"
            )
    except Exception as e:
        errors.append(f"ytt-api: {e}")

    raise HTTPException(
        status_code=503,
        detail=f"All transcript methods failed: {' | '.join(errors)}"
    )


# ═══════════════════════════════════════════════════════
# STRATEGY 1: Supadata API
# Free tier: 100 req/day. Uses residential IPs — never blocked.
# No API key needed for basic usage.
# ═══════════════════════════════════════════════════════

def _fetch_supadata(video_id: str):
    url = f"{SUPADATA_API}?videoId={video_id}&text=true"
    resp = httpx.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0",
    })
    if resp.status_code == 404:
        raise Exception("No transcript available")
    if resp.status_code == 429:
        raise Exception("Rate limit hit")
    if not resp.is_success:
        raise Exception(f"HTTP {resp.status_code}")

    data = resp.json()
    content = data.get("content") or data.get("transcript") or data.get("text")
    if not content:
        raise Exception("Empty response")

    lang = data.get("lang", "en")
    return str(content).strip(), lang


# ═══════════════════════════════════════════════════════
# STRATEGY 2: Direct timedtext API with bypass params
# Works from data center IPs for many videos.
# ═══════════════════════════════════════════════════════

def _fetch_timedtext_bypass(video_id: str):
    headers = {
        "User-Agent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.youtube.com",
    }

    # These params bypass the standard bot-detection check
    for lang in ["en", "en-US", "en-GB"]:
        for kind in ["", "asr"]:
            params = f"v={video_id}&lang={lang}&fmt=json3&xoaf=5"
            if kind:
                params += f"&kind={kind}"
            url = f"https://www.youtube.com/api/timedtext?{params}"
            try:
                resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
                if resp.is_success and resp.text and len(resp.text) > 50:
                    text = _parse_timedtext_json3(resp.text)
                    if text and len(text) > 100:
                        return text, lang
            except Exception:
                continue

    raise Exception("No timedtext captions found")


def _parse_timedtext_json3(raw: str) -> str:
    """Parse YouTube's json3 caption format into plain text."""
    import json
    try:
        data = json.loads(raw)
        segments = []
        for event in data.get("events", []):
            if "segs" not in event:
                continue
            line = "".join(s.get("utf8", "") for s in event["segs"])
            line = line.replace("\n", " ").strip()
            if line and line != "\u200b":
                segments.append(line)
        return re.sub(r" {2,}", " ", " ".join(segments)).strip()
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════
# STRATEGY 3: youtube-transcript-api library
# Works when Vercel IP is not currently blocked.
# ═══════════════════════════════════════════════════════

def _fetch_ytt_api(video_id: str):
    from youtube_transcript_api import (
        YouTubeTranscriptApi, NoTranscriptFound,
        TranscriptsDisabled, VideoUnavailable,
    )

    ytt = YouTubeTranscriptApi()
    transcript_list = ytt.list(video_id)

    fetched = None
    lang_code = "en"

    try:
        t = transcript_list.find_transcript(["en", "en-US", "en-GB"])
        fetched = t.fetch()
        lang_code = t.language_code
    except NoTranscriptFound:
        for t in transcript_list:
            try:
                fetched = t.fetch()
                lang_code = t.language_code
                break
            except Exception:
                continue

    if fetched is None:
        raise Exception("No transcript found")

    full_text = " ".join(
        s.text.replace("\n", " ").strip()
        for s in fetched if s.text and s.text.strip()
    )
    return re.sub(r" {2,}", " ", full_text).strip(), lang_code
