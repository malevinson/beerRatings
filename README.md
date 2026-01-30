# Beer Menu Scanner

Snap a photo of a beer menu and get instant ratings, styles, and details for every beer — powered by GPT-4o Vision.

## Architecture

```
┌─────────────────┐         HTTP          ┌──────────────────┐
│  iPad/Mac App    │  ──── image ────▶    │  server.py       │
│  (Toga UI)       │  ◀── JSON beers ──   │  (runs on Mac)   │
│                  │                      │  OpenAI GPT-4o   │
└─────────────────┘                       └──────────────────┘
```

The app itself has zero compiled dependencies (runs on iOS). All OpenAI calls happen on the server running on your Mac.

---

## Prerequisites

- **Python 3.11+** (you likely already have this)
- **uv** — fast Python package manager
- **Xcode** — required for iPad deployment (Mac App Store)
- **OpenAI API key** — needs GPT-4o access

### Install uv (one time)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
```

### Install briefcase (one time)

```bash
uv tool install briefcase
```

---

## Setup

### 1. Clone / navigate to the project

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
```

### 2. Set your OpenAI API key

Create a `.env` file in the project root (already gitignored):

```bash
echo 'OPENAI_API_KEY=sk-your-key-here' > .env
```

### 3. Install server dependencies (one time)

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv .venv-server
source .venv-server/bin/activate
uv pip install -r requirements-server.txt
deactivate
```

---

## Running in Dev Mode (Mac Desktop)

You need **two terminals** — one for the server, one for the app.

### Terminal 1 — Start the server

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8888
```

### Terminal 2 — Start the app

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"
briefcase dev
```

A native macOS window opens. Click **"Select from Library"** and pick a photo of a beer menu.

### Stopping

- **App**: Close the window, `Cmd+Q`, or `Ctrl+C` in Terminal 2
- **Server**: `Ctrl+C` in Terminal 1

### Debug mode (skip file picker)

Place a test image at `src/beerratingsmenuocr/resources/test_menu.jpg`, then:

```bash
DEBUG_MODE=1 briefcase dev
```

A **[DEBUG] Use Test Image** button appears on the home screen.

---

## Running on iPad

### One-time Xcode setup

```bash
# Accept Xcode license
sudo xcodebuild -license accept

# Point xcode-select to the full Xcode app
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
# (adjust the path if your Xcode has a different name, e.g. Xcode-26.2.0.app)

# Install iOS simulator runtime (optional, for simulator testing)
xcodebuild -downloadPlatform iOS
```

### One-time iOS project creation

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase create iOS
briefcase build iOS
```

### Deploying to iPad

You need **two terminals** — one for the server, one for deployment.

#### Terminal 1 — Start the server

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888
```

#### Terminal 2 — Find your Mac's IP

```bash
ipconfig getifaddr en0
```

Note the IP (e.g. `192.168.86.31`).

#### Terminal 2 — Deploy to iPad

1. Connect your iPad via USB
2. Unlock the iPad and tap **Trust** if prompted

```bash
cd /Users/mattlevinson/myProjects/iPhoneApps/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase run iOS -d
```

Briefcase will list connected devices — pick your iPad. If asked about signing, select your personal Apple ID.

#### On the iPad

1. The app opens to the home screen
2. Tap **Settings** at the bottom
3. Change the server URL to your Mac's IP:
   ```
   http://192.168.86.31:8888
   ```
4. Tap **Save**
5. Tap **Take Photo** and snap a beer menu!

> **Important**: Your iPad and Mac must be on the same Wi-Fi network.

### After code changes

To push updated code to the iPad:

```bash
export PATH="$HOME/.local/bin:$PATH"
briefcase update iOS
briefcase build iOS
briefcase run iOS -d
```

---

## Project Structure

```
beerRatingsMenuOcr/
├── .env                          # OpenAI API key (gitignored)
├── pyproject.toml                # Briefcase config + app metadata
├── requirements-server.txt       # Server-side Python deps
├── server.py                     # FastAPI server (OpenAI calls happen here)
├── src/beerratingsmenuocr/
│   ├── app.py                    # Main Toga app (views, event handlers)
│   ├── ai_agent.py               # HTTP client → sends images to server
│   ├── ui_components.py          # UI builders (home, settings, results cards)
│   ├── models.py                 # Pydantic models (server-side only)
│   └── resources/                # App icons, test images
└── build/                        # Generated by briefcase (gitignored)
```

---

## Quick Reference

| Task | Command |
|---|---|
| Start server | `.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888` |
| Run app (Mac) | `briefcase dev` |
| Run app (iPad) | `briefcase run iOS -d` |
| Rebuild after code changes | `briefcase update iOS && briefcase build iOS` |
| Update server deps | `source .venv-server/bin/activate && uv pip install -r requirements-server.txt` |
| Update app deps | `briefcase dev --update-requirements` |
| Find Mac IP | `ipconfig getifaddr en0` |

---

## Rating Tiers (color-coded in results)

| BA Score | Tier | Color |
|---|---|---|
| 92+ | TOP TIER | Gold |
| 85–91 | GREAT | Green |
| 75–84 | GOOD | Blue |
| 65–74 | AVERAGE | Gray |
| <65 | BELOW AVG | Red |
