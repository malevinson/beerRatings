# Beer Menu Scanner - Android

Deploy the Beer Menu Scanner to an Android phone or tablet.

## Prerequisites

- **Python 3.11+**
- **uv** — fast Python package manager ([install](https://astral.sh/uv))
- **briefcase** — `uv tool install briefcase`
- **Android Studio** — required for Android SDK and emulator
- **Java 17+** — required by the Android build tools
- **OpenAI API key** — needs GPT-4o access (used by the server)

### Install Android Studio (one time)

Download from [developer.android.com/studio](https://developer.android.com/studio). During setup, install:

- Android SDK
- Android SDK Platform-Tools
- Android Emulator (if you want to test without a device)

Briefcase will automatically download any additional SDK components it needs on first build.

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

## One-Time Android Project Setup

```bash
cd /path/to/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase create android
briefcase build android
```

This downloads the Android SDK components (first run takes a few minutes) and generates the Gradle project under `build/beerratingsmenuocr/android/`.

---

## Running on Android Emulator

You need **two terminals** — one for the server, one for the app.

### Terminal 1 — Start the server

```bash
cd /path/to/beerRatingsMenuOcr
.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888
```

### Terminal 2 — Launch the emulator

```bash
cd /path/to/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase run android
```

Briefcase will list available emulators — pick one (or it will create a default).

### Configure the server URL

1. In the app, tap **Settings**
2. Set the server URL to `http://10.0.2.2:8888`
   - `10.0.2.2` is the Android emulator's alias for your host machine's `localhost`
3. Tap **Save**

> **Note**: The emulator camera is simulated. Use **Select from Library** with a test image for best results.

---

## Running on a Physical Device

### Enable USB debugging on your Android device

1. Go to **Settings > About phone**
2. Tap **Build number** 7 times to enable Developer options
3. Go to **Settings > Developer options**
4. Enable **USB debugging**

### Deploy

You need **two terminals** — one for the server, one for the app.

#### Terminal 1 — Start the server

```bash
cd /path/to/beerRatingsMenuOcr
.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888
```

#### Terminal 2 — Find your server IP

```bash
# Mac
ipconfig getifaddr en0

# Windows
ipconfig | findstr IPv4

# Linux
hostname -I
```

Note the IP (e.g. `192.168.86.31`).

#### Terminal 2 — Deploy to device

1. Connect your Android device via USB
2. Accept the USB debugging prompt on the device
3. Find your device name:

```bash
adb devices
```

4. Run the app on your device:

```bash
cd /path/to/beerRatingsMenuOcr
export PATH="$HOME/.local/bin:$PATH"

briefcase run android -d "YOUR_DEVICE_NAME"
```

Replace `YOUR_DEVICE_NAME` with the device ID from `adb devices` (e.g. `Pixel_7`).

#### On the device

1. The app opens to the home screen
2. Tap **Settings**
3. Set the server URL to your machine's IP:
   ```
   http://192.168.86.31:8888
   ```
4. Tap **Save**
5. Tap **Take Photo** and snap a beer menu!

> **Important**: Your Android device and server must be on the same Wi-Fi network.

---

## After Code Changes

To push updated code to Android:

```bash
export PATH="$HOME/.local/bin:$PATH"
briefcase update android
briefcase build android
briefcase run android                    # emulator
briefcase run android -d "DEVICE_NAME"   # physical device
```

---

## Quick Reference

| Task | Command |
|---|---|
| Start server | `.venv-server/bin/uvicorn server:app --host 0.0.0.0 --port 8888` |
| Create Android project | `briefcase create android` |
| Build Android | `briefcase build android` |
| Run on emulator | `briefcase run android` |
| Run on device | `briefcase run android -d "DEVICE_NAME"` |
| Rebuild after changes | `briefcase update android && briefcase build android` |

---

## Troubleshooting

**"SDK not found" or Java errors**
- Ensure Android Studio is installed and the SDK path is set
- Briefcase auto-detects the SDK; if not, set `ANDROID_HOME` environment variable

**App can't reach server**
- Emulator: use `http://10.0.2.2:8888` (not `localhost`)
- Physical device: use your machine's local IP, not `localhost`
- Ensure both are on the same Wi-Fi network
- Check that the server is running and bound to `0.0.0.0` (not `127.0.0.1`)

**Camera not working on emulator**
- The emulator has a simulated camera; use **Select from Library** instead
- Place a test image on the emulator or use `DEBUG_MODE=1`

**Build takes a long time**
- First build downloads SDK components and Gradle dependencies — this is normal
- Subsequent builds are much faster
