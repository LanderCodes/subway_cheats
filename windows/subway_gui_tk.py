#!/usr/bin/env python3
"""Tkinter GUI for subway_tool.py. Works on Windows, Linux and macOS."""
import contextlib
import io
import queue
import re
import shlex
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import subway_tool as st

if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

OP_LOCK = threading.Lock()


class Args:
    def __init__(self, serial=None, start=False, dry_run=False, **kwargs):
        self.serial = serial
        self.yes = True
        self.start = start
        self.dry_run = dry_run
        self.dir = None
        self.file = None
        self.value = None
        self.only = None
        self.target = None
        self.values = []
        self.type = None
        self.items = []
        self.extra = []
        self.owned = False
        self.missing = False
        self.search = None
        self.__dict__.update(kwargs)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Subway Profile Tool")
        self.geometry("1000x860")
        self.minsize(760, 600)
        self.work = queue.Queue()
        self.build()
        self.after(100, self._poll)
        self.after(300, self.refresh_async)

    # ---------- helpers ----------
    def read_only_text(self, height):
        widget = tk.Text(self, height=height, wrap="word", font=("Consolas", 9))
        widget.configure(state="disabled")
        return widget

    def set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def log(self, text):
        self.log_view.configure(state="normal")
        self.log_view.insert("end", ("\n" if self.log_view.get("1.0", "end-1c") else "") + text)
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def parse_ids(self, text):
        return [part for part in re.split(r"[,\s]+", text.strip()) if part]

    def selected(self, combo):
        return combo.get().strip()

    def make_entry(self, parent, text="", width=None):
        entry = ttk.Entry(parent)
        if text:
            entry.insert(0, text)
        if width:
            entry.configure(width=width)
        return entry

    def check(self, parent, text):
        var = tk.BooleanVar(value=False)
        return ttk.Checkbutton(parent, text=text, variable=var), var

    # ---------- layout ----------
    def build(self):
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        status_frame = ttk.LabelFrame(root, text="Status", padding=4)
        status_frame.pack(fill="x")
        self.status_view = self.read_only_text(7)
        self.status_view.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, pady=8)
        self.notebook.add(self.tab_refill(), text="Refill")
        self.notebook.add(self.tab_own(), text="Own")
        self.notebook.add(self.tab_disown(), text="Disown")
        self.notebook.add(self.tab_custom(), text="Set / Select")
        self.notebook.add(self.tab_browse(), text="Browse")
        self.notebook.add(self.tab_backup(), text="Backup")

        options = ttk.Frame(root)
        options.pack(fill="x")
        ttk.Label(options, text="Device").pack(side="left")
        self.serial = ttk.Entry(options, width=20)
        self.serial.pack(side="left", padx=(4, 12))
        self.start_check, self.start_var = self.check(options, "Relaunch game after write")
        self.start_check.pack(side="left", padx=(0, 12))
        self.dry_check, self.dry_var = self.check(options, "Dry run")
        self.dry_check.pack(side="left", padx=(0, 12))
        ttk.Button(options, text="Refresh", command=self.refresh_async).pack(side="left")
        ttk.Button(options, text="Clear log", command=self.clear_log).pack(side="left", padx=6)

        output_frame = ttk.LabelFrame(root, text="Output", padding=4)
        output_frame.pack(fill="both", expand=True)
        self.log_view = self.read_only_text(10)
        self.log_view.pack(fill="both", expand=True)

    def tab_refill(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.refill_value = self.make_entry(frame, "2000000000", 18)
        self.refill_only = self.make_entry(frame)

        ttk.Label(frame, text="Value for every currency").grid(row=0, column=0, sticky="w", pady=4)
        self.refill_value.grid(row=0, column=1, sticky="w", pady=4)
        ttk.Button(frame, text="Refill all currencies", command=self.on_refill).grid(
            row=0, column=2, sticky="w", padx=8, pady=4
        )
        ttk.Label(frame, text="Only these IDs (optional)").grid(row=1, column=0, sticky="w", pady=4)
        self.refill_only.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(frame, text="List currencies", command=lambda: self.on_list_kind("currencies")).grid(
            row=2, column=0, sticky="w", pady=4
        )
        ttk.Separator(frame, orient="horizontal").grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(frame, text="Single currency ID").grid(row=4, column=0, sticky="w", pady=4)
        self.cur_id = self.make_entry(frame)
        self.cur_id.grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Value").grid(row=5, column=0, sticky="w", pady=4)
        self.cur_val = self.make_entry(frame, "2000000000")
        self.cur_val.grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Set this currency", command=self.on_set_currency).grid(
            row=5, column=2, sticky="w", padx=8, pady=4
        )
        ttk.Label(
            frame,
            text="Tip: 'List currencies' shows IDs and current values. ID 2 is the coin balance.",
            foreground="#666666",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def tab_own(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.own_type = ttk.Combobox(
            frame,
            values=["characters", "outfits", "boards", "portraits", "frames", "backgrounds"],
            state="readonly",
        )
        self.own_type.current(0)
        self.own_ids = self.make_entry(frame)

        ttk.Label(frame, text="Type").grid(row=0, column=0, sticky="w", pady=4)
        self.own_type.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="IDs").grid(row=1, column=0, sticky="w", pady=4)
        self.own_ids.grid(row=1, column=1, sticky="ew", pady=4)
        self.own_all_check, self.own_all_var = self.check(frame, "All of this type (ignore IDs)")
        self.own_all_check.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Button(frame, text="Own", command=self.on_own).grid(row=3, column=1, sticky="w", pady=4)
        ttk.Label(
            frame,
            text="Examples: holly songYi  |  outfits: holly partyOutfit  |  tick All to unlock everything of that type.",
            foreground="#666666",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def tab_disown(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.dis_type = ttk.Combobox(
            frame,
            values=["characters", "outfits", "boards", "portraits", "frames", "backgrounds"],
            state="readonly",
        )
        self.dis_type.current(0)
        self.dis_ids = self.make_entry(frame)

        ttk.Label(frame, text="Type").grid(row=0, column=0, sticky="w", pady=4)
        self.dis_type.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="IDs").grid(row=1, column=0, sticky="w", pady=4)
        self.dis_ids.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Disown", command=self.on_disown).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            frame,
            text="The selected character/outfit/board falls back automatically. Default outfits cannot be removed.",
            foreground="#666666",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def tab_custom(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.custom_target = ttk.Combobox(
            frame,
            values=["currency", "upgrade", "score", "multiplier", "json", "select"],
            state="readonly",
        )
        self.custom_target.current(0)
        self.custom_args = self.make_entry(frame)

        ttk.Label(frame, text="Target").grid(row=0, column=0, sticky="w", pady=4)
        self.custom_target.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Arguments").grid(row=1, column=0, sticky="w", pady=4)
        self.custom_args.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Apply", command=self.on_custom).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(
            frame,
            text=(
                "currency 2 500000  |  upgrade jetpack 6  |  score 999999999  |  "
                "multiplier 99  |  json wallet currencies.2.value 123  |  "
                "select char holly partyOutfit"
            ),
            foreground="#666666",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def tab_browse(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.list_type = ttk.Combobox(
            frame,
            values=["characters", "outfits", "boards", "portraits", "frames", "backgrounds", "currencies"],
            state="readonly",
        )
        self.list_type.current(0)
        self.list_search = self.make_entry(frame)
        self.list_char = self.make_entry(frame)

        ttk.Label(frame, text="Type").grid(row=0, column=0, sticky="w", pady=4)
        self.list_type.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Search").grid(row=1, column=0, sticky="w", pady=4)
        self.list_search.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Character (outfits only)").grid(row=2, column=0, sticky="w", pady=4)
        self.list_char.grid(row=2, column=1, sticky="ew", pady=4)
        self.list_missing_check, self.list_missing_var = self.check(frame, "Only missing")
        self.list_missing_check.grid(row=3, column=1, sticky="w", pady=2)
        self.list_owned_check, self.list_owned_var = self.check(frame, "Only owned")
        self.list_owned_check.grid(row=4, column=1, sticky="w", pady=2)
        ttk.Button(frame, text="List", command=self.on_list).grid(row=5, column=1, sticky="w", pady=6)
        frame.columnconfigure(1, weight=1)
        return frame

    def tab_backup(self):
        frame = ttk.Frame(self.notebook, padding=12)
        self.restore_dir = self.make_entry(frame)

        ttk.Button(frame, text="Backup now", command=self.on_backup).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Button(frame, text="Undo last change", command=self.on_undo).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="Restore folder").grid(row=1, column=0, sticky="w", pady=4)
        self.restore_dir.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="Browse", command=self.browse_restore).grid(row=1, column=2, padx=4, pady=4)
        ttk.Button(frame, text="Restore", command=self.on_restore).grid(row=1, column=3, pady=4)
        ttk.Label(
            frame,
            text="Backups are stored in the app state folder. Every write also saves an automatic undo snapshot.",
            foreground="#666666",
        ).grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    # ---------- async plumbing ----------
    def ns(self, **kwargs):
        return Args(
            serial=self.serial.get().strip() or None,
            start=self.start_var.get(),
            dry_run=self.dry_var.get(),
            **kwargs,
        )

    def run_async(self, fn, args):
        def worker():
            with OP_LOCK:
                st.SERIAL = args.serial
                out = io.StringIO()
                err = io.StringIO()
                ok = True
                try:
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                        fn()
                except Exception as exc:
                    ok = False
                    err.write(f"ERROR: {exc}\n")
                text = (out.getvalue() + err.getvalue()).strip()
                self.work.put(("log", text, ok))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_async(self):
        args = self.ns()

        def worker():
            with OP_LOCK:
                st.SERIAL = args.serial
                out = io.StringIO()
                try:
                    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                        st.cmd_status(args)
                except Exception as exc:
                    out.write(f"Status error: {exc}\n")
                self.work.put(("status", out.getvalue(), True))

        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, text, ok = self.work.get_nowait()
                if kind == "status":
                    self.set_text(self.status_view, text)
                else:
                    if text:
                        self.log(text)
                    elif ok:
                        self.log("OK")
                    self.refresh_async()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def clear_log(self):
        self.set_text(self.log_view, "")

    # ---------- actions ----------
    def on_refill(self):
        args = self.ns(
            value=self.refill_value.get().strip() or "2000000000",
            only=self.refill_only.get().strip() or None,
        )
        self.run_async(lambda: st.cmd_refill(args), args)

    def on_set_currency(self):
        args = self.ns(
            target="currency",
            values=[self.cur_id.get().strip(), self.cur_val.get().strip()],
        )
        self.run_async(lambda: st.cmd_set(args), args)

    def on_own(self):
        kind = self.selected(self.own_type)
        if self.own_all_var.get():
            items = ["all"]
        else:
            items = self.parse_ids(self.own_ids.get())
        if not items:
            self.log("Enter one or more IDs, or tick 'All of this type'.")
            return
        args = self.ns(type=kind, items=items)
        self.run_async(lambda: st.cmd_own(args), args)

    def on_disown(self):
        kind = self.selected(self.dis_type)
        items = self.parse_ids(self.dis_ids.get())
        if not items:
            self.log("Enter one or more IDs to remove.")
            return
        args = self.ns(type=kind, items=items)
        self.run_async(lambda: st.cmd_disown(args), args)

    def on_custom(self):
        target = self.selected(self.custom_target)
        try:
            values = shlex.split(self.custom_args.get().strip())
        except ValueError as exc:
            self.log(f"ERROR: {exc}")
            return
        if target == "select":
            if not values:
                self.log("Use: select char holly partyOutfit  |  select board guardboard")
                return
            args = self.ns(type=values[0], items=values[1:])
            self.run_async(lambda: st.cmd_select(args), args)
            return
        if target in ("currency", "upgrade") and len(values) != 2:
            self.log(f"Use: {target} <name/id> <value>")
            return
        if target in ("score", "multiplier") and len(values) != 1:
            self.log(f"Use: {target} <value>")
            return
        if target == "json" and len(values) < 3:
            self.log("Use: json <file> <dotted.path> <value>")
            return
        args = self.ns(target=target, values=values)
        self.run_async(lambda: st.cmd_set(args), args)

    def on_list(self):
        kind = self.selected(self.list_type)
        extra = []
        if kind == "outfits":
            char = self.list_char.get().strip()
            if not char:
                self.log("Enter a character for the outfit list.")
                return
            extra = [char]
        args = self.ns(
            type=kind,
            extra=extra,
            owned=self.list_owned_var.get(),
            missing=self.list_missing_var.get(),
            search=self.list_search.get().strip() or None,
        )
        self.run_async(lambda: st.cmd_list(args), args)

    def on_list_kind(self, kind):
        args = self.ns(type=kind, extra=[])
        self.run_async(lambda: st.cmd_list(args), args)

    def on_backup(self):
        args = self.ns()
        self.run_async(lambda: st.cmd_backup(args), args)

    def on_undo(self):
        args = self.ns()
        self.run_async(lambda: st.cmd_undo(args), args)

    def browse_restore(self):
        path = filedialog.askdirectory(title="Choose a backup folder")
        if path:
            self.restore_dir.delete(0, "end")
            self.restore_dir.insert(0, path)

    def on_restore(self):
        path = self.restore_dir.get().strip()
        if not path:
            self.log("Enter the path to a backup folder.")
            return
        args = self.ns(dir=path)
        self.run_async(lambda: st.cmd_restore(args), args)


def main():
    try:
        app = App()
        app.mainloop()
    except tk.TclError as exc:
        messagebox.showerror("Subway Profile Tool", f"Could not start the GUI: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
