# Subway Profile Tool — macOS host / iOS target

This folder contains the macOS launchers, build script, and iOS backup module.
The shared sources live at the repository root:

- `subway_tool.py` — CLI and profile codec (root)
- `subway_gui_tk.py` — Tkinter GUI (root)
- `ios_backup.py` — reads/writes profile files inside an iOS backup (this folder)
- `data/` — reference JSON (root)

Two workflows are supported on a Mac:

1. **Android phone over ADB** — same as Linux/Windows.
2. **Stock (non-jailbroken) iPhone using an unencrypted local backup** — edit
   the profile files inside a backup, then restore the backup to the phone.

## Status and next steps

The macOS launchers, local profile backend, iOS backup reader/writer, and CLI
commands are implemented and covered by synthetic tests. They have **not yet
been validated on a physical iPhone**, so treat the iOS restore path as alpha.

Validated on Linux with generated backups:

- `ios backups` / `ios info` / `ios pull` / `ios push`
- `--profile-dir` reads and writes, including plaintext iOS envelopes
- AES/plain/inline envelope round-trips
- `Manifest.db` updates and undo snapshots

Still to validate on real hardware:

1. Read the actual `Documents/profile` file list from an unencrypted backup.
2. Confirm the envelope format and whether the stock iOS key/IV match Android.
3. Verify `ios push` + `ios restore` on iOS 16/17/18 with Finder and
   `idevicebackup2` backups.
4. Check that new `Manifest.db` rows restore correctly, or fall back to
   updating only files already present in the backup.
5. Run the Tkinter GUI on macOS and build/sign/notarize the `.app` bundle.
6. Add macOS support to the root `install.py` (currently Linux/Windows).

Known limitations:

- Encrypted backups are rejected; disable backup encryption and make a new one.
- Restore replaces the whole backup on the phone, not just the profile.
- `idevicebackup2` behavior varies by libimobiledevice version; use a recent
  release and keep the phone connected through the reboot.

## Requirements

- macOS 11+
- Python 3.9+ (`python3`)
- `cryptography` Python package
- For Android: Android platform-tools (`adb`) on `PATH`
- For iPhone: `libimobiledevice` (`brew install libimobiledevice`) and Xcode
  command-line tools for the Tkinter GUI

```sh
python3 -m pip install -r requirements.txt
brew install libimobiledevice
```

## Run

```sh
./subway status
./subway menu
./subway-gui
```

`./subway` and `./subway-gui` work from any directory.

## iPhone workflow (unencrypted backup)

> **Backup encryption must be OFF.** In Finder, select your iPhone, open the
> General tab, and make sure "Encrypt local backup" is unchecked. Encrypted
> backups store `Manifest.db` encrypted, so this tool cannot read them.

### 1. Make a backup in Finder

Connect the iPhone, open Finder, select the device, and click **Back up now**.
Alternatively:

```sh
idevicebackup2 backup --full ~/ios-backup
```

The tool looks in the standard macOS location
(`~/Library/Application Support/MobileSync/Backup`) and picks the newest
backup. Override the search folder with `IOS_BACKUP_ROOT`, or pass `--backup`.

### 2. Find and inspect backups

```sh
./subway ios backups
./subway ios info
./subway ios info --backup ~/Library/Application\ Support/MobileSync/Backup/<UDID>
```

`ios info` lists the files found under the app's `Documents/profile` folder.

### 3. Pull the profile, edit it locally, push it back

```sh
./subway ios pull ~/subway-profile
./subway --profile-dir ~/subway-profile status
./subway --profile-dir ~/subway-profile refill 2000000000
./subway --profile-dir ~/subway-profile own all chars
./subway ios push ~/subway-profile
```

`ios pull` without a destination writes to
`~/.subway-tool/ios/<timestamp>/profile`. `ios push` snapshots the original
blobs and `Manifest.db` to `~/.subway-tool/ios-undo/<timestamp>/` first.

The iOS profile uses the same file names as Android. Decompiled envelopes may
be either plain inner JSON or base64+AES; the tool detects the format on read
and writes it back in the same format.

### 4. Restore the backup to the iPhone

```sh
./subway ios restore --yes
```

This runs:

```sh
idevicebackup2 restore --system --settings --remove <backup>
```

The phone will reboot. Keep it connected until the restore finishes. Then open
Subway Surfers and verify the profile.

You can target a specific device with `--udid <UDID>`.

## Local profile mode (no phone)

`--profile-dir` (or `SUBWAY_PROFILE_DIR`) makes the whole CLI edit a local
folder instead of a phone:

```sh
./subway --profile-dir ./profile status
./subway --profile-dir ./profile refill 999999999
SUBWAY_PROFILE_DIR=./profile ./subway own all chars
```

This is what `ios pull`/`ios push` use, and it is also handy for testing.

## Key overrides

The Android key is the default. If an iOS build uses a different key, pass it
with `--key` / `--iv`. Both accept UTF-8 text or `hex:<hex-bytes>`:

```sh
./subway --profile-dir ./profile --key 'hex:0011...' --iv 'hex:0000...' status
```

## Build a macOS app

Build on macOS; PyInstaller cannot cross-compile:

```sh
./build-macos.sh
```

Outputs:

- `dist/subway` — CLI
- `dist/subway-gui.app` — GUI app bundle

## State and undo

State lives in `~/.subway-tool/` by default:

- `backups/<timestamp>/` — manual `backup` command
- `last/` — undo snapshot from the previous write
- `ios/<timestamp>/profile` — default `ios pull` destination
- `ios-undo/<timestamp>/` — backup files replaced by `ios push`

Override with `SUBWAY_TOOL_HOME`.
