import customtkinter as ctk
import json
import time
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests
import os
import threading
import re
import shutil
import sqlite3
import base64
import pyautogui
from pycaw.pycaw import AudioUtilities
import psutil
from pywinauto import Desktop
from pywinauto.application import Application

CONFIG_FILE = "config.json"
PROFILES_FILE = "profiles.json"

def load_creds():
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_creds(creds):
    with open(CONFIG_FILE, "w") as f:
        json.dump(creds, f, indent=4)

def mute_spotify():
    """Mutes Spotify.exe via Windows audio API."""
    sessions = AudioUtilities.GetAllSessions()
    for session in sessions:
        try:
            if session.Process and session.Process.name() == "Spotify.exe":
                session.SimpleAudioVolume.SetMute(1, None)
                print(">>> Spotify muted.")
                return True
        except (psutil.NoSuchProcess, Exception):
            continue
    return False


def get_chrome_encryption_key():
    """Retrieves Chrome's AES encryption key from Local State (DPAPI-unwrapped)."""
    try:
        import win32crypt
        from Crypto.Cipher import AES

        local_state_path = os.path.join(
            os.environ["LOCALAPPDATA"],
            "Google", "Chrome", "User Data", "Local State"
        )
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)

        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]

        key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return key
    except Exception as e:
        print(f">>> Token Grab: Could not get Chrome key: {e}")
        return None

def get_edge_encryption_key():
    """Retrieves Microsoft Edge's AES encryption key from Local State (DPAPI-unwrapped)."""
    try:
        import win32crypt

        local_state_path = os.path.join(
            os.environ["LOCALAPPDATA"],
            "Microsoft", "Edge", "User Data", "Local State"
        )
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state = json.load(f)

        encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
        encrypted_key = encrypted_key[5:]
        key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        return key
    except Exception as e:
        print(f">>> Token Grab: Could not get Edge key: {e}")
        return None

def decrypt_cookie_value(encrypted_value, key):
    """Decrypts Chrome/Edge cookie using AES-256-GCM."""
    try:
        from Crypto.Cipher import AES

        if encrypted_value[:3] == b'v10':
            nonce = encrypted_value[3:15]
            ciphertext = encrypted_value[15:-16]
            tag = encrypted_value[-16:]

            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            return cipher.decrypt_and_verify(ciphertext, tag).decode("utf-8")
    except Exception:
        pass
    return None

def grab_media_token_from_browser():
    """
    Silent token grab: reads media-user-token directly from browser cookies.
    Tries Chrome first, then Edge. Returns token or None if not found.
    """
    browsers = [
        {
            "name": "Chrome",
            "cookie_path": os.path.join(
                os.environ["LOCALAPPDATA"],
                "Google", "Chrome", "User Data", "Default", "Network", "Cookies"
            ),
            "key_fn": get_chrome_encryption_key
        },
        {
            "name": "Edge",
            "cookie_path": os.path.join(
                os.environ["LOCALAPPDATA"],
                "Microsoft", "Edge", "User Data", "Default", "Network", "Cookies"
            ),
            "key_fn": get_edge_encryption_key
        },
    ]

    for browser in browsers:
        cookie_db = browser["cookie_path"]
        if not os.path.exists(cookie_db):
            print(f">>> Token Grab: {browser['name']} cookie DB not found.")
            continue

        print(f">>> Token Grab: Trying {browser['name']}...")

        temp_db = cookie_db + "_temp_lossless"
        try:
            shutil.copy2(cookie_db, temp_db)
        except Exception as e:
            print(f">>> Token Grab: Could not copy {browser['name']} DB: {e}")
            continue

        try:
            key = browser["key_fn"]()
            if key is None:
                continue

            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT encrypted_value
                FROM cookies
                WHERE host_key LIKE '%music.apple.com%'
                  AND name = 'media-user-token'
                LIMIT 1
            """)
            row = cursor.fetchone()
            conn.close()

            if row:
                token = decrypt_cookie_value(row[0], key)
                if token:
                    print(f">>> Token Grab: Found in {browser['name']}!")
                    return token
                else:
                    print(f">>> Token Grab: Decryption failed in {browser['name']}.")
            else:
                print(f">>> Token Grab: media-user-token not found in {browser['name']}.")

        except Exception as e:
            print(f">>> Token Grab: Error reading {browser['name']}: {e}")
        finally:
            try:
                os.remove(temp_db)
            except Exception:
                pass

    return None

def refresh_apple_token(creds):
    """Attempts silent token refresh from browser. Returns updated or original creds."""
    print(">>> Token Refresh: Attempting silent grab...")
    new_token = grab_media_token_from_browser()

    if new_token:
        creds["apple_media"] = new_token
        save_creds(creds)
        print(">>> Token Refresh: Updated config.json")
        return creds
    else:
        print(">>> Token Refresh: Could not grab. Using existing token.")
        return creds


def get_apple_music_window(timeout=10):
    """Finds and returns the Apple Music window handle."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            all_windows = Desktop(backend="uia").windows()
            for w in all_windows:
                try:
                    if "Apple Music" in w.window_text() and w.is_visible():
                        pid = w.process_id()
                        app_handle = Application(backend="uia").connect(process=pid)
                        window = app_handle.window(title_re=".*Apple Music.*", found_index=0)
                        return window
                except Exception:
                    continue
        except Exception:
            pass
        time.sleep(0.5)
    return None

