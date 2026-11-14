# Subway Profile Tool — Windows build

Windows-focused version of the Subway Surfers profile tool. It edits profile
data on a USB-connected **Android** phone over ADB (no root required). The host
runs Windows; the phone still must be Android.

## Requirements

- Windows 10/11
- [Python 3.9+](https://www.python.org/downloads/windows/) (tick **Add python.exe to PATH**)
- Android [platform-tools](https://developer.android.com/tools/releases/platform-tools) (ADB)
- USB debugging enabled on the phone
- `cryptography` Python package

```bat
py -3 -m pip install -r requirements.txt
```

## Run from source (the `.py`)

```bat
subway.bat status
subway.bat refill 2000000000
subway.bat set currency 2 999999999
subway.bat own all chars
subway.bat backup
```

Or call Python directly:

```bat
py -3 subway_tool.py status
py -3 subway_tool.py menu
```

GUI (Tkinter, ships with Python on Windows):

```bat
subway-gui.bat
```

## Finding ADB

The tool looks for `adb` in this order:

1. `ADB` (or `SUBWAY_ADB`) environment variable — full path to `adb.exe`
2. `adb` on `PATH`
3. `platform-tools\adb.exe` next to the script or `.exe`
4. `adb.exe` next to the script or `.exe`

Either add platform-tools to `PATH` or drop the `platform-tools` folder beside
the script/executable.

## Build the `.exe`

Build on Windows (PyInstaller cannot cross-compile from Linux):

```bat
build-windows.bat
```

Outputs:

- `dist\subway.exe` — command-line tool
- `dist\subway-gui.exe` — windowed GUI

The shared `subway_tool.py`, `subway_gui_tk.py`, and `data\` from the repository
root plus `mac\ios_backup.py` are bundled into both executables.

## State and backups

On Windows state lives in:

```
%LOCALAPPDATA%\subway-tool\
```

- `backups\<timestamp>\` — manual backups
- `last\` — automatic undo snapshot from the previous write

Override the location with the `SUBWAY_TOOL_HOME` environment variable.

## Available commands

```bat
subway.bat status
subway.bat list chars
subway.bat list outfits holly
subway.bat refill 2000000000
subway.bat set currency 2 999999999
subway.bat own char holly songYi
subway.bat own outfit holly partyOutfit
subway.bat own all chars
subway.bat disown board "roll&Race"
subway.bat select char holly partyOutfit
subway.bat backup
subway.bat restore <folder>
subway.bat undo
subway.bat raw get wallet.json
subway.bat menu
```

Common flags: `--serial <id>`, `--profile-dir <folder>`, `--key`, `--iv`,
`--start`, `--yes`, `--dry-run`.

`--profile-dir` (or `SUBWAY_PROFILE_DIR`) edits a local folder instead of a
phone. The iOS backup commands (`subway.bat ios ...`) are also available, though
the iPhone workflow is documented for macOS in [`../mac/README.md`](../mac/README.md).

## Notes

- The game is force-stopped before every write. Reopen it afterwards or pass
  `--start`.
- Only one ADB device is used unless `--serial` is given.
- `subway_tool.py` and `subway_gui_tk.py` at the repository root are shared
  sources; `ios_backup.py` lives in `mac\`. This folder contains the Windows
  launchers and the PyInstaller spec.
