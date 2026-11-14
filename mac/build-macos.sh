#!/bin/sh
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
root=$(CDPATH= cd -- "$here/.." && pwd -P)
cd "$root"

python3 -m pip install --upgrade pip
python3 -m pip install -r mac/requirements.txt
python3 -m PyInstaller --noconfirm --clean \
    --paths . \
    --paths mac \
    --add-data "data:data" \
    --name subway \
    subway_tool.py
python3 -m PyInstaller --noconfirm --clean \
    --paths . \
    --paths mac \
    --add-data "data:data" \
    --hidden-import subway_tool \
    --hidden-import ios_backup \
    --windowed \
    --name subway-gui \
    subway_gui_tk.py

echo
echo "Build complete:"
echo "  dist/subway"
echo "  dist/subway-gui.app"
