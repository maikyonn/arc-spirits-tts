#!/usr/bin/env python3
"""
File watcher that automatically triggers TTS mod builds on save.
Watches src/, objects/, modsettings/, and config.json for changes.

Keyboard shortcuts:
  B - Build the mod
  A - Check assets (Supabase URLs)
  D - Decompose (extract from TTS save to source files)
  Q - Quit
"""

import json
import os
import subprocess
import sys
import time
import select
import termios
import tty
import urllib.error
import urllib.request
from pathlib import Path

# Try to import watchdog, install if missing
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
except ImportError:
    print("Installing watchdog...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent

# Configuration
GAME_NAME = "Arc Spirits"
PROJECT_DIR = Path(__file__).resolve().parent
TTSMODMANAGER_DIR = PROJECT_DIR / "TTSModManager"
ASSET_MANIFEST_URL = "https://gvxfokbptelmvvlxbigh.supabase.co/functions/v1/export-all-tts-json"
ASSET_CHECK_TIMEOUT = 10

# Cache asset checks by export timestamp
ASSET_CHECK_CACHE = {
    "exported_at": None,
    "bad_urls": None,
}

# Directories/files to watch
WATCH_PATTERNS = [
    "src",
    "objects",
    "modsettings",
    "config.json",
]

# File extensions to trigger builds
WATCH_EXTENSIONS = {".ttslua", ".lua", ".json", ".xml"}

# Debounce settings (prevent multiple rapid builds)
DEBOUNCE_SECONDS = 1.0


def get_tts_saves_folder():
    """Get the TTS Saves folder path based on OS."""
    if sys.platform == "darwin":  # macOS
        return Path.home() / "Library" / "Tabletop Simulator" / "Saves"
    elif sys.platform == "win32":  # Windows
        return Path.home() / "Documents" / "My Games" / "Tabletop Simulator" / "Saves"
    else:  # Linux
        return Path.home() / ".local" / "share" / "Tabletop Simulator" / "Saves"


def fetch_asset_manifest():
    """Fetch the latest asset manifest from Supabase."""
    with urllib.request.urlopen(ASSET_MANIFEST_URL, timeout=ASSET_CHECK_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def gather_asset_urls(data):
    """Recursively gather all Supabase asset URLs from the manifest."""
    urls = set()

    def walk(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                if key == "schema_docs":
                    continue
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)
        elif isinstance(value, str):
            if value.startswith("http") and "supabase.co" in value:
                urls.add(value)

    walk(data)
    return urls


def check_url(url):
    """Return True if the asset URL is reachable."""
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=ASSET_CHECK_TIMEOUT) as response:
            return response.status < 400
    except urllib.error.HTTPError as err:
        if err.code != 405:
            return False
    except Exception:
        return False

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=ASSET_CHECK_TIMEOUT) as response:
            return response.status < 400
    except Exception:
        return False


def verify_assets():
    """Check that all asset URLs from Supabase are reachable."""
    try:
        manifest = fetch_asset_manifest()
    except Exception as err:
        print(f"Asset check failed: {err}")
        return False

    exported_at = manifest.get("exported_at")
    cached_export = ASSET_CHECK_CACHE["exported_at"]
    cached_bad = ASSET_CHECK_CACHE["bad_urls"]
    if cached_export == exported_at and cached_bad is not None:
        if cached_bad:
            print(f"Asset check failed (cached): {len(cached_bad)} missing assets")
            for url in cached_bad[:10]:
                print(f"  - {url}")
            if len(cached_bad) > 10:
                print(f"  ... and {len(cached_bad) - 10} more")
            return False
        return True

    urls = sorted(gather_asset_urls(manifest))
    if not urls:
        print("Asset check failed: no URLs found in manifest")
        return False

    bad_urls = []
    for index, url in enumerate(urls, start=1):
        if not check_url(url):
            bad_urls.append(url)
        if index % 100 == 0:
            print(f"Checked {index}/{len(urls)} assets...")

    ASSET_CHECK_CACHE["exported_at"] = exported_at
    ASSET_CHECK_CACHE["bad_urls"] = bad_urls

    if bad_urls:
        print(f"Asset check failed: {len(bad_urls)} missing assets")
        for url in bad_urls[:10]:
            print(f"  - {url}")
        if len(bad_urls) > 10:
            print(f"  ... and {len(bad_urls) - 10} more")
        return False

    print(f"Asset check OK ({len(urls)} assets)")
    return True


