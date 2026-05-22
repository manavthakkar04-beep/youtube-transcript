# YouTube Transcript Microservice

Tiny FastAPI wrapper around [jdepoix/youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api).
Deploys **free on Vercel** — no credit card needed.

## Deploy on Vercel (2 minutes)

### Step 1: Push code to GitHub
1. Create new GitHub repo: [github.com/new](https://github.com/new)
   - Name: `second-brain-transcript`
   - Public repo
2. Upload these files to the repo:
   - `main.py`
   - `requirements.txt`
   - `vercel.json`
   - `.gitignore`

### Step 2: Deploy on Vercel
1. Go to [vercel.com](https://vercel.com)
2. Click **Sign Up → Sign up with GitHub**
3. Click **Import Project → GitHub**
4. Find and select `second-brain-transcript` repo
5. Click **Import**
6. Vercel auto-detects Python and deploys
7. Copy your URL: `https://second-brain-transcript.vercel.app`

**That's it!** Vercel automatically redeploys whenever you push to GitHub.

## API

### POST /transcript

**Request:**
```json
{ "video_id": "dQw4w9WgXcQ" }
```

**Response (200 OK):**
```json
{
  "transcript": "full plain text transcript...",
  "language": "English",
  "language_code": "en",
  "is_generated": true,
  "word_count": 4821
}
```

**Error Responses:**
- 404: Video has no captions
- 403: Age-restricted video
- 503: YouTube IP blocked

## Local Testing

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Then test:
```bash
curl -X POST http://localhost:8000/transcript \
  -H "Content-Type: application/json" \
  -d '{"video_id": "dQw4w9WgXcQ"}'
```

## Free Tier (Vercel)

- **Bandwidth:** 100GB/month
- **Compute time:** Unlimited function executions
- **No credit card needed**
- **No cold start penalties**
- **Automatic scaling**

## Cost: $0/month

Completely free with Vercel's generous free tier.
