# 🎵 Lossless Bridge

**Automatically plays the lossless Apple Music version of whatever you're listening to on Spotify — zero clicks required.**

Spotify has the library. Apple Music has the lossless audio. Lossless Bridge connects them silently in the background so you always hear the highest quality version, without ever switching apps manually.

---

## How It Works

1. You play a song on Spotify as normal
2. Lossless Bridge detects the track using the Spotify API
3. It finds the exact lossless match on Apple Music using the song's ISRC code (a universal track fingerprint)
4. It opens the album in the Apple Music Windows app and clicks Play on the correct track
5. Spotify is silently muted in the Windows volume mixer
6. You hear lossless audio — fully automatic, every song, every skip

---

## Features

- **Zero-touch sync** — detects new tracks and skips in real time
- **ISRC matching** — finds the exact song, not just a fuzzy title search
- **X-Ray UI automation** — uses pywinauto to click the right track row in Apple Music
- **Ghost mute** — mutes Spotify in the volume mixer without pausing it
- **Auto token refresh** — silently grabs a fresh Apple Music token from your browser cookies when it expires
- **Profile system** — Netflix-style profile select, supports multiple users
- **Skip detection** — wakes up immediately when you skip, doesn't wait for the song to end

---

## Requirements

- Windows 10 or 11
- [Apple Music Windows app](https://apps.microsoft.com/store/detail/apple-music-preview/9PFHDD62MXS1) installed and logged in
- Spotify desktop app installed
- A [Spotify Developer account](https://developer.spotify.com/dashboard) (free)
- Chrome or Edge with `music.apple.com` logged in (for auto token grab)
- Python 3.10+ (only needed if running from source)

---

## Getting Started

### Option A — Run the EXE (recommended)

1. Download `LosslessBridge.exe` from [Releases](../../releases)
2. Double-click to run — no installation needed
3. On first launch, the setup screen appears

### Option B — Run from source

```bash
git clone https://github.com/Stampy705/lossless-bridge
cd lossless-bridge
pip install customtkinter spotipy requests pycaw psutil pywinauto pyautogui pywin32 pycryptodome
python lossless_bridge.py
```

### Option C — Build the EXE yourself

```bash
git clone https://github.com/Stampy705/lossless-bridge
cd lossless-bridge
# Double-click build.bat — it installs PyInstaller and builds automatically
build.bat
# EXE will appear in dist\LosslessBridge.exe
```

---

## First-Time Setup

When you launch for the first time you'll see the **Create Profile** screen:

### 1. Profile Name
Enter any name — this is just a label (e.g. your name, "Home", "Work").

### 2. Spotify Keys
1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Create a new app (name it anything)
3. Add `http://127.0.0.1:8888/callback` as a Redirect URI
4. Copy the **Client ID** and **Client Secret** into the setup screen

### 3. Apple Music Token
Click **Grab Token from Browser** — it silently reads the token from your Chrome or Edge cookie store. Make sure you're logged into [music.apple.com](https://music.apple.com) in at least one of those browsers first.

If the grab fails, you can paste the token manually:
- Open DevTools on music.apple.com → Application → Cookies
- Copy the value of `media-user-token`

### 4. Save & Continue
Click **Save & Continue** — your profile is saved and syncing starts immediately.

---

## Profile System

Lossless Bridge supports multiple profiles (like Netflix).

- **Select screen** — shown on every launch, click your profile to start
- **Add Profile** — click the `+` card to create a new profile
- **Switch** — click `⇄ ProfileName` in the dashboard corner anytime
- **Token auto-update** — when your Apple Music token expires mid-session, it's refreshed automatically and saved back to your profile for next time

---

## Troubleshooting

**Song opens in Apple Music but doesn't play automatically**
The X-Ray automation needs the Apple Music window to be visible (not minimised). Keep it in the background but not minimised.

**Token grab says "Not found"**
Make sure you're logged into `music.apple.com` (not just the desktop app) in Chrome or Edge. Visit the site, log in, then try grabbing again.

**Spotify 401 errors**
Your Apple Music token expired. Click your profile → Edit → Grab Token from Browser to refresh it.

**Windows Defender flags the EXE**
This is a known false positive with PyInstaller-built apps. Click "More info → Run anyway" or add the folder as a Defender exclusion. The source code is fully visible above.

**Song not found on Apple Music**
Some tracks aren't available in your country's Apple Music catalogue, or Apple Music doesn't have a lossless version. The app skips those silently.

---

## Project Structure

```
lossless_bridge.py   ← entire app (logic + UI in one file)
build.bat            ← builds LosslessBridge.exe with PyInstaller
config.json          ← active profile credentials (auto-generated, never commit real tokens)
profiles.json        ← saved profiles (auto-generated, never commit)
```

---

## How the Token Refresh Works

Apple Music tokens expire periodically. When the app gets a 401 response:

1. It copies your browser's cookie database to a temp file
2. Decrypts the `media-user-token` cookie using your browser's DPAPI key
3. Updates `config.json` and your saved profile in `profiles.json`
4. Retries the Apple Music request — all without interrupting playback

No browser window is opened. No manual action required.

---

## Privacy

- Your Spotify and Apple Music credentials are stored **locally only** in `profiles.json` and `config.json`
- Nothing is sent to any server except the official Spotify API and Apple Music API
- The token grab reads your local browser cookie database — it never touches network traffic

---

## Dependencies

| Package | Purpose |
|---|---|
| `customtkinter` | UI |
| `spotipy` | Spotify API |
| `requests` | Apple Music API |
| `pywinauto` | UI automation (click Play in Apple Music) |
| `pyautogui` | Mouse control for scrolling tracklist |
| `pycaw` | Mute Spotify in Windows volume mixer |
| `psutil` | Find Spotify process |
| `pywin32` | Windows DPAPI for cookie decryption |
| `pycryptodome` | AES-GCM cookie decryption |

---

## License

MIT — do whatever you want with it.
