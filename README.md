# Subway Profile Tool

A tool for editing Subway Surfers profile data on a USB-connected phone over ADB (no root required).

## Features

- View and edit character, outfit, board, portrait, frame, and background inventories
- Modify currency (coins), powerup levels, scores, and multipliers
- Own all characters/outfits/boards/cosmetics with a single command
- Backup and restore profile files
- Undo last change
- Simple CLI and GTK4 GUI options

## Usage

### CLI

```bash
# Basic usage
./subway status
./subway refill 2000000000
./subway set currency 2 999999999
./subway own char holly songYi
./subway own outfit holly partyOutfit sunglassesOutfit
./subway own all chars
./subway list chars
./subway backup
```

### GUI

```bash
python3 subway_gui.py
```

## Requirements

- ADB and a USB-connected phone with Subway Surfers installed
- Python 3
- `pip install cryptography` (for AES decryption/encryption)

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**.

- **Free use**: You are free to use, modify, and distribute this software for non-commercial purposes.
- **Free modification**: You are free to adapt the code for your own needs.
- **No commercial use**: You may not use this software for commercial purposes without explicit permission.

For commercial use, please contact the author.

## Inspiration

This tool reads and writes the encrypted profile files stored in `%APPDATA%\..\com.kiloo.subwaysurf\files\profile` on Android, using the same AES-CBC encryption as the original game.