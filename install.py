#!/usr/bin/env python3
"""Interactive installer for the Subway Surfers profile tool.

Run from the repository root:

    python3 install.py          # Linux/macOS
    py -3 install.py            # Windows

The installer can add `subway` launchers to PATH, install only the Python
dependencies, or build standalone Windows executables.
"""
import argparse
import importlib.metadata
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
MIN_PYTHON = (3, 9)
CRYPTO_MIN = (41,)


class InstallError(Exception):
    pass


def current_os():
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def say(message=""):
    print(message)


def ask(prompt, default=None, choices=None):
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            answer = input(f"{prompt}{suffix}: ").strip()
        except EOFError:
            answer = ""
        if not answer and default is not None:
            answer = default
        if choices is not None and answer not in choices:
            say(f"Choose one of: {', '.join(sorted(choices))}")
            continue
        if answer:
            return answer


def ask_yes_no(prompt, default=True, assume_yes=False):
    if assume_yes:
        return default
    answer = ask(f"{prompt} (y/n)", "y" if default else "n", {"y", "n", "yes", "no"})
    return answer.lower().startswith("y")


def choose_os(args):
    detected = current_os()
    if args.os:
        return args.os
    if args.yes:
        return detected
    say(f"Detected operating system: {detected}")
    default = {"linux": "1", "windows": "2", "mac": "3"}[detected]
    choice = ask(
        "Which OS are you on?  1) Linux  2) Windows  3) macOS (coming later)",
        default,
        {"1", "2", "3"},
    )
    return {"1": "linux", "2": "windows", "3": "mac"}[choice]


def choose_mode(os_name, args):
    if args.mode:
        return args.mode
    if args.yes:
        return "commands"
    say()
    say("Installation type:")
    say("  1) Commands    install dependencies and add `subway` to PATH")
    say("  2) Source      install dependencies only")
    if os_name == "windows":
        say("  3) Standalone  build .exe files and add them to PATH")
        default = "1"
        choices = {"1", "2", "3"}
    else:
        default = "1"
        choices = {"1", "2"}
    choice = ask("Choose", default, choices)
    return {"1": "commands", "2": "source", "3": "exe"}[choice]


def default_prefix(os_name):
    if os_name == "windows":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "subway-tool" / "bin"
    return Path.home() / ".local" / "bin"


def version_tuple(text):
    numbers = []
    for part in text.split("."):
        digits = ""
        for char in part:
            if char.isdigit():
                digits += char
            else:
                break
        numbers.append(int(digits or 0))
    return tuple(numbers)


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def in_virtualenv():
    return sys.prefix != sys.base_prefix


def pip_install(spec):
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    if not in_virtualenv():
        cmd.append("--user")
    cmd.append(spec)
    say("running: " + " ".join(cmd))
    try:
        subprocess.check_call(cmd)
    except subprocess.CalledProcessError as exc:
        raise InstallError(
            "could not install dependencies. Create a virtual environment, or "
            "install `cryptography` with your system package manager, then re-run."
        ) from exc


def ensure_cryptography():
    version = package_version("cryptography")
    if version and version_tuple(version) >= CRYPTO_MIN:
        say(f"cryptography {version} is already installed")
        return
    pip_install("cryptography>=41")


def ensure_pyinstaller():
    if package_version("pyinstaller"):
        say("pyinstaller is already installed")
        return
    pip_install("pyinstaller>=6.0")


def tkinter_available():
    return importlib.util.find_spec("tkinter") is not None


def write_launcher(path, text):
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def install_linux_launchers(prefix):
    prefix.mkdir(parents=True, exist_ok=True)
    python = shlex.quote(sys.executable)
    cli = REPO / "subway_tool.py"
    launch = prefix / "subway"
    write_launcher(launch, f'#!/bin/sh\nexec {python} {shlex.quote(str(cli))} "$@"\n')

    gui_script = None
    if tkinter_available():
        gui_script = REPO / "subway_gui_tk.py"
    elif importlib.util.find_spec("gi") is not None:
        gui_script = REPO / "linux" / "subway_gui.py"
    if gui_script is not None:
        write_launcher(
            prefix / "subway-gui",
            f'#!/bin/sh\nexec {python} {shlex.quote(str(gui_script))} "$@"\n',
        )
        say(f"installed {prefix / 'subway-gui'}")
    else:
        say("note: no tkinter or GTK found; skipping the GUI launcher")
    say(f"installed {launch}")


def install_windows_launchers(prefix):
    prefix.mkdir(parents=True, exist_ok=True)
    python = Path(sys.executable)
    cli = REPO / "subway_tool.py"
    (prefix / "subway.bat").write_text(
        f'@echo off\r\n"{python}" "{cli}" %*\r\n', encoding="utf-8"
    )
    say(f"installed {prefix / 'subway.bat'}")

    if tkinter_available():
        pythonw = python.with_name("pythonw.exe")
        gui_python = pythonw if pythonw.is_file() else python
        gui = REPO / "subway_gui_tk.py"
        (prefix / "subway-gui.bat").write_text(
            f'@echo off\r\nstart "" "{gui_python}" "{gui}" %*\r\n', encoding="utf-8"
        )
        say(f"installed {prefix / 'subway-gui.bat'}")
    else:
        say("note: tkinter not found; skipping the GUI launcher")


def build_windows_exes(prefix):
    ensure_pyinstaller()
    spec_dir = REPO / "windows"
    say("building standalone executables (this can take a minute)")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "subway.spec"]
    try:
        subprocess.check_call(cmd, cwd=spec_dir)
    except subprocess.CalledProcessError as exc:
        raise InstallError("PyInstaller build failed; see the output above") from exc
    prefix.mkdir(parents=True, exist_ok=True)
    for name in ("subway.exe", "subway-gui.exe"):
        source = spec_dir / "dist" / name
        if not source.is_file():
            raise InstallError(f"build did not produce {name}")
        shutil.copy2(source, prefix / name)
        say(f"installed {prefix / name}")


def shell_path_config(prefix):
    shell = os.environ.get("SHELL", "")
    if shell.endswith("fish"):
        return (
            Path.home() / ".config" / "fish" / "config.fish",
            f"fish_add_path {shlex.quote(str(prefix))}",
        )
    if shell.endswith("zsh"):
        rc = Path.home() / ".zshrc"
    elif shell.endswith("bash"):
        rc = Path.home() / ".bashrc"
    else:
        rc = Path.home() / ".profile"
    return rc, f'export PATH={shlex.quote(str(prefix))}:"$PATH"'


def prefix_on_path(prefix):
    wanted = prefix.expanduser().resolve()
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and Path(entry).expanduser().resolve() == wanted:
            return True
    return False


def add_linux_path(prefix, assume_yes):
    if prefix_on_path(prefix):
        say(f"{prefix} is already on PATH")
        return
    rc, path_line = shell_path_config(prefix)
    if not ask_yes_no(f"Add {prefix} to PATH in {rc}?", True, assume_yes):
        say(f"Add this to your shell profile manually: {path_line}")
        return
    block = f"\n# >>> subway-tool >>>\n{path_line}\n# <<< subway-tool <<<\n"
    existing = rc.read_text(encoding="utf-8", errors="replace") if rc.exists() else ""
    if "# >>> subway-tool >>>" in existing:
        say(f"PATH already configured in {rc}")
    else:
        rc.parent.mkdir(parents=True, exist_ok=True)
        with rc.open("a", encoding="utf-8") as handle:
            handle.write(block)
        say(f"updated {rc}; open a new terminal or run: . {rc}")


def add_windows_path(prefix, assume_yes):
    if not ask_yes_no(f"Add {prefix} to your user PATH?", True, assume_yes):
        say(f'Add this folder to PATH manually: {prefix}')
        return
    import winreg

    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE
    )
    try:
        try:
            value, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value, value_type = "", winreg.REG_EXPAND_SZ
        parts = [part for part in value.split(";") if part]
        if str(prefix) in parts:
            say(f"{prefix} is already on PATH")
            return
        parts.append(str(prefix))
        winreg.SetValueEx(key, "Path", 0, value_type, ";".join(parts))
        say(f"added {prefix} to the user PATH; open a new terminal to use it")
    finally:
        winreg.CloseKey(key)
    try:
        import ctypes

        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 0x0002, 5000, ctypes.byref(ctypes.c_ulong())
        )
    except Exception:
        pass


def report_system_tools(os_name):
    adb = shutil.which("adb") or shutil.which("adb.exe")
    if not adb:
        if os_name == "windows":
            say("note: adb not found. Install Android platform-tools and add them to PATH.")
        else:
            say("note: adb not found. Install Android platform-tools (adb) and add it to PATH.")
    if os_name == "linux" and not shutil.which("idevicebackup2"):
        say("note: idevicebackup2 not found; only needed for iOS backups.")


def run(args):
    if sys.version_info < MIN_PYTHON:
        raise InstallError(
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
            f"(found {sys.version.split()[0]})"
        )
    if not (REPO / "subway_tool.py").is_file():
        raise InstallError("run install.py from the repository root")

    os_name = choose_os(args)
    if os_name == "mac":
        say("The macOS installer is not available yet. Follow mac/README.md instead.")
        return 0
    detected = current_os()
    if os_name != detected:
        raise InstallError(
            f"this installer is running on {detected}, so it cannot install for {os_name}"
        )

    mode = choose_mode(os_name, args)
    if mode == "exe" and os_name != "windows":
        raise InstallError("the standalone .exe option is Windows-only")
    prefix = Path(args.prefix).expanduser() if args.prefix else default_prefix(os_name)

    say()
    ensure_cryptography()
    if mode == "source":
        say()
        say("Dependencies are ready. Run the tool from this checkout:")
        if os_name == "windows":
            say(r"  windows\subway.bat status")
        else:
            say("  linux/subway status")
        report_system_tools(os_name)
        return 0

    if mode == "exe":
        build_windows_exes(prefix)
    elif os_name == "windows":
        install_windows_launchers(prefix)
    else:
        install_linux_launchers(prefix)

    if os_name == "windows":
        add_windows_path(prefix, args.yes)
    else:
        add_linux_path(prefix, args.yes)

    say()
    say("Done. Open a new terminal, then run:")
    say("  subway status")
    report_system_tools(os_name)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Install the Subway Surfers profile tool")
    parser.add_argument("--os", choices=["windows", "linux", "mac"], help="target OS")
    parser.add_argument(
        "--mode", choices=["commands", "source", "exe"], help="installation type"
    )
    parser.add_argument("--prefix", help="where to put launchers/executables")
    parser.add_argument("--yes", action="store_true", help="accept the defaults")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except InstallError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