def get_name_variants(song_name):
    """Generates name variants by removing parentheses and dash-separated content."""
    variants = [song_name.strip()]
    base = re.sub(r'\s*\(.*?\)', '', song_name).strip()
    if base and base.lower() != song_name.strip().lower():
        variants.append(base)
    dash_base = re.split(r'\s+-\s+', song_name)[0].strip()
    if dash_base and dash_base.lower() not in [v.lower() for v in variants]:
        variants.append(dash_base)
    return variants

def is_fuzzy_match(am_text, song_name, artist_name):
    """
    Fuzzy title matching with three progressive levels:
    1. Starts-with boundary check
    2. Cleaned contains check
    3. Word overlap + artist confirmation
    """
    am_lower = am_text.strip().lower()
    song_lower = song_name.strip().lower()
    artist_lower = artist_name.strip().lower() if artist_name else ""

    def artist_confirmed():
        if not artist_lower:
            return True
        artist_words = [w for w in re.split(r'\W+', artist_lower) if len(w) > 2]
        return any(w in am_lower for w in artist_words)

    def clean(s):
        s = re.sub(r'[\(\[\{].*?[\)\]\}]', '', s)
        return re.sub(r'\s+', ' ', s).strip()

    if am_lower.startswith(song_lower):
        if len(am_lower) == len(song_lower):
            return True
        if am_lower[len(song_lower)] in (" ", "(", "-"):
            return True

    am_clean = clean(am_lower)
    song_clean = clean(song_lower)
    if song_clean and (song_clean in am_clean or am_clean in song_clean):
        return artist_confirmed()

    song_words = [w for w in re.split(r'\W+', song_clean) if len(w) >= 3]
    if not song_words:
        return False
    hits = sum(1 for w in song_words if w in am_lower)
    if hits / len(song_words) >= 0.8:
        return artist_confirmed()

    return False

def scroll_tracklist(window, direction="down", clicks=3):
    """Scrolls the Apple Music tracklist."""
    try:
        rect = window.rectangle()
        scroll_x = rect.left + int((rect.right - rect.left) * 0.5)
        scroll_y = rect.top + int((rect.bottom - rect.top) * 0.6)
        pyautogui.moveTo(scroll_x, scroll_y, duration=0.1)
        scroll_amount = -clicks if direction == "down" else clicks
        pyautogui.scroll(scroll_amount)
        time.sleep(0.4)
    except Exception as e:
        print(f">>> X-Ray: Scroll error: {e}")

