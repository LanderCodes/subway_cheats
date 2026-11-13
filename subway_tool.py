#!/usr/bin/env python3
"""Subway Surfers profile tool (adb, no root) for Windows and other desktops.

The tool edits profiles on a USB-connected Android phone. The host can be
Windows, Linux or macOS; Windows is the primary target of this build.

Examples (Windows):
  subway.bat status
  subway.bat refill 2000000000
  subway.bat set currency 2 999999999
  subway.bat own char holly songYi
  subway.bat own outfit holly partyOutfit sunglassesOutfit
  subway.bat own all chars
  subway.bat disown board "roll&Race"
  subway.bat select char holly partyOutfit
  subway.bat list chars --missing
  subway.bat backup
  subway.bat undo
  subway.bat menu

Notes:
  * The game is force-stopped before every write. Reopen it afterwards, or pass --start.
  * Before each write the previous encrypted file is saved as an undo snapshot.
  * Own/disown also works for portraits, frames, backgrounds, characters, outfits and boards.
  * adb is located from the ADB env var, PATH, or a platform-tools folder next to this script.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import ios_backup


def _configure_stdio():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_configure_stdio()

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    sys.exit("Missing dependency: pip install cryptography")

APP_NAME = "subway-tool"


def resource_base():
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def default_state_dir():
    override = os.environ.get("SUBWAY_TOOL_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root) / APP_NAME
    return Path.home() / f".{APP_NAME}"


BASE = Path(__file__).resolve().parent
DATA = resource_base() / "data"
STATE = default_state_dir()
LAST = STATE / "last"
PROFILE_DIR = "/sdcard/Android/data/com.kiloo.subwaysurf/files/profile"
PKG = "com.kiloo.subwaysurf"
KEY = b"9rkxCPljSM1GVQhWw1r1rKOHGccb2iJ5"
IV = b"\0" * 16
KEY_OVERRIDE = None
IV_OVERRIDE = None

CHARS_FILE = "characters_inventory.json"
BOARDS_FILE = "boards_inventory.json"
PORTRAIT_FILE = "profile_portrait.json"
FRAME_FILE = "profile_frame.json"
BACKGROUND_FILE = "profile_background.json"
WALLET_FILE = "wallet.json"
UPGRADES_FILE = "upgrades.json"
STATS_FILE = "user_stats.json"
TOP_RUN_FILE = "top_run.json"

ALLOWED_FILES = {
    CHARS_FILE, BOARDS_FILE, PORTRAIT_FILE, FRAME_FILE, BACKGROUND_FILE,
    WALLET_FILE, UPGRADES_FILE, STATS_FILE, TOP_RUN_FILE,
    "achievements.json", "trophies.json",
}

SERIAL = None
PROFILE_DIR_OVERRIDE = None


class ToolError(Exception):
    pass


def load_ref(name, default):
    path = DATA / name
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ToolError(f"bad bundled data {path}: {exc}")


CHARS = load_ref("chars.json", {})
BOARDS = load_ref("boards.json", {})
PORTRAITS = load_ref("portraits.json", [])
FRAMES = load_ref("frames.json", [])
BACKGROUNDS = load_ref("backgrounds.json", [])


def find_adb():
    override = os.environ.get("ADB") or os.environ.get("SUBWAY_ADB")
    if override:
        return override
    found = shutil.which("adb")
    if found:
        return found
    names = ["adb.exe", "adb"] if os.name == "nt" else ["adb"]
    roots = [BASE]
    if getattr(sys, "frozen", False):
        roots.insert(0, Path(sys.executable).resolve().parent)
    candidates = [root / "platform-tools" / name for root in roots for name in names]
    candidates += [root / name for root in roots for name in names]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return names[0]


ADB = find_adb()


def adb():
    return [ADB, "-s", SERIAL] if SERIAL else [ADB]


def run_cmd(cmd, check=True):
    kwargs = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(cmd, **kwargs)
    except FileNotFoundError:
        raise ToolError(
            "adb not found. Install Android platform-tools, add adb to PATH, "
            "or set the ADB environment variable to adb.exe."
        )
    if check and proc.returncode != 0:
        msg = proc.stderr.decode(errors="replace").strip() or proc.stdout.decode(errors="replace").strip()
        raise ToolError(f"command failed: {' '.join(cmd)}\n{msg}")
    return proc


class AdbBackend:
    kind = "android"

    def label(self):
        return f"Android via adb ({SERIAL})" if SERIAL else "Android via adb"

    def device_serial(self):
        proc = run_cmd(adb() + ["get-serialno"], check=False)
        serial = proc.stdout.decode(errors="replace").strip()
        if proc.returncode != 0 or not serial or serial == "unknown":
            raise ToolError("No adb device found. Connect the phone and enable USB debugging.")
        return serial

    def game_pid(self):
        proc = run_cmd(adb() + ["shell", "pidof", PKG], check=False)
        if proc.returncode == 0:
            return proc.stdout.decode(errors="replace").strip()
        return ""

    def read(self, name):
        proc = run_cmd(adb() + ["exec-out", "cat", f"{PROFILE_DIR}/{name}"])
        if not proc.stdout:
            raise ToolError(f"empty or missing remote file: {name}")
        return proc.stdout

    def write(self, name, data):
        fd, tmp = tempfile.mkstemp(prefix="subway-", suffix=".json")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            run_cmd(adb() + ["push", tmp, f"{PROFILE_DIR}/{name}"])
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def list_files(self):
        proc = run_cmd(adb() + ["shell", f"ls -1 {PROFILE_DIR}"])
        names = []
        for line in proc.stdout.decode(errors="replace").splitlines():
            name = line.strip()
            if name and re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                names.append(name)
        return names

    def stop(self, args):
        if not self.game_pid():
            return False
        if getattr(args, "dry_run", False):
            print("Game is running; would force-stop it.")
            return False
        if not getattr(args, "yes", False):
            if sys.stdin.isatty():
                answer = input("Game is running. Force-stop it? Unsaved run progress will be lost [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    raise ToolError("aborted")
            else:
                raise ToolError("Game is running; re-run with --yes to force-stop it")
        run_cmd(adb() + ["shell", "am", "force-stop", PKG])
        time.sleep(1)
        print("Game stopped.")
        return True

    def start(self, args):
        if getattr(args, "start", False) and not getattr(args, "dry_run", False):
            run_cmd(adb() + ["shell", "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1"], check=False)
            print("Game launched.")


class LocalDirBackend:
    kind = "local"

    def __init__(self, path):
        self.path = Path(path).expanduser()
        if not self.path.is_dir():
            raise ToolError(f"profile folder not found: {self.path}")

    def label(self):
        return f"Local profile folder ({self.path})"

    def device_serial(self):
        return str(self.path)

    def game_pid(self):
        return ""

    def read(self, name):
        path = self.path / name
        if not path.is_file():
            raise ToolError(f"missing file: {path}")
        return path.read_bytes()

    def write(self, name, data):
        (self.path / name).write_bytes(data)

    def list_files(self):
        return sorted(
            p.name for p in self.path.iterdir()
            if p.is_file() and not p.name.startswith(".") and re.fullmatch(r"[A-Za-z0-9_.-]+", p.name)
        )

    def stop(self, args):
        if not getattr(args, "dry_run", False):
            print("Local profile mode: make sure Subway Surfers is fully closed.")
        return False

    def start(self, args):
        return None


BACKEND = AdbBackend()


def select_backend(profile_dir=None):
    global BACKEND
    path = profile_dir or PROFILE_DIR_OVERRIDE or os.environ.get("SUBWAY_PROFILE_DIR")
    if path:
        BACKEND = LocalDirBackend(path)
    else:
        BACKEND = AdbBackend()
    return BACKEND


def device_serial():
    return BACKEND.device_serial()


def game_pid():
    return BACKEND.game_pid()


def read_remote(name):
    return BACKEND.read(name)


def write_remote(name, data):
    return BACKEND.write(name, data)


def list_remote_files():
    return BACKEND.list_files()


def stop_game(args):
    return BACKEND.stop(args)


def start_game(args):
    return BACKEND.start(args)


def _decode_key(value, default):
    if not value:
        return default
    if value.startswith("hex:"):
        return bytes.fromhex(value[4:])
    return value.encode("utf-8")


def active_key():
    return _decode_key(KEY_OVERRIDE, KEY)


def active_iv():
    return _decode_key(IV_OVERRIDE, IV)


def _b64decode(text):
    padded = text + "=" * (-len(text) % 4)
    try:
        return base64.b64decode(padded, validate=True)
    except Exception as exc:
        raise ToolError(f"bad profile envelope: {exc}")


def _aes_decrypt(ciphertext):
    dec = Cipher(algorithms.AES(active_key()), modes.CBC(active_iv()), backend=default_backend()).decryptor()
    plain = dec.update(ciphertext) + dec.finalize()
    if not plain:
        raise ToolError("empty profile payload")
    pad = plain[-1]
    if 1 <= pad <= 16 and plain[-pad:] == bytes([pad]) * pad:
        plain = plain[:-pad]
    return plain


def _aes_encrypt(plain):
    padnum = 16 - len(plain) % 16
    plain += bytes([padnum]) * padnum
    enc = Cipher(algorithms.AES(active_key()), modes.CBC(active_iv()), backend=default_backend()).encryptor()
    return enc.update(plain) + enc.finalize()


def decrypt_env(env):
    if not isinstance(env, dict):
        raise ToolError("profile envelope must be a JSON object")
    payload = env.get("data")
    if isinstance(payload, dict):
        env["_subway_format"] = "inline"
        return payload
    if not isinstance(payload, str):
        raise ToolError("profile envelope has no string data")
    text = payload.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
        except Exception as exc:
            raise ToolError(f"could not parse plaintext profile: {exc}")
        env["_subway_format"] = "plain"
        return parsed
    try:
        plain = _aes_decrypt(_b64decode(text))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(
            f"could not decrypt profile: {exc}. If this is an iOS plaintext profile, "
            "its data field should contain JSON instead of base64."
        )
    try:
        parsed = json.loads(plain)
    except Exception as exc:
        raise ToolError(f"could not parse decrypted profile: {exc}")
    env["_subway_format"] = "aes"
    return parsed


def encode_env(data, version, fmt="aes"):
    if fmt == "inline":
        env = {"version": version, "data": data}
    else:
        text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
        if fmt == "plain":
            env = {"version": version, "data": text}
        else:
            ciphertext = _aes_encrypt(text.encode("utf-8"))
            env = {"version": version, "data": base64.b64encode(ciphertext).decode("ascii")}
    env["_subway_format"] = fmt
    return env


def encrypt_env(data, version):
    return encode_env(data, version, "aes")


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def load_profile(name):
    raw = read_remote(name)
    try:
        env = json.loads(raw)
    except Exception as exc:
        raise ToolError(f"{name}: not valid JSON ({exc})")
    return env, decrypt_env(env), raw


def save_profile(name, data, env, raw, args, note=""):
    data["lastSaved"] = now_iso()
    if getattr(args, "dry_run", False):
        print(f"[dry-run] would write {name}" + (f" ({note})" if note else ""))
        return
    LAST.mkdir(parents=True, exist_ok=True)
    if raw:
        try:
            (LAST / name).write_bytes(raw)
        except OSError:
            pass
    fmt = env.get("_subway_format", "aes")
    new_env = encode_env(data, env.get("version", 1), fmt)
    write_remote(name, json.dumps(new_env, separators=(",", ":")).encode("utf-8"))
    print(f"wrote {name}" + (f" ({note})" if note else ""))


def begin_write(args, name):
    stop_game(args)
    return load_profile(name)


def norm_type(value):
    value = value.lower()
    mapping = {
        "char": "char", "chars": "char", "character": "char", "characters": "char",
        "personage": "char", "personages": "char",
        "outfit": "outfit", "outfits": "outfit", "skin": "outfit", "skins": "outfit",
        "board": "board", "boards": "board", "hoverboard": "board", "hoverboards": "board",
        "portrait": "portrait", "portraits": "portrait",
        "frame": "frame", "frames": "frame",
        "background": "background", "backgrounds": "background",
        "currency": "currency", "currencies": "currency",
    }
    return mapping.get(value)


COS_TYPES = {
    "portrait": (PORTRAIT_FILE, PORTRAITS, "portraits"),
    "frame": (FRAME_FILE, FRAMES, "frames"),
    "background": (BACKGROUND_FILE, BACKGROUNDS, "backgrounds"),
}


def own_char(data, cid, outfits=None):
    outfits = list(outfits) if outfits else list(CHARS.get(cid, ["default"]))
    if "default" not in outfits:
        outfits.insert(0, "default")
    entry = data["owned"].get(cid)
    if entry is None:
        data["owned"][cid] = {"id": cid, "ownedOutfits": outfits, "lastOutfit": "default"}
        return True
    current = entry.setdefault("ownedOutfits", [])
    changed = False
    for outfit in outfits:
        if outfit not in current:
            current.append(outfit)
            changed = True
    if entry.get("lastOutfit") not in current:
        entry["lastOutfit"] = "default"
        changed = True
    return changed


def fallback_char(data):
    owned = data["owned"]
    for cid in ["jake"] + sorted(owned):
        if cid in owned:
            return cid
    return None


def disown_char(data, cid):
    if cid not in data["owned"]:
        raise ToolError(f"character not owned: {cid}")
    if len(data["owned"]) <= 1:
        raise ToolError("cannot remove the last owned character")
    del data["owned"][cid]
    selected = data.get("selected", {})
    if selected.get("character") == cid:
        fallback = fallback_char(data)
        if not fallback:
            raise ToolError("no fallback character available")
        entry = data["owned"][fallback]
        outfits = entry.get("ownedOutfits", ["default"])
        outfit = entry.get("lastOutfit")
        if outfit not in outfits:
            outfit = "default" if "default" in outfits else outfits[0]
        data["selected"] = {"character": fallback, "outfit": outfit}


def own_outfit(data, cid, outfit):
    if cid not in data["owned"]:
        own_char(data, cid, [outfit])
        return True
    current = data["owned"][cid].setdefault("ownedOutfits", [])
    if outfit in current:
        return False
    current.append(outfit)
    return True


def disown_outfit(data, cid, outfit):
    if cid not in data["owned"]:
        raise ToolError(f"character not owned: {cid}")
    if outfit == "default":
        raise ToolError("refusing to remove the default outfit")
    current = data["owned"][cid].get("ownedOutfits", [])
    if outfit not in current:
        raise ToolError(f"outfit not owned: {cid}/{outfit}")
    current.remove(outfit)
    entry = data["owned"][cid]
    if entry.get("lastOutfit") == outfit:
        entry["lastOutfit"] = "default" if "default" in current else (current[0] if current else "default")
    selected = data.get("selected", {})
    if selected.get("character") == cid and selected.get("outfit") == outfit:
        selected["outfit"] = "default" if "default" in current else (current[0] if current else "default")


def board_upgrades(bid):
    upgrades = {name: True for name in BOARDS.get(bid, ["default"])}
    upgrades["default"] = True
    return upgrades


def own_board(data, bid):
    if bid in data["owned"]:
        current = data["owned"][bid].setdefault("ownedUpgrades", {})
        changed = False
        for name in board_upgrades(bid):
            if not current.get(name):
                current[name] = True
                changed = True
        return changed
    data["owned"][bid] = {"id": bid, "ownedUpgrades": board_upgrades(bid)}
    return True


def disown_board(data, bid):
    if bid not in data["owned"]:
        raise ToolError(f"board not owned: {bid}")
    if len(data["owned"]) <= 1:
        raise ToolError("cannot remove the last owned board")
    del data["owned"][bid]
    if data.get("selected") == bid:
        data["selected"] = "default" if "default" in data["owned"] else sorted(data["owned"])[0]


def cosmetic_item_ids(data):
    ids = []
    for value in data.get("leveledEntries", {}).values():
        if isinstance(value, dict) and value.get("id"):
            ids.append(value["id"])
    return ids


def own_cosmetic(data, cid):
    owned = data.setdefault("owned", {})
    changed = False
    if cid not in owned:
        owned[cid] = {"id": cid, "isSeen": True}
        changed = True
    elif not owned[cid].get("isSeen"):
        owned[cid]["isSeen"] = True
        changed = True
    leveled = data.get("leveledEntries", {})
    if cid in leveled and isinstance(leveled[cid], dict) and leveled[cid].get("id"):
        item = leveled[cid]["id"]
        if item not in owned:
            owned[item] = {"id": item, "isSeen": True}
            changed = True
    return changed


def disown_cosmetic(data, cid):
    owned = data.get("owned", {})
    if cid not in owned:
        raise ToolError(f"not owned: {cid}")
    if len(owned) <= 1:
        raise ToolError("cannot remove the last owned item")
    del owned[cid]
    leveled = data.get("leveledEntries", {})
    if cid in leveled:
        item = leveled[cid].get("id") if isinstance(leveled[cid], dict) else None
        del leveled[cid]
        if item and item in owned and item != cid:
            owned.pop(item, None)
    if data.get("selected") == cid:
        candidates = sorted(owned)
        data["selected"] = next((x for x in candidates if x.startswith("default")), candidates[0])


def parse_number(value):
    try:
        return int(str(value).replace("_", ""))
    except ValueError:
        raise ToolError(f"not an integer: {value}")


def cmd_status(args):
    print("Device:", device_serial())
    pid = game_pid()
    print("Game:", f"running (pid {pid})" if pid else "stopped")
    try:
        _, chars, _ = load_profile(CHARS_FILE)
        selected = chars.get("selected", {})
        print(f"Characters: {len(chars.get('owned', {}))} owned / {len(CHARS)} reference; selected {selected.get('character')} / {selected.get('outfit')}")
    except ToolError as exc:
        print("Characters: unavailable:", exc)
    try:
        _, boards, _ = load_profile(BOARDS_FILE)
        print(f"Boards: {len(boards.get('owned', {}))} owned / {len(BOARDS)} reference; selected {boards.get('selected')}")
    except ToolError as exc:
        print("Boards: unavailable:", exc)
    for label, fname, ref in [
        ("Portraits", PORTRAIT_FILE, PORTRAITS),
        ("Frames", FRAME_FILE, FRAMES),
        ("Backgrounds", BACKGROUND_FILE, BACKGROUNDS),
    ]:
        try:
            _, data, _ = load_profile(fname)
            print(f"{label}: {len(data.get('owned', {}))} owned / {len(ref)} reference; selected {data.get('selected')}")
        except ToolError as exc:
            print(f"{label}: unavailable:", exc)
    try:
        _, wallet, _ = load_profile(WALLET_FILE)
        currencies = wallet.get("currencies", {})
        parts = []
        for key in sorted(currencies, key=lambda x: int(x)):
            value = currencies[key].get("value")
            parts.append(f"{key}={'?' if value is None else value}")
        print("Wallet:", "  ".join(parts))
    except ToolError as exc:
        print("Wallet: unavailable:", exc)
    try:
        _, upgrades, _ = load_profile(UPGRADES_FILE)
        print("Powerups:", upgrades.get("powerupLevels"))
    except ToolError as exc:
        print("Powerups: unavailable:", exc)
    try:
        _, top_run, _ = load_profile(TOP_RUN_FILE)
        print("Top score:", top_run.get("currentScore"))
    except ToolError as exc:
        print("Top score: unavailable:", exc)


def cmd_list(args):
    kind = norm_type(args.type)
    if kind is None:
        raise ToolError(f"unknown type: {args.type}")
    if kind == "currency":
        _, wallet, _ = load_profile(WALLET_FILE)
        for key in sorted(wallet.get("currencies", {}), key=lambda x: int(x)):
            value = wallet["currencies"][key].get("value")
            print(f"{key} = {value}")
        return
    search = (args.search or "").lower()

    def keep(cid, owned):
        if search and search not in cid.lower():
            return False
        if args.missing and owned:
            return False
        if args.owned and not owned:
            return False
        return True

    if kind == "outfit":
        if not args.extra:
            raise ToolError("usage: list outfits <character>")
        cid = args.extra[0]
        _, data, _ = load_profile(CHARS_FILE)
        owned = data.get("owned", {}).get(cid, {}).get("ownedOutfits", [])
        all_outfits = set(CHARS.get(cid, [])) | set(owned)
        for outfit in sorted(all_outfits, key=lambda x: (x != "default", x)):
            if keep(outfit, outfit in owned):
                print(("[x] " if outfit in owned else "[ ] ") + outfit)
        return

    if kind == "char":
        _, data, _ = load_profile(CHARS_FILE)
        owned = data.get("owned", {})
        for cid in sorted(set(CHARS) | set(owned)):
            is_owned = cid in owned
            if keep(cid, is_owned):
                count = len(owned.get(cid, {}).get("ownedOutfits", []))
                print(("[x] " if is_owned else "[ ] ") + cid + (f" ({count} outfits)" if is_owned else ""))
        return

    if kind == "board":
        _, data, _ = load_profile(BOARDS_FILE)
        owned = data.get("owned", {})
        for bid in sorted(set(BOARDS) | set(owned)):
            is_owned = bid in owned
            if keep(bid, is_owned):
                print(("[x] " if is_owned else "[ ] ") + bid)
        return

    _, reference, _ = COS_TYPES[kind]
    fname, _, _ = COS_TYPES[kind]
    _, data, _ = load_profile(fname)
    owned = data.get("owned", {})
    for cid in sorted(set(reference) | set(owned)):
        is_owned = cid in owned
        if keep(cid, is_owned):
            print(("[x] " if is_owned else "[ ] ") + cid)


def cmd_refill(args):
    value = parse_number(args.value)
    only = None
    if args.only:
        only = [x.strip() for x in args.only.split(",") if x.strip()]
    env, wallet, raw = begin_write(args, WALLET_FILE)
    currencies = wallet.setdefault("currencies", {})
    targets = only if only else [k for k in currencies if k != "0"]
    changed = False
    for key in targets:
        entry = currencies.setdefault(key, {"value": value, "expirationType": 0, "contextType": 0, "contextData": {}})
        if entry.get("value") != value:
            entry["value"] = value
            changed = True
    if not changed:
        print("nothing to change")
        return
    save_profile(WALLET_FILE, wallet, env, raw, args, note=f"currencies -> {value}")
    start_game(args)


def cmd_set(args):
    target = args.target.lower()
    values = args.values
    if target == "currency":
        if len(values) != 2:
            raise ToolError("usage: set currency <id|all|id,id> <value>")
        ids, value = values[0], parse_number(values[1])
        env, wallet, raw = begin_write(args, WALLET_FILE)
        currencies = wallet.setdefault("currencies", {})
        targets = [k for k in currencies if k != "0"] if ids.lower() == "all" else [x.strip() for x in ids.split(",") if x.strip()]
        changed = False
        for key in targets:
            entry = currencies.setdefault(key, {"value": value, "expirationType": 0, "contextType": 0, "contextData": {}})
            if entry.get("value") != value:
                entry["value"] = value
                changed = True
        if not changed:
            print("nothing to change")
            return
        save_profile(WALLET_FILE, wallet, env, raw, args, note=f"currency {ids} -> {value}")
        start_game(args)
        return
    if target == "upgrade":
        if len(values) != 2:
            raise ToolError("usage: set upgrade <jetpack|superSneakers|magnet|doubleScore> <level>")
        name, level = values[0], parse_number(values[1])
        env, upgrades, raw = begin_write(args, UPGRADES_FILE)
        levels = upgrades.setdefault("powerupLevels", {})
        if levels.get(name) == level:
            print("nothing to change")
            return
        levels[name] = level
        save_profile(UPGRADES_FILE, upgrades, env, raw, args, note=f"{name} -> {level}")
        start_game(args)
        return
    if target == "score":
        if len(values) != 1:
            raise ToolError("usage: set score <value>")
        value = parse_number(values[0])
        env, top_run, raw = begin_write(args, TOP_RUN_FILE)
        top_run["currentScore"] = value
        save_profile(TOP_RUN_FILE, top_run, env, raw, args, note=f"currentScore -> {value}")
        start_game(args)
        return
    if target == "multiplier":
        if len(values) != 1:
            raise ToolError("usage: set multiplier <value>")
        value = parse_number(values[0])
        env, stats, raw = begin_write(args, STATS_FILE)
        stats["highestMultiplierEver"] = value
        save_profile(STATS_FILE, stats, env, raw, args, note=f"highestMultiplierEver -> {value}")
        start_game(args)
        return
    if target == "json":
        if len(values) < 3:
            raise ToolError("usage: set json <file> <dotted.path> <json-or-string-value>")
        fname, path = values[0], values[1]
        if fname not in ALLOWED_FILES:
            raise ToolError(f"file not allowed: {fname}")
        raw_value = " ".join(values[2:])
        try:
            value = json.loads(raw_value)
        except Exception:
            value = raw_value
        env, data, raw = begin_write(args, fname)
        cursor = data
        parts = path.split(".")
        for part in parts[:-1]:
            if isinstance(cursor, list):
                cursor = cursor[int(part)]
            elif isinstance(cursor, dict):
                if part not in cursor:
                    raise ToolError(f"path not found: {path}")
                cursor = cursor[part]
            else:
                raise ToolError(f"bad path: {path}")
        last = parts[-1]
        if isinstance(cursor, list):
            cursor[int(last)] = value
        elif isinstance(cursor, dict):
            cursor[last] = value
        else:
            raise ToolError(f"bad path: {path}")
        save_profile(fname, data, env, raw, args, note=f"{path} -> {raw_value}")
        start_game(args)
        return
    raise ToolError(f"unknown set target: {target}")


def cmd_own(args):
    kind = norm_type(args.type)
    items = list(args.items)
    if args.type.lower() == "all":
        if not items:
            raise ToolError("usage: own all <chars|outfits|boards|portraits|frames|backgrounds>")
        kind = norm_type(items[0])
        items = items[1:]
    if kind is None:
        raise ToolError(f"unknown type: {args.type}")

    if kind == "outfit":
        env, data, raw = begin_write(args, CHARS_FILE)
        changed = False
        added = 0
        if not items or items == ["all"]:
            targets = [(cid, outfits) for cid, outfits in CHARS.items()]
        else:
            cid = items[0]
            outfits = items[1:] or (CHARS.get(cid) or ["default"])
            targets = [(cid, outfits)]
        for cid, outfits in targets:
            was_owned = cid in data["owned"]
            if own_char(data, cid, outfits):
                changed = True
            if not was_owned:
                added += 1
        if not changed:
            print("nothing to change")
            return
        save_profile(CHARS_FILE, data, env, raw, args, note="outfits added")
        print(f"characters: {len(data['owned'])} owned, {added} new")
        start_game(args)
        return

    if kind == "char":
        env, data, raw = begin_write(args, CHARS_FILE)
        targets = list(CHARS) if (not items or items == ["all"]) else items
        changed = False
        added = 0
        for cid in targets:
            was_owned = cid in data["owned"]
            if own_char(data, cid):
                changed = True
            if not was_owned:
                added += 1
        if not changed:
            print("nothing to change")
            return
        save_profile(CHARS_FILE, data, env, raw, args, note="characters added")
        print(f"characters: {len(data['owned'])} owned, {added} new")
        start_game(args)
        return

    if kind == "board":
        env, data, raw = begin_write(args, BOARDS_FILE)
        targets = list(BOARDS) if (not items or items == ["all"]) else items
        changed = False
        added = 0
        for bid in targets:
            was_owned = bid in data["owned"]
            if own_board(data, bid):
                changed = True
            if not was_owned:
                added += 1
        if not changed:
            print("nothing to change")
            return
        save_profile(BOARDS_FILE, data, env, raw, args, note="boards added")
        print(f"boards: {len(data['owned'])} owned, {added} new")
        start_game(args)
        return

    fname, reference, label = COS_TYPES[kind]
    env, data, raw = begin_write(args, fname)
    targets = list(reference) if (not items or items == ["all"]) else items
    changed = False
    for cid in targets:
        if own_cosmetic(data, cid):
            changed = True
    if kind == "frame":
        for item in cosmetic_item_ids(data):
            if own_cosmetic(data, item):
                changed = True
    if not changed:
        print("nothing to change")
        return
    save_profile(fname, data, env, raw, args, note=f"{label} added")
    print(f"{label}: {len(data.get('owned', {}))} owned")
    start_game(args)


def cmd_disown(args):
    kind = norm_type(args.type)
    items = list(args.items)
    if args.type.lower() == "all":
        raise ToolError("refusing 'disown all'; specify the IDs you want to remove")
    if kind is None:
        raise ToolError(f"unknown type: {args.type}")
    if not items or items == ["all"]:
        raise ToolError("refusing to remove everything; specify one or more IDs")

    if kind == "outfit":
        if items[0] == "all":
            raise ToolError("refusing to remove all outfits; specify a character and outfits")
        cid = items[0]
        outfits = items[1:]
        if not outfits:
            raise ToolError("usage: disown outfit <character> <outfit...>")
        env, data, raw = begin_write(args, CHARS_FILE)
        removed = 0
        for outfit in outfits:
            if outfit not in data.get("owned", {}).get(cid, {}).get("ownedOutfits", []):
                print(f"skip (not owned): {cid}/{outfit}")
                continue
            disown_outfit(data, cid, outfit)
            removed += 1
        if not removed:
            print("nothing to change")
            return
        save_profile(CHARS_FILE, data, env, raw, args, note="outfits removed")
        print(f"removed {removed} outfit(s) from {cid}")
        start_game(args)
        return

    if kind == "char":
        env, data, raw = begin_write(args, CHARS_FILE)
        removed = 0
        for cid in items:
            if cid not in data.get("owned", {}):
                print(f"skip (not owned): {cid}")
                continue
            disown_char(data, cid)
            removed += 1
        if not removed:
            print("nothing to change")
            return
        save_profile(CHARS_FILE, data, env, raw, args, note="characters removed")
        print(f"characters: {len(data['owned'])} owned, {removed} removed")
        start_game(args)
        return

    if kind == "board":
        env, data, raw = begin_write(args, BOARDS_FILE)
        removed = 0
        for bid in items:
            if bid not in data.get("owned", {}):
                print(f"skip (not owned): {bid}")
                continue
            disown_board(data, bid)
            removed += 1
        if not removed:
            print("nothing to change")
            return
        save_profile(BOARDS_FILE, data, env, raw, args, note="boards removed")
        print(f"boards: {len(data['owned'])} owned, {removed} removed")
        start_game(args)
        return

    fname, _, label = COS_TYPES[kind]
    env, data, raw = begin_write(args, fname)
    removed = 0
    for cid in items:
        if cid not in data.get("owned", {}):
            print(f"skip (not owned): {cid}")
            continue
        disown_cosmetic(data, cid)
        removed += 1
    if not removed:
        print("nothing to change")
        return
    save_profile(fname, data, env, raw, args, note=f"{label} removed")
    print(f"{label}: {len(data.get('owned', {}))} owned, {removed} removed")
    start_game(args)


def cmd_select(args):
    kind = norm_type(args.type)
    items = list(args.items)
    if kind is None:
        raise ToolError(f"unknown type: {args.type}")
    if kind == "char":
        cid = items[0]
        outfit = items[1] if len(items) > 1 else None
        env, data, raw = load_profile(CHARS_FILE)
        if cid not in data.get("owned", {}):
            raise ToolError(f"character not owned: {cid}")
        outfits = data["owned"][cid].get("ownedOutfits", [])
        if outfit is None:
            outfit = data["owned"][cid].get("lastOutfit")
            if outfit not in outfits:
                outfit = "default" if "default" in outfits else (outfits[0] if outfits else "default")
        if outfit not in outfits:
            raise ToolError(f"outfit not owned: {cid}/{outfit}")
        stop_game(args)
        env, data, raw = load_profile(CHARS_FILE)
        data["selected"] = {"character": cid, "outfit": outfit}
        data["owned"][cid]["lastOutfit"] = outfit
        save_profile(CHARS_FILE, data, env, raw, args, note=f"selected {cid}/{outfit}")
        start_game(args)
        return
    if kind == "board":
        bid = items[0]
        env, data, raw = load_profile(BOARDS_FILE)
        if bid not in data.get("owned", {}):
            raise ToolError(f"board not owned: {bid}")
        stop_game(args)
        env, data, raw = load_profile(BOARDS_FILE)
        data["selected"] = bid
        save_profile(BOARDS_FILE, data, env, raw, args, note=f"selected {bid}")
        start_game(args)
        return
    fname, _, label = COS_TYPES[kind]
    cid = items[0]
    env, data, raw = load_profile(fname)
    if cid not in data.get("owned", {}):
        raise ToolError(f"not owned: {cid}")
    stop_game(args)
    env, data, raw = load_profile(fname)
    data["selected"] = cid
    save_profile(fname, data, env, raw, args, note=f"selected {cid}")
    start_game(args)


def cmd_backup(args):
    device_serial()
    target = Path(args.dir) if args.dir else STATE / "backups" / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True, exist_ok=True)
    count = 0
    for name in list_remote_files():
        try:
            raw = read_remote(name)
        except ToolError as exc:
            print(f"skip {name}: {exc}")
            continue
        (target / name).write_bytes(raw)
        count += 1
    print(f"backed up {count} files to {target}")


def cmd_restore(args):
    source = Path(args.dir)
    if not source.is_dir():
        raise ToolError(f"not a directory: {source}")
    if (source / "profile").is_dir():
        source = source / "profile"
    files = sorted(p for p in source.iterdir() if p.is_file() and not p.name.startswith("."))
    if not files:
        raise ToolError(f"no files in {source}")
    stop_game(args)
    for path in files:
        write_remote(path.name, path.read_bytes())
        print("restored", path.name)
    start_game(args)


def cmd_undo(args):
    if not LAST.is_dir():
        raise ToolError("no undo snapshot yet")
    if args.file:
        files = [LAST / args.file]
    else:
        files = sorted(LAST.iterdir())
    files = [p for p in files if p.is_file()]
    if not files:
        raise ToolError("nothing to undo")
    stop_game(args)
    for path in files:
        write_remote(path.name, path.read_bytes())
        print("restored", path.name)
    start_game(args)


def cmd_raw(args):
    if args.action == "get":
        if args.file not in ALLOWED_FILES:
            raise ToolError(f"file not allowed: {args.file}")
        _, data, _ = load_profile(args.file)
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if args.action == "set":
        if args.file not in ALLOWED_FILES:
            raise ToolError(f"file not allowed: {args.file}")
        if not args.path:
            raise ToolError("usage: raw set <file> <json-file|->")
        text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except Exception as exc:
            raise ToolError(f"invalid JSON: {exc}")
        if not isinstance(data, dict):
            raise ToolError("top-level JSON must be an object")
        env, _, raw = begin_write(args, args.file)
        save_profile(args.file, data, env, raw, args, note="raw replace")
        start_game(args)
        return
    raise ToolError(f"unknown raw action: {args.action}")


def _confirm(question):
    if not sys.stdin.isatty():
        return False
    return input(question + " [y/N] ").strip().lower() in ("y", "yes")


def cmd_ios(args):
    action = getattr(args, "ios_command", None)
    backup_arg = getattr(args, "backup", None)
    try:
        if action in (None, "backups"):
            backups = ios_backup.find_backups()
            if not backups:
                raise ios_backup.IosBackupError(
                    "no iOS backups found. Create one with Finder, or run: "
                    "idevicebackup2 backup --full <folder>"
                )
            for path in backups:
                print(ios_backup.describe(path))
                print(" ", path)
            return
        backup = ios_backup.resolve_backup(backup_arg)
        if action == "info":
            print(ios_backup.describe(backup))
            for entry in ios_backup.list_profile_entries(backup):
                print(" ", entry["relativePath"])
            return
        if action == "pull":
            if getattr(args, "dest", None):
                dest = Path(args.dest).expanduser()
            else:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                dest = STATE / "ios" / stamp / "profile"
            dest, count = ios_backup.pull(backup, dest)
            print(f"copied {count} profile files to {dest}")
            print(f'edit with: subway --profile-dir "{dest}" status')
            return
        if action == "push":
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            undo = STATE / "ios-undo" / stamp
            count = ios_backup.push(backup, args.dir, undo_dir=undo)
            print(f"pushed {count} profile files into {backup}")
            print(f"undo snapshot: {undo}")
            print(f'apply with: subway ios restore --backup "{backup}" --yes')
            return
        if action == "restore":
            if not (getattr(args, "yes", False) or _confirm("Restore this backup to the iPhone? Apps may restart")):
                raise ToolError("aborted")
            ios_backup.restore(backup, udid=getattr(args, "udid", None))
            print("restore command finished; the phone may reboot. Keep it plugged in.")
            return
    except ios_backup.IosBackupError as exc:
        raise ToolError(str(exc))
    raise ToolError(f"unknown ios action: {action}")


def add_common(parser, suppress=False):
    default = argparse.SUPPRESS if suppress else None
    parser.add_argument("--serial", default=default, help="adb device serial")
    parser.add_argument("--profile-dir", default=default,
                        help="edit a local profile folder instead of a phone")
    parser.add_argument("--key", default=default,
                        help="AES key override (UTF-8 text, or hex:...)")
    parser.add_argument("--iv", default=default,
                        help="AES IV override (UTF-8 text, or hex:...)")
    parser.add_argument("--yes", action="store_true", default=(argparse.SUPPRESS if suppress else False),
                        help="do not ask before force-stopping the game")
    parser.add_argument("--start", action="store_true", default=(argparse.SUPPRESS if suppress else False),
                        help="launch the game after writing")
    parser.add_argument("--dry-run", action="store_true", default=(argparse.SUPPRESS if suppress else False),
                        help="show what would change without writing")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="subway",
        description="Edit the Subway Surfers profile on a USB-connected phone over adb (no root).",
        epilog="Run with no command for an interactive menu.",
    )
    add_common(parser)
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("status", help="show inventory and currency counts")
    add_common(p, suppress=True)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("list", help="list characters, outfits, boards, cosmetics or currencies")
    add_common(p, suppress=True)
    p.add_argument("type")
    p.add_argument("extra", nargs="*")
    p.add_argument("--owned", action="store_true", help="only owned")
    p.add_argument("--missing", action="store_true", help="only not owned")
    p.add_argument("--search", help="substring filter")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("refill", help="set all currencies to a value")
    add_common(p, suppress=True)
    p.add_argument("value", nargs="?", default="2000000000")
    p.add_argument("--only", help="comma-separated currency IDs instead of all")
    p.set_defaults(func=cmd_refill)

    p = sub.add_parser("set", help="set a currency, upgrade, score, multiplier or raw JSON path")
    add_common(p, suppress=True)
    p.add_argument("target", help="currency|upgrade|score|multiplier|json")
    p.add_argument("values", nargs="+")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("own", help="own characters, outfits, boards or cosmetics")
    add_common(p, suppress=True)
    p.add_argument("type", help="char|outfit|board|portrait|frame|background|all")
    p.add_argument("items", nargs="*", help="IDs; 'all' for every bundled item")
    p.set_defaults(func=cmd_own)

    p = sub.add_parser("disown", help="remove characters, outfits, boards or cosmetics")
    add_common(p, suppress=True)
    p.add_argument("type", help="char|outfit|board|portrait|frame|background")
    p.add_argument("items", nargs="*")
    p.set_defaults(func=cmd_disown)

    p = sub.add_parser("select", help="select a character, board, portrait, frame or background")
    add_common(p, suppress=True)
    p.add_argument("type", help="char|board|portrait|frame|background")
    p.add_argument("items", nargs="+")
    p.set_defaults(func=cmd_select)

    p = sub.add_parser("backup", help="copy every profile file to a local folder")
    add_common(p, suppress=True)
    p.add_argument("dir", nargs="?")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="push a backup folder back to the phone")
    add_common(p, suppress=True)
    p.add_argument("dir")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("undo", help="restore the file(s) changed by the last write")
    add_common(p, suppress=True)
    p.add_argument("--file")
    p.set_defaults(func=cmd_undo)

    p = sub.add_parser("raw", help="print or replace a decrypted profile file")
    add_common(p, suppress=True)
    p.add_argument("action", choices=["get", "set"])
    p.add_argument("file")
    p.add_argument("path", nargs="?")
    p.set_defaults(func=cmd_raw)

    p = sub.add_parser("menu", help="interactive menu")
    add_common(p, suppress=True)
    p.set_defaults(func=lambda args: menu())

    p = sub.add_parser("ios", help="work with unencrypted iOS backups (stock iPhone)")
    add_common(p, suppress=True)
    p.add_argument("--backup", help="backup folder (default: newest)")
    p.set_defaults(func=cmd_ios)
    ios_sub = p.add_subparsers(dest="ios_command")

    sp = ios_sub.add_parser("backups", help="list available iOS backups")
    add_common(sp, suppress=True)
    sp.add_argument("--backup", default=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_ios)

    sp = ios_sub.add_parser("info", help="list profile files in a backup")
    add_common(sp, suppress=True)
    sp.add_argument("--backup", default=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_ios)

    sp = ios_sub.add_parser("pull", help="extract profile files from a backup")
    add_common(sp, suppress=True)
    sp.add_argument("dest", nargs="?")
    sp.add_argument("--backup", default=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_ios)

    sp = ios_sub.add_parser("push", help="inject a profile folder into a backup")
    add_common(sp, suppress=True)
    sp.add_argument("dir")
    sp.add_argument("--backup", default=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_ios)

    sp = ios_sub.add_parser("restore", help="restore the edited backup to the iPhone")
    add_common(sp, suppress=True)
    sp.add_argument("--backup", default=argparse.SUPPRESS)
    sp.add_argument("--udid")
    sp.set_defaults(func=cmd_ios)

    return parser


PARSER = build_parser()


def _configure(args):
    global SERIAL, KEY_OVERRIDE, IV_OVERRIDE, PROFILE_DIR_OVERRIDE
    serial = getattr(args, "serial", None)
    if serial is not None:
        SERIAL = serial
    key = getattr(args, "key", None)
    if key is not None:
        KEY_OVERRIDE = key
    iv = getattr(args, "iv", None)
    if iv is not None:
        IV_OVERRIDE = iv
    profile = getattr(args, "profile_dir", None)
    if profile is not None:
        PROFILE_DIR_OVERRIDE = profile
    select_backend(PROFILE_DIR_OVERRIDE)


def run_argv(argv):
    args = PARSER.parse_args(argv)
    _configure(args)
    if hasattr(args, "func"):
        args.func(args)


def menu():
    global SERIAL
    try:
        print("Subway Surfers profile tool")
        print("Device:", device_serial())
    except ToolError as exc:
        print("error:", exc)
        return
    while True:
        print("1) Status")
        print("2) Refill all currencies")
        print("3) Set one currency")
        print("4) Own     (e.g. char holly | outfit holly partyOutfit | all chars)")
        print("5) Disown  (e.g. char holly | outfit holly partyOutfit)")
        print("6) List    (chars/outfits/boards/portraits/frames/backgrounds/currencies)")
        print("7) Select  (char/board/portrait/frame/background)")
        print("8) Backup all profile files")
        print("9) Undo last change")
        print("0) Quit")
        try:
            choice = input("> ").strip()
            if choice == "0":
                break
            if choice == "1":
                run_argv(["status"])
            elif choice == "2":
                value = input("value [2000000000]: ").strip() or "2000000000"
                run_argv(["refill", value])
            elif choice == "3":
                cid = input("currency id (or all): ").strip()
                value = input("value: ").strip()
                run_argv(["set", "currency", cid, value])
            elif choice == "4":
                line = input("own> ").strip().split()
                if line:
                    run_argv(["own"] + line)
            elif choice == "5":
                line = input("disown> ").strip().split()
                if line:
                    run_argv(["disown"] + line)
            elif choice == "6":
                kind = input("type> ").strip()
                argv = ["list", kind]
                if kind.lower().startswith("outfit"):
                    argv.append(input("character: ").strip())
                run_argv(argv)
            elif choice == "7":
                kind = input("type (char/board/portrait/frame/background)> ").strip()
                item_id = input("id> ").strip()
                argv = ["select", kind, item_id]
                if kind.lower().startswith("char"):
                    outfit = input("outfit (optional)> ").strip()
                    if outfit:
                        argv.append(outfit)
                run_argv(argv)
            elif choice == "8":
                run_argv(["backup"])
            elif choice == "9":
                run_argv(["undo"])
            else:
                print("unknown choice")
        except ToolError as exc:
            print("error:", exc)
        except SystemExit:
            pass
        except KeyboardInterrupt:
            print()
            break


def main(argv=None):
    args = PARSER.parse_args(argv)
    _configure(args)
    if not hasattr(args, "func"):
        menu()
        return 0
    try:
        args.func(args)
    except ToolError as exc:
        print("error:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
