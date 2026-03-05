# BeerRated - iOS / iPad

Deploy BeerRated to an iPhone or iPad.

## Prerequisites

- **macOS** — required for iOS development
- **Python 3.11+**
- **uv** — fast Python package manager ([install](https://astral.sh/uv))
- **briefcase** — `uv tool install briefcase`
- **Xcode** — from the Mac App Store
- **Apple ID** — for device signing
- **OpenAI API key** — needs GPT-4o access (used by the server)

---

## Setup

### 1. Set your OpenAI API key

Create a `.env` file in the project root (already gitignored):

```bash
echo 'OPENAI_API_KEY=sk-your-key-here' > .env
```

### 2. Install server dependencies (one time)

```bash
export PATH="$HOME/.local/bin:$PATH"
uv venv .venv-server
source .venv-server/bin/activate
uv pip install -r requirements-server.txt
deactivate
```

---

## One-Time Xcode Setup

```bash
# Accept Xcode license
sudo xcodebuild -license accept

# Point xcode-select to the full Xcode app
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
# (adjust the path if your Xcode has a different name, e.g. Xcode-26.2.0.app)

# Install iOS simulator runtime (optional, for simulator testing)
xcodebuild -downloadPlatform iOS
```

---

## One-Time iOS Project Setup

```bash
cd /path/to/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase create iOS
briefcase build iOS
```

---

## Running on iPad / iPhone

You need **two terminals** — one for the server, one for deployment.

### Terminal 1 — Start the server

```bash
cd /path/to/beerRatingsMenuOcr
.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888
```

### Terminal 2 — Find your Mac's IP

```bash
ipconfig getifaddr en0
```

Note the IP (e.g. `192.168.86.31`).

### Terminal 2 — Deploy to device

1. Connect your iPad/iPhone via USB
2. Unlock the device and tap **Trust** if prompted

```bash
cd /path/to/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase run iOS -d
```

Briefcase will list connected devices — pick yours. If asked about signing, select your personal Apple ID.

### On the device

1. The app opens to the home screen
2. Tap **Settings** at the bottom
3. Change the server URL to your Mac's IP:
   ```
   http://192.168.86.31:8888
   ```
4. Tap **Save**
5. Tap **Take Photo** and snap a beer menu!

> **Important**: Your iOS device and Mac must be on the same Wi-Fi network.

---

## After Code Changes

To push updated code to your device:

```bash
export PATH="$HOME/.local/bin:$PATH"
briefcase update iOS
briefcase build iOS
briefcase run iOS -d
```

---

## Quick Reference

| Task | Command |
|---|---|
| Start server | `.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888` |
| Create iOS project | `briefcase create iOS` |
| Build iOS | `briefcase build iOS` |
| Run on device | `briefcase run iOS -d` |
| Rebuild after changes | `briefcase update iOS && briefcase build iOS` |
| Find Mac IP | `ipconfig getifaddr en0` |

---

## Troubleshooting

**Xcode license or path errors**
- Run `sudo xcodebuild -license accept`
- Run `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`

**Signing issues**
- Use your personal Apple ID for free development signing
- Free signing requires re-deploying every 7 days

**App can't reach server**
- Use your Mac's local IP (not `localhost`)
- Ensure both devices are on the same Wi-Fi network
- Check that the server is running and bound to `0.0.0.0`