def find_track_element(window, song_name, artist_name="", timeout=12):
    """
    Finds song element with fuzzy matching and best-pick ranking.
    Scores candidates and prefers those confirmed in tracklist rows.
    Auto-scrolls if not found.
    """
    variants = get_name_variants(song_name)
    song_lower = song_name.strip().lower()
    print(f">>> X-Ray: Searching '{song_name}' by '{artist_name}' | variants: {variants}")

    deadline = time.time() + timeout
    scroll_count = 0
    MAX_SCROLLS = 8

    def score_match(el_text):
        """Returns (score, length) for ranking. Higher is better."""
        t = el_text.strip().lower()
        s = song_lower

        for v in variants:
            if t == v.lower():
                return (3, len(el_text))

        if t.startswith(s):
            if len(t) == len(s):
                return (3, len(el_text))
            if t[len(s)] in (" ", "(", "-"):
                return (2, len(el_text))

        if s in t:
            return (1, len(el_text))

        if is_fuzzy_match(el_text, song_name, artist_name):
            return (0, len(el_text))

        return None

    def has_duration_nearby(el):
        """Checks if element is in a real tracklist row by looking for duration text."""
        try:
            parent = el.parent()
            if not hasattr(parent, "descendants"):
                return False
            siblings = parent.descendants(control_type="Text")
            for s in siblings:
                try:
                    txt = s.window_text().strip()
                    if re.match(r"^\d{1,2}:\d{2}$", txt):
                        return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    while time.time() < deadline:
        try:
            all_text = window.descendants(control_type="Text")
        except Exception:
            all_text = []

        candidates = []
        for el in all_text:
            try:
                el_text = el.window_text().strip()
                if not el_text:
                    continue
                result = score_match(el_text)
                if result is not None:
                    candidates.append((result, el, el_text))
            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda x: (x[0][0], x[0][1]), reverse=True)

            for (score_tuple, el, el_text) in candidates:
                if has_duration_nearby(el):
                    print(f">>> X-Ray: Best match (score={score_tuple[0]}): '{el_text}'")
                    return el

            best_score, best_el, best_text = candidates[0]
            print(f">>> X-Ray: Best match (score={best_score[0]}): '{best_text}'")
            return best_el

        if scroll_count < MAX_SCROLLS:
            print(f">>> X-Ray: Not visible, scrolling ({scroll_count+1}/{MAX_SCROLLS})...")
            scroll_tracklist(window, direction="down", clicks=3)
            scroll_count += 1
        else:
            time.sleep(0.5)

    return None

def auto_play_target_track(song_name, artist_name=""):
    """Automatically plays target track in Apple Music."""
    time.sleep(6)
    print(f">>> X-Ray: Searching for Apple Music window...")
    window = get_apple_music_window(timeout=10)
    if window is None:
        print(">>> X-Ray Error: Apple Music window not found.")
        return
    window.set_focus()
    print(f">>> X-Ray: Searching tracklist for '{song_name}'...")
    target_track = find_track_element(window, song_name, artist_name=artist_name, timeout=12)
    if target_track is None:
        print(f">>> X-Ray Error: '{song_name}' not found in tracklist.")
        return
    try:
        rect = target_track.rectangle()
        row_mid_y = (rect.top + rect.bottom) // 2
        hover_x = rect.left - 45
        print(f">>> X-Ray: Hovering to reveal Play button...")
        pyautogui.moveTo(hover_x, row_mid_y, duration=0.2)
        time.sleep(0.5)

        parent = target_track.parent()
        if not hasattr(parent, "child_window"):
            raise AttributeError("parent() lacks child_window method")

        play_btn = parent.child_window(title="Play", control_type="Button", found_index=0)
        play_btn.wait("enabled", timeout=2)
        play_btn.click_input()
        print(f">>> SUCCESS: Playing '{song_name}' on Apple Music.")
        return
    except Exception as e:
        print(f">>> Strategy 1 failed ({e}), trying double-click...")
    try:
        target_track.double_click_input()
        print(f">>> SUCCESS: Playing '{song_name}' on Apple Music.")
    except Exception as fallback_err:
        print(f">>> X-Ray Error: Both strategies failed. {fallback_err}")


def skip_aware_sleep(sp, current_track_id, playback):
    """Sleeps intelligently, waking early if track is skipped."""
    CHUNK_SIZE = 2
    WAKE_BEFORE = 2
    MAX_SLEEP = 60
    try:
        progress_ms = playback.get('progress_ms', 0)
        duration_ms = playback.get('item', {}).get('duration_ms', 0)
        if duration_ms > 0:
            remaining_s = max(0, (duration_ms - progress_ms) / 1000 - WAKE_BEFORE)
            total_sleep = min(remaining_s, MAX_SLEEP)
        else:
            total_sleep = CHUNK_SIZE
    except Exception:
        total_sleep = CHUNK_SIZE

    slept = 0.0
    while slept < total_sleep:
        chunk = min(CHUNK_SIZE, total_sleep - slept)
        time.sleep(chunk)
        slept += chunk
        try:
            check = sp.current_playback()
            if check:
                new_id = check.get('item', {}).get('id')
                if new_id and new_id != current_track_id:
                    print(f">>> Watchdog: Skip detected after {slept:.0f}s.")
                    return
        except Exception:
            pass

    print(f">>> Watchdog: Natural sleep of {slept:.0f}s complete.")


