# Subway Surfers Profile Tool

Edit Subway Surfers profile data without root or jailbreak. The tool works with
an **Android** phone over ADB, or with a stock **iPhone** through an unencrypted
local backup on macOS.

## Support

| Host | Target | Status |
| --- | --- | --- |
| Linux | Android via ADB | Supported |
| Windows 10/11 | Android via ADB | Supported |
| macOS | Android via ADB | Supported |
| macOS | iPhone via unencrypted backup | Alpha, needs hardware validation |

## Features

- View and edit characters, outfits, boards, portraits, frames, and backgrounds
- Refill coins and set powerup levels, scores, and multipliers
- Own all characters/outfits/boards/cosmetics with one command
- Back up, restore, and undo profile changes
- CLI plus GTK4 (Linux) and Tkinter (Windows/macOS) GUIs
- Local profile mode for editing a folder without a phone
- iOS backup pull/push/restore workflow

## Requirements

- Python 3.9+
- `cryptography` (`python3 -m pip install cryptography`)
- **Android:** Android platform-tools (`adb`) and USB debugging enabled
- **iPhone:** a macOS host, `libimobiledevice`
  (`brew install libimobiledevice`), and an **unencrypted** backup

## Installation

### Installer

Clone the repository and run the installer:

```bash
git clone git@github.com:LanderCodes/subway_cheats.git
cd subway_cheats
python3 install.py
```

On Windows use `py -3 install.py`. The installer asks which OS you are on and
what you want:

- **Commands** — install dependencies and add `subway` to PATH
- **Source** — install dependencies only; run from the checkout
- **Standalone** (Windows only) — build `.exe` files and add them to PATH

It installs `cryptography`, creates launchers, and offers to update PATH. It
does not install system tools such as `adb`; see Requirements.

Non-interactive examples:

```bash
python3 install.py --yes --mode commands
python3 install.py --yes --mode source
python3 install.py --os windows --mode exe
```

Options: `--os`, `--mode`, `--prefix`, `--yes`. macOS installer support is
planned; use the manual steps in [`mac/README.md`](mac/README.md) for now.

### Manual

Linux:

```bash
python3 -m pip install cryptography
linux/subway status
```

macOS:

```bash
python3 -m pip install cryptography
mac/subway status
```

Windows:

```bat
py -3 -m pip install cryptography
windows\subway.bat status
```

Run `linux/subway menu`, `mac/subway menu`, or `windows\subway.bat menu` for
the interactive menu.

## Usage

After installing, the `subway` command is on PATH. From a checkout, use
`linux/subway`, `mac/subway`, or `windows\subway.bat` instead.

```bash
subway status
subway refill 2000000000
subway set currency 2 999999999
subway own char holly songYi
subway own outfit holly partyOutfit sunglassesOutfit
subway own all chars
subway list chars
subway backup
subway undo
```

Common flags: `--serial <id>`, `--profile-dir <folder>`, `--key`, `--iv`,
`--start`, `--yes`, `--dry-run`.

### Local profile mode

Edit a local folder instead of a phone:

```bash
subway --profile-dir ./profile status
subway --profile-dir ./profile refill 2000000000
```

Or set `SUBWAY_PROFILE_DIR`. This is also how the iOS pull/push workflow edits
profile files.

### GUI

```bash
python3 linux/subway_gui.py   # Linux, GTK4
python3 subway_gui_tk.py      # Windows/macOS, Tkinter
```

## Android

1. Enable USB debugging on the phone
   (*Settings → About phone → tap Build number 7 times → Developer options*).
2. Connect the phone and approve the debugging prompt.
3. Confirm the device is visible with `adb devices`.
4. Run `subway status`.

The game is force-stopped before every write. Reopen it afterwards, or pass
`--start`.

## iPhone (macOS, alpha)

Use an **unencrypted** Finder or `idevicebackup2` backup. Encrypted backups
store `Manifest.db` encrypted and cannot be read by this tool.

```bash
mac/subway ios backups        # list local backups
mac/subway ios info           # list profile files in the newest backup
mac/subway ios pull <dir>     # extract profile files
mac/subway --profile-dir <dir> refill 2000000000
mac/subway ios push <dir>     # inject files into the backup
mac/subway ios restore --yes  # restore the backup to the phone
```

`ios push` saves an undo snapshot to `~/.subway-tool/ios-undo/`. Restore uses
`idevicebackup2 restore --system --settings --remove <backup>` and reboots the
phone. See [`mac/README.md`](mac/README.md) for the full walkthrough and known
limitations.

## Platform folders

Shared sources live at the repository root:

- `subway_tool.py` — CLI and profile codec
- `subway_gui_tk.py` — Tkinter GUI (Windows/macOS)
- `data/` — bundled reference JSON
- `tests/` — synthetic profile and backup tests

Platform folders contain the code that only applies to that host:

- [`windows/`](windows/) — batch launchers, PyInstaller spec, requirements
- [`mac/`](mac/) — macOS launchers, build script, iOS backup module, notes
- [`linux/`](linux/) — Linux launchers and GTK4 GUI

## State, backups, and safety

State lives in `~/.subway-tool/` (or `%LOCALAPPDATA%\subway-tool\` on Windows):

- `backups/<timestamp>/` — output of `subway backup`
- `last/` — automatic undo snapshot from the previous write
- `ios/<timestamp>/profile` — default `ios pull` destination
- `ios-undo/<timestamp>/` — files replaced by `ios push`

Override the location with `SUBWAY_TOOL_HOME`.

`--key` and `--iv` override the AES key/IV (UTF-8 text or `hex:...`) for Android
or iOS profiles.

## Development

```bash
python3 -m unittest discover -s tests -v
```

The tests use synthetic profiles and backups; no phone is required.

## License

Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0).

- Free to use, modify, and distribute for non-commercial purposes.
- No commercial use without explicit permission.

For commercial use, contact the author.
