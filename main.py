"""
YouTube Transcript Service — Vercel deployment with residential proxy.
Uses Webshare.io free residential proxies to bypass YouTube IP blocks.

Setup:
1. Sign up at webshare.io (free, no credit card)
2. Go to Proxy > List > copy any proxy in format ip:port:user:pass
3. Set PROXY_URL env var in Vercel dashboard
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import (
    YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled,
    VideoUnavailable, RequestBlocked, IpBlocked, AgeRestricted, VideoUnplayable,
)
from youtube_transcript_api.proxies import ProxyConfig
import re, os

app = FastAPI(title="YouTube Transcript Service")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class TranscriptRequest(BaseModel):
    video_id: str

class TranscriptResponse(BaseModel):
    transcript: str
    language: str
    language_code: str
    is_generated: bool
    word_count: int

@app.get("/")
def root():
    return {"status": "ok", "proxy": "configured" if os.environ.get("PROXY_URL") else "not set"}

@app.post("/transcript", response_model=TranscriptResponse)
def get_transcript(req: TranscriptRequest):
    video_id = req.video_id.strip()
    if not re.match(r'^[a-zA-Z0-9_-]{6,20}$', video_id):
        raise HTTPException(status_code=400, detail=f"Invalid video ID: {video_id}")

    proxy_url = os.environ.get("PROXY_URL", "")

    # Try with proxy first (residential IP), then without
    attempts = []
    if proxy_url:
        attempts.append(("proxy", proxy_url))
    attempts.append(("direct", None))

    last_error = None

    for method, proxy in attempts:
        try:
            if proxy:
                proxy_config = ProxyConfig(
                    proxies={"https": proxy, "http": proxy},
                    retries_when_blocked=2,
                )
                ytt = YouTubeTranscriptApi(proxy_config=proxy_config)
            else:
                ytt = YouTubeTranscriptApi()

            transcript_list = ytt.list(video_id)
            fetched, language, language_code, is_generated = None, "unknown", "unknown", False

            try:
                t = transcript_list.find_transcript(["en", "en-US", "en-GB"])
                fetched = t.fetch()
                language, language_code, is_generated = t.language, t.language_code, t.is_generated
            except NoTranscriptFound:
                pass

            if fetched is None:
                for t in transcript_list:
                    try:
                        fetched = t.fetch()
                        language, language_code, is_generated = t.language, t.language_code, t.is_generated
                        break
                    except:
                        continue

            if fetched is None:
                raise HTTPException(status_code=404, detail="No transcript found for this video")

            full_text = " ".join(
                s.text.replace("\n", " ").strip()
                for s in fetched if s.text and s.text.strip()
            )
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
            raise

        except TranscriptsDisabled:
            raise HTTPException(status_code=404, detail="Transcripts are disabled for this video")

        except VideoUnavailable:
            raise HTTPException(status_code=404, detail="Video unavailable")

        except AgeRestricted:
            raise HTTPException(status_code=403, detail="Age-restricted video")

        except (RequestBlocked, IpBlocked) as e:
            last_error = f"{method}: IP blocked"
            continue

        except Exception as e:
            last_error = f"{method}: {str(e)}"
            continue

    raise HTTPException(status_code=503, detail=f"All methods failed. Last error: {last_error}")