def run_watchdog():
    """Main sync loop: monitors Spotify and syncs to Apple Music."""
    creds = load_creds()
    creds = refresh_apple_token(creds)

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=creds["spotify_id"],
        client_secret=creds["spotify_secret"],
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="user-read-currently-playing user-read-playback-state"
    ))

    apple_headers = {
        'Authorization': creds["apple_auth"],
        'media-user-token': creds["apple_media"],
        'Origin': 'https://music.apple.com'
    }

    last_played_id = None
    consecutive_401s = 0

    while True:
        try:
            playback = sp.current_playback()

            if playback and playback.get('is_playing'):
                track = playback.get('item')

                if track and track.get('id') != last_played_id:
                    title = track['name']
                    artist = track['artists'][0]['name']
                    print(f"\n🎵 New Spotify Track: {title}")

                    full_track = sp.track(track['id'])
                    isrc = full_track.get('external_ids', {}).get('isrc')

                    if isrc:
                        url = f"https://api.music.apple.com/v1/catalog/in/songs?filter[isrc]={isrc}"
                        response = requests.get(url, headers=apple_headers)

                        if response.status_code == 401:
                            consecutive_401s += 1
                            print(f">>> Apple Music: 401 Unauthorized (attempt {consecutive_401s}).")
                            creds = refresh_apple_token(creds)
                            apple_headers['media-user-token'] = creds["apple_media"]
                            response = requests.get(url, headers=apple_headers)
                            if response.status_code == 401:
                                print(">>> Token Refresh failed. Re-login at music.apple.com.")
                            else:
                                consecutive_401s = 0

                        if response.status_code == 200:
                            data = response.json()
                            if data.get('data'):
                                apple_id = data['data'][0]['id']
                                print(f">>> Match found! Syncing {title}...")
                                mute_spotify()
                                os.startfile(f"musics://music.apple.com/in/song/{apple_id}")
                                threading.Thread(
                                    target=auto_play_target_track,
                                    args=(title, artist),
                                    daemon=True
                                ).start()

                    last_played_id = track['id']

                skip_aware_sleep(sp, last_played_id, playback)
            else:
                time.sleep(3)

        except Exception as e:
            print(f"Watchdog Loop Error: {e}")
            time.sleep(5)


def load_profiles():
    if os.path.exists(PROFILES_FILE):
        with open(PROFILES_FILE) as f:
            return json.load(f)
    return {}

def save_profiles(p):
    with open(PROFILES_FILE, "w") as f:
        json.dump(p, f, indent=4)

def write_config(profile):
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "spotify_id": profile["spotify_id"],
            "spotify_secret": profile["spotify_secret"],
            "apple_auth": profile.get("apple_auth", ""),
            "apple_media": profile.get("apple_media", ""),
        }, f, indent=4)


G = "#1DB954"
R = "#fa233b"
BG = "#0d0d0d"
C1 = "#1a1a1a"
C2 = "#242424"
TX = "#eeeeee"
MU = "#5e5e5e"
BR = "#2a2a2a"

ctk.set_appearance_mode("dark")
root = ctk.CTk()
root.title("Lossless Bridge")
root.geometry("860x540")
root.resizable(False, False)
root.configure(fg_color=BG)
root.update_idletasks()
root.geometry(f"860x540+{(root.winfo_screenwidth()-860)//2}+{(root.winfo_screenheight()-540)//2}")

_proc = [None]


def _clear():
    for w in root.winfo_children():
        w.destroy()

def _lbl(parent, text, size=13, bold=False, color=TX, **kw):
    return ctk.CTkLabel(parent, text=text,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        text_color=color, **kw)

def _entry(parent, hint, show=None, w=340):
    e = ctk.CTkEntry(parent, placeholder_text=hint,
                     width=w, height=42,
                     fg_color=C1, border_color=BR, border_width=1,
                     corner_radius=8, text_color=TX, font=("Segoe UI", 12))
    if show:
        e.configure(show=show)
    return e

def _btn(parent, text, cmd, w=180, h=42, fg=G, tc="#000"):
    hov = "#17a349" if fg == G else C2
    return ctk.CTkButton(parent, text=text, command=cmd,
                         width=w, height=h,
                         fg_color=fg, hover_color=hov,
                         text_color=tc, corner_radius=8,
                         font=("Segoe UI", 13, "bold"))

