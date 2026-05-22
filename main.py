"""
YouTube Transcript Microservice
Wraps jdepoix/youtube-transcript-api in a tiny FastAPI app.
Deploy free on Vercel (Python serverless) or Railway/Render.

Endpoint:
  POST /transcript
  Body: { "video_id": "dQw4w9WgXcQ" }
  Returns: { "transcript": "full text...", "language": "en", "is_generated": true }
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    RequestBlocked,
    IpBlocked,
    AgeRestricted,
    VideoUnplayable,
)
import re

app = FastAPI(title="YouTube Transcript API", version="1.0.0")

# Allow requests from Cloudflare Workers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


class TranscriptRequest(BaseModel):
    video_id: str  # just the ID, e.g. "dQw4w9WgXcQ"


class TranscriptResponse(BaseModel):
    transcript: str
    language: str
    language_code: str
    is_generated: bool
    word_count: int


@app.get("/")
def root():
    return {"status": "ok", "service": "youtube-transcript-api"}


@app.post("/transcript", response_model=TranscriptResponse)
def get_transcript(req: TranscriptRequest):
    """
    Fetch the full transcript for a YouTube video by ID.
    Tries English manual first, then English auto-generated,
    then any available language.
    """
    video_id = req.video_id.strip()

    # Validate video ID format (11 alphanumeric chars)
    if not re.match(r'^[a-zA-Z0-9_-]{6,20}$', video_id):
        raise HTTPException(status_code=400, detail=f"Invalid video ID format: {video_id}")

    ytt = YouTubeTranscriptApi()

    try:
        # List all available transcripts first
        transcript_list = ytt.list(video_id)

        # Priority: manual English → generated English → manual any → generated any
        fetched = None
        language = "unknown"
        language_code = "unknown"
        is_generated = False

        try:
            t = transcript_list.find_transcript(["en", "en-US", "en-GB"])
            fetched = t.fetch()
            language = t.language
            language_code = t.language_code
            is_generated = t.is_generated
        except NoTranscriptFound:
            pass

        if fetched is None:
            # Try any available transcript
            for t in transcript_list:
                try:
                    fetched = t.fetch()
                    language = t.language
                    language_code = t.language_code
                    is_generated = t.is_generated
                    break
                except Exception:
                    continue

        if fetched is None:
            raise HTTPException(status_code=404, detail="No usable transcript found for this video")

        # Join all snippets into clean plain text
        full_text = " ".join(
            snippet.text.replace("\n", " ").strip()
            for snippet in fetched
            if snippet.text and snippet.text.strip()
        )

        # Collapse multiple spaces
        full_text = re.sub(r" {2,}", " ", full_text).strip()

        if not full_text:
            raise HTTPException(status_code=404, detail="Transcript was empty")

        return TranscriptResponse(
            transcript=full_text,
            language=language,
            language_code=language_code,
            is_generated=is_generated,
            word_count=len(full_text.split()),
        )

    except HTTPException:
        raise  # re-raise our own exceptions as-is

    except TranscriptsDisabled:
        raise HTTPException(status_code=404, detail="Transcripts are disabled for this video")

    except VideoUnavailable:
        raise HTTPException(status_code=404, detail="Video is unavailable or does not exist")

    except AgeRestricted:
        raise HTTPException(status_code=403, detail="Video is age-restricted")

    except (RequestBlocked, IpBlocked):
        raise HTTPException(
            status_code=503,
            detail="YouTube has temporarily blocked this server's IP. Try again later or add a proxy."
        )

    except VideoUnplayable as e:
        raise HTTPException(status_code=404, detail=f"Video is unplayable: {e}")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