def run_build(check_assets: bool = False):
    """Run TTSModManager to build the mod."""
    if check_assets and not verify_assets():
        print("Build skipped due to missing assets.")
        return

    output_file = get_tts_saves_folder() / f"{GAME_NAME}.json"

    cmd = [
        "go", "run", "main.go",
        f"-moddir={PROJECT_DIR}",
        f"-modfile={output_file}",
    ]

    print(f"\n{'='*60}")
    print(f"Building: {time.strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            cwd=TTSMODMANAGER_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"Build successful ({elapsed:.2f}s)")
            trigger_tts_reload()
        else:
            print(f"Build FAILED:")
            print(result.stderr)

    except subprocess.TimeoutExpired:
        print("Build timed out!")
    except Exception as e:
        print(f"Build error: {e}")


def run_decompose():
    """Run TTSModManager to decompose (extract TTS save to source files)."""
    output_file = get_tts_saves_folder() / f"{GAME_NAME}.json"

    if not output_file.exists():
        print(f"Error: TTS save file not found: {output_file}")
        return

    cmd = [
        "go", "run", "main.go",
        f"-moddir={PROJECT_DIR}",
        f"-modfile={output_file}",
        "-reverse",
    ]

    print(f"\n{'='*60}")
    print(f"Decomposing: {time.strftime('%H:%M:%S')}")
    print(f"{'='*60}")

    try:
        start = time.time()
        result = subprocess.run(
            cmd,
            cwd=TTSMODMANAGER_DIR,
            capture_output=True,
            text=True,
            timeout=60
        )
        elapsed = time.time() - start

        if result.returncode == 0:
            print(f"Decompose successful ({elapsed:.2f}s)")
            print("Source files updated from TTS save.")
        else:
            print(f"Decompose FAILED:")
            print(result.stderr)

    except subprocess.TimeoutExpired:
        print("Decompose timed out!")
    except Exception as e:
        print(f"Decompose error: {e}")


def trigger_tts_reload():
    """Attempt to reload the save in TTS using pyautogui."""
    try:
        import pyautogui
        import pygetwindow

        # On macOS, use getAllTitles() and check for partial match
        titles = pygetwindow.getAllTitles()
        tts_found = any("Tabletop Simulator" in t for t in titles)

        if tts_found:
            # Activate TTS using AppleScript (more reliable on macOS)
            subprocess.run(
                ["osascript", "-e", 'tell application "Tabletop Simulator" to activate'],
                capture_output=True,
                timeout=5
            )
            time.sleep(0.5)
            pyautogui.hotkey("f9")
            print("Triggered TTS reload (F9)")
        else:
            print("TTS window not found")

    except ImportError:
        print("Install pyautogui/pygetwindow: pip install pyautogui pygetwindow")
    except Exception as e:
        print(f"Could not trigger TTS reload: {e}")


class BuildHandler(FileSystemEventHandler):
    """Handles file system events and triggers builds."""

    def __init__(self):
        self.last_build_time = 0

    def should_trigger_build(self, path: Path) -> bool:
        """Check if this file change should trigger a build."""
        # Check extension
        if path.suffix.lower() not in WATCH_EXTENSIONS:
            return False

        # Check if in watched directories
        rel_path = path.relative_to(PROJECT_DIR)
        first_part = rel_path.parts[0] if rel_path.parts else ""

        if first_part not in WATCH_PATTERNS and str(rel_path) not in WATCH_PATTERNS:
            return False

        # Ignore hidden files and temp files
        if any(part.startswith('.') for part in rel_path.parts):
            return False
        if path.name.endswith('~') or path.name.startswith('.#'):
            return False

        return True

    def on_any_event(self, event):
        """Handle file system events."""
        if event.is_directory:
            return

        if not isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            return

        path = Path(event.src_path)

        if not self.should_trigger_build(path):
            return

        # Debounce
        now = time.time()
        if now - self.last_build_time < DEBOUNCE_SECONDS:
            return

        self.last_build_time = now

        rel_path = path.relative_to(PROJECT_DIR)
        print(f"\nChanged: {rel_path}")
        run_build()


def get_key_nonblocking():
    """Get a keypress without blocking. Returns None if no key pressed."""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None


def main():
    print(f"""
╔══════════════════════════════════════════════════════════╗
║           Arc Spirits TTS - File Watcher                 ║
╠══════════════════════════════════════════════════════════╣
║  Watching: src/, objects/, modsettings/, config.json     ║
║  Output:   ~/Library/Tabletop Simulator/Saves/           ║
║                                                          ║
║  Keyboard Shortcuts:                                     ║
║    B - Build mod                                         ║
║    A - Check assets (Supabase URLs)                      ║
║    D - Decompose (extract TTS save to source)            ║
║    Q - Quit                                              ║
╚══════════════════════════════════════════════════════════╝
""")

    # Verify TTS saves folder exists
    saves_folder = get_tts_saves_folder()
    if not saves_folder.exists():
        print(f"Warning: TTS Saves folder not found: {saves_folder}")
        print("Creating it...")
        saves_folder.mkdir(parents=True, exist_ok=True)

    # Set up file watcher
    event_handler = BuildHandler()
    observer = Observer()

    # Watch the project directory
    observer.schedule(event_handler, str(PROJECT_DIR), recursive=True)
    observer.start()

    print(f"Watching {PROJECT_DIR}...")
    print("Make a change to trigger a build, or press B/D/Q\n")

    # Set up terminal for raw input (non-blocking single char reads)
    old_settings = termios.tcgetattr(sys.stdin)

    try:
        tty.setcbreak(sys.stdin.fileno())

        while True:
            key = get_key_nonblocking()

            if key:
                key_lower = key.lower()

                if key_lower == 'b':
                    print("\n[Manual Build triggered]")
                    run_build()
                elif key_lower == 'a':
                    print("\n[Manual Asset Check triggered]")
                    verify_assets()
                elif key_lower == 'd':
                    print("\n[Manual Decompose triggered]")
                    run_decompose()
                elif key_lower == 'q':
                    print("\nQuitting...")
                    break

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nStopping watcher...")
    finally:
        # Restore terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        observer.stop()

    observer.join()
    print("Done.")


if __name__ == "__main__":
    main()