def show_select():
    _clear()
    profiles = load_profiles()
    COLORS = ["#1DB954", "#fa233b", "#0071e3", "#ff9f0a", "#bf5af2",
              "#30d158", "#ff6b6b", "#64d2ff"]

    _lbl(root, "LOSSLESS BRIDGE", size=11, bold=True, color=G).place(x=36, y=26)
    _lbl(root, "Who's listening?", size=30, bold=True).place(relx=0.5, y=80, anchor="n")
    _lbl(root, "Select your profile to continue", size=13, color=MU).place(relx=0.5, y=130, anchor="n")

    row = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
    row.place(relx=0.5, y=185, anchor="n")

    for i, (name, data) in enumerate(list(profiles.items())[:7]):
        col = COLORS[i % len(COLORS)]
        f = ctk.CTkFrame(row, fg_color=BG, corner_radius=0)
        f.pack(side="left", padx=14)
        ctk.CTkButton(f, text=name[0].upper(), width=90, height=90,
                      fg_color=col, hover_color=col,
                      text_color="#fff", corner_radius=12,
                      font=("Segoe UI", 32, "bold"),
                      command=lambda n=name, d=data: _launch(n, d)).pack()
        _lbl(f, name, size=12, color=MU).pack(pady=(8, 0))

    af = ctk.CTkFrame(row, fg_color=BG, corner_radius=0)
    af.pack(side="left", padx=14)
    ctk.CTkButton(af, text="+", width=90, height=90,
                  fg_color=C1, hover_color=C2,
                  text_color=MU, corner_radius=12,
                  font=("Segoe UI", 30),
                  command=show_setup).pack()
    _lbl(af, "Add Profile", size=12, color=MU).pack(pady=(8, 0))

def show_setup():
    _clear()
    profiles = load_profiles()

    if profiles:
        _btn(root, "← Back", show_select, w=90, h=30, fg="transparent", tc=MU).place(x=14, y=12)

    _lbl(root, "Create Profile", size=22, bold=True).place(x=54, y=58)
    _lbl(root, "Name your profile and add Spotify keys", size=12, color=MU).place(x=54, y=92)

    _lbl(root, "Profile Name", size=11, color=MU).place(x=54, y=128)
    name_e = _entry(root, "e.g. Shant, Home, Work…")
    name_e.place(x=54, y=150)

    _lbl(root, "Spotify Client ID", size=11, color=MU).place(x=54, y=208)
    sp_id = _entry(root, "Paste Client ID")
    sp_id.place(x=54, y=230)

    _lbl(root, "Spotify Client Secret", size=11, color=MU).place(x=54, y=286)
    sp_sec = _entry(root, "Paste Client Secret", show="•")
    sp_sec.place(x=54, y=308)

    ctk.CTkFrame(root, fg_color=BR, width=1, height=400, corner_radius=0).place(x=432, y=56)

    _lbl(root, "Apple Music Token", size=22, bold=True).place(x=464, y=58)
    _lbl(root, "Auto-grabbed from your browser", size=12, color=MU).place(x=464, y=92)

    st = _lbl(root, "○  Not grabbed yet", size=12, color=MU)
    st.place(x=464, y=132)

    grab = _btn(root, "⟳  Grab Token from Browser", cmd=lambda: None, w=330, h=40, fg=C2, tc=TX)
    grab.place(x=464, y=160)

    _lbl(root, "media-user-token", size=11, color=MU).place(x=464, y=216)
    am_med = _entry(root, "0.AsSi… (paste if grab fails)", w=330)
    am_med.place(x=464, y=238)

    _lbl(root, "apple_auth token", size=11, color=MU).place(x=464, y=294)
    am_auth = _entry(root, "Bearer eyJ… (optional)", w=330)
    am_auth.place(x=464, y=316)

    def do_grab():
        grab.configure(text="Searching…", state="disabled")
        st.configure(text="⟳  Checking browser cookies…", text_color="#facc15")
        def _work():
            token = grab_media_token_from_browser()
            if token:
                root.after(0, lambda: [
                    am_med.delete(0, "end"),
                    am_med.insert(0, token),
                    st.configure(text="✓  Token grabbed!", text_color=G),
                    grab.configure(text="✓  Done", state="normal"),
                ])
            else:
                root.after(0, lambda: [
                    st.configure(text="✗  Not found — paste manually below", text_color=R),
                    grab.configure(text="⟳  Try Again", state="normal"),
                ])
        threading.Thread(target=_work, daemon=True).start()
    grab.configure(command=do_grab)

    err = _lbl(root, "", size=12, color=R)
    err.place(relx=0.5, y=390, anchor="n")

    def do_save():
        n = name_e.get().strip()
        si = sp_id.get().strip()
        ss = sp_sec.get().strip()
        am = am_med.get().strip()
        aa = am_auth.get().strip()
        if not n:
            err.configure(text="⚠  Please enter a profile name.")
            return
        if not si or not ss:
            err.configure(text="⚠  Spotify Client ID and Secret required.")
            return
        p = load_profiles()
        p[n] = {"spotify_id": si, "spotify_secret": ss, "apple_auth": aa, "apple_media": am}
        save_profiles(p)
        _launch(n, p[n])

    _btn(root, "Save & Continue →", do_save, w=220, h=44).place(relx=0.5, y=450, anchor="n")

