# TapLens — Server Deployment

The TapLens server is a FastAPI app (`server.py`) that handles menu OCR and beer rating lookups via Gemini.

## Local Development

```bash
# Install dependencies
pip install -r requirements-server.txt

# Create .env with your OpenAI key
echo "OPENAI_API_KEY=sk-..." > .env

# Run the server
uvicorn server:app --host 0.0.0.0 --port 8888
```

The app uses `LOCAL_IP` in `src/beerratingsmenuocr/ai_agent.py` to connect. Update this to your Mac's local IP if it changes:

```python
LOCAL_IP = "192.168.86.31"
```

Find your IP with `ipconfig getifaddr en0` (Mac) or `hostname -I` (Linux).

## Deploy to Production (Railway)

1. Create a [Railway](https://railway.app) account and new project
2. Connect your GitHub repo (or use `railway up` CLI)
3. Add environment variable: `OPENAI_API_KEY=sk-...`
4. Railway auto-detects the `Procfile` and `requirements-server.txt`
5. After deploy, grab your public URL (e.g. `https://taplens-production.up.railway.app`)

### Point the app at production

In `src/beerratingsmenuocr/ai_agent.py`, change:

```python
DEFAULT_SERVER_URL = f"http://{LOCAL_IP}:8888"
```

to:

```python
DEFAULT_SERVER_URL = "https://your-railway-url.up.railway.app"
```

Then rebuild the app (`briefcase update android && briefcase build android`).

## Other Hosting Options

The server works on any platform that runs Python + uvicorn:

| Platform | Notes |
|----------|-------|
| **Railway** | Easiest — auto-detects Procfile, free tier available |
| **Render** | Similar to Railway, uses Procfile |
| **Fly.io** | Needs a `fly.toml` config, good free tier |
| **Heroku** | Uses Procfile, no free tier |
| **VPS** | Run uvicorn behind nginx with systemd |

All platforms need the `OPENAI_API_KEY` environment variable set.

## Server Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/analyze` | POST | Combined OCR + ratings (multipart image) |
| `/ocr` | POST | Menu OCR only (multipart image) |
| `/rate` | POST | Rate a single beer (JSON body) |
| `/annotate` | POST | Annotate menu image with numbered markers (JSON body) |

## Files

- `server.py` — FastAPI app with all endpoints
- `Procfile` — Process command for cloud platforms
- `requirements-server.txt` — Python dependencies
- `.env` — OpenAI API key (not committed)
