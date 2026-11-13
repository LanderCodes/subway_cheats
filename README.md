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

## Quick start

Linux/macOS:

```bash
git clone git@github.com:LanderCodes/subway_cheats.git
cd subway_cheats
python3 -m pip install cryptography
./subway status
```

Windows:

```bat
git clone git@github.com:LanderCodes/subway_cheats.git
cd subway_cheats
py -3 -m pip install cryptography
windows\subway.bat status
```

Run `./subway menu` (or `windows\subway.bat menu`) for the interactive menu.

## Usage

```bash
./subway status
./subway refill 2000000000
./subway set currency 2 999999999
./subway own char holly songYi
./subway own outfit holly partyOutfit sunglassesOutfit
./subway own all chars
./subway list chars
./subway backup
./subway undo
```

Common flags: `--serial <id>`, `--profile-dir <folder>`, `--key`, `--iv`,
`--start`, `--yes`, `--dry-run`.

### Local profile mode

Edit a local folder instead of a phone:

```bash
./subway --profile-dir ./profile status
./subway --profile-dir ./profile refill 2000000000
```

Or set `SUBWAY_PROFILE_DIR`. This is also how the iOS pull/push workflow edits
profile files.

### GUI

```bash
python3 subway_gui.py       # Linux, GTK4
python3 subway_gui_tk.py    # Windows/macOS, Tkinter
```

## Android

1. Enable USB debugging on the phone
   (*Settings → About phone → tap Build number 7 times → Developer options*).
2. Connect the phone and approve the debugging prompt.
3. Confirm the device is visible with `adb devices`.
4. Run `./subway status`.

The game is force-stopped before every write. Reopen it afterwards, or pass
`--start`.

## iPhone (macOS, alpha)

Use an **unencrypted** Finder or `idevicebackup2` backup. Encrypted backups
store `Manifest.db` encrypted and cannot be read by this tool.

```bash
./subway ios backups        # list local backups
./subway ios info           # list profile files in the newest backup
./subway ios pull <dir>     # extract profile files
./subway --profile-dir <dir> refill 2000000000
./subway ios push <dir>     # inject files into the backup
./subway ios restore --yes  # restore the backup to the phone
```

`ios push` saves an undo snapshot to `~/.subway-tool/ios-undo/`. Restore uses
`idevicebackup2 restore --system --settings --remove <backup>` and reboots the
phone. See [`mac/README.md`](mac/README.md) for the full walkthrough and known
limitations.

## Platform folders

The core sources are shared at the repository root:

- `subway_tool.py` — CLI and profile codec
- `subway_gui_tk.py` — Tkinter GUI
- `ios_backup.py` — iOS backup reader/writer
- `data/` — bundled reference JSON

Platform folders only contain launchers and build files:

- [`windows/`](windows/) — batch launchers and PyInstaller spec
- [`mac/`](mac/) — macOS launchers, build script, and iOS notes

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