def show_dashboard(name):
    _clear()

    ctk.CTkFrame(root, fg_color=G, height=3, width=220, corner_radius=0).place(x=0, y=0)
    _lbl(root, "LOSSLESS BRIDGE", size=11, bold=True, color=G).place(x=36, y=22)
    _btn(root, f"⇄  {name}", show_select, w=150, h=30, fg=C1, tc=MU).place(x=674, y=16)

    dot = _lbl(root, "⬤", size=20, color=G)
    dot.place(relx=0.5, y=158, anchor="n")
    _pulse = {"on": True}
    def pulse():
        if not dot.winfo_exists():
            return
        dot.configure(text_color=G if _pulse["on"] else "#0a3d1f")
        _pulse["on"] = not _pulse["on"]
        root.after(800, pulse)
    pulse()

    _lbl(root, "FULL AUTO SYNC ACTIVE", size=26, bold=True).place(relx=0.5, y=196, anchor="n")
    _lbl(root, f"Profile: {name}", size=13, color=MU).place(relx=0.5, y=242, anchor="n")

    strip = ctk.CTkFrame(root, fg_color=C1, corner_radius=10,
                         border_width=1, border_color=BR, width=540, height=52)
    strip.place(relx=0.5, y=308, anchor="n")
    strip.pack_propagate(False)
    st = _lbl(strip, "Waiting for Spotify…", size=13, color=MU)
    st.pack(expand=True)
    root._st = st

def _set_status(text):
    try:
        s = getattr(root, "_st", None)
        if s and s.winfo_exists():
            root.after(0, lambda: s.configure(text=text, text_color=TX))
    except Exception:
        pass

def _launch(name, data):
    write_config(data)
    show_dashboard(name)

    def _watchdog_with_status():
        import builtins
        original_print = builtins.print
        def patched_print(*args, **kwargs):
            original_print(*args, **kwargs)
            line = " ".join(str(a) for a in args)
            if "New Spotify Track:" in line:
                _set_status("🎵  " + line.split("New Spotify Track:")[-1].strip())
            elif "SUCCESS" in line:
                _set_status("✓  " + line.split(">>>")[-1].strip())
            elif "Watchdog Loop Error" in line:
                _set_status("⚠  " + line)
        builtins.print = patched_print
        try:
            run_watchdog()
        finally:
            builtins.print = original_print

    if _proc[0] is None or not _proc[0].is_alive():
        t = threading.Thread(target=_watchdog_with_status, daemon=True)
        _proc[0] = t
        t.start()


_original_save_creds = save_creds

def _save_creds_and_sync_profile(creds):
    """Syncs updated tokens back to profiles.json."""
    _original_save_creds(creds)
    try:
        ps = load_profiles()
        for pname, pdata in ps.items():
            if pdata.get("spotify_id") == creds.get("spotify_id"):
                pdata["apple_media"] = creds.get("apple_media", "")
                pdata["apple_auth"] = creds.get("apple_auth", "")
                print(f">>> Profile Sync: Updated '{pname}'")
                break
        save_profiles(ps)
    except Exception as e:
        print(f">>> Profile Sync Error: {e}")

globals()["save_creds"] = _save_creds_and_sync_profile


profiles = load_profiles()
if profiles:
    show_select()
else:
    show_setup()

root.mainloop()
