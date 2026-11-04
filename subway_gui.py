#!/usr/bin/env python3
"""Simple GTK4 GUI for subway_tool.py."""
import contextlib
import io
import re
import shlex
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

import subway_tool as st  # noqa: E402

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


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Subway Profile Tool")
        self.set_default_size(1000, 900)
        self.build()
        GLib.timeout_add(300, self._initial_refresh)

    # ---------- widget helpers ----------
    def textview(self):
        view = Gtk.TextView()
        view.set_editable(False)
        view.set_cursor_visible(False)
        view.set_monospace(True)
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        view.set_margin_top(6)
        view.set_margin_bottom(6)
        view.set_margin_start(6)
        view.set_margin_end(6)
        return view

    def scroll(self, child, height, vexpand=False):
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(child)
        scroller.set_min_content_height(height)
        scroller.set_vexpand(vexpand)
        return scroller

    def grid(self):
        grid = Gtk.Grid()
        grid.set_column_spacing(10)
        grid.set_row_spacing(10)
        grid.set_margin_top(14)
        grid.set_margin_bottom(14)
        grid.set_margin_start(14)
        grid.set_margin_end(14)
        return grid

    def label(self, text, dim=False):
        label = Gtk.Label(label=text)
        label.set_xalign(0)
        if dim:
            label.add_css_class("dim-label")
            label.set_wrap(True)
        return label

    def frame(self, title, child):
        frame = Gtk.Frame()
        frame.set_label(title)
        frame.set_child(child)
        return frame

    def dropdown_value(self, dropdown):
        item = dropdown.get_selected_item()
        return item.get_string() if item is not None else ""

    def parse_ids(self, text):
        return [part for part in re.split(r"[,\s]+", text.strip()) if part]

    # ---------- layout ----------
    def build(self):
        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        title = Gtk.Label(label="Subway Profile Tool")
        title.add_css_class("title")
        header.set_title_widget(title)
        refresh = Gtk.Button(label="Refresh")
        refresh.connect("clicked", lambda *_: self.refresh_async())
        header.pack_end(refresh)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_margin_top(6)
        root.set_margin_bottom(6)
        root.set_margin_start(10)
        root.set_margin_end(10)
        self.set_child(root)

        self.status_view = self.textview()
        root.append(self.frame("Status", self.scroll(self.status_view, 110, False)))

        notebook = Gtk.Notebook()
        notebook.append_page(self.tab_refill(), Gtk.Label(label="Refill"))
        notebook.append_page(self.tab_own(), Gtk.Label(label="Own"))
        notebook.append_page(self.tab_disown(), Gtk.Label(label="Disown"))
        notebook.append_page(self.tab_custom(), Gtk.Label(label="Set / Select"))
        notebook.append_page(self.tab_browse(), Gtk.Label(label="Browse"))
        notebook.append_page(self.tab_backup(), Gtk.Label(label="Backup"))
        root.append(notebook)

        options = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        options.append(self.label("Device"))
        self.serial = Gtk.Entry()
        self.serial.set_placeholder_text("adb serial (optional)")
        self.serial.set_width_chars(18)
        options.append(self.serial)
        self.start_check = Gtk.CheckButton(label="Relaunch game after write")
        options.append(self.start_check)
        self.dry_check = Gtk.CheckButton(label="Dry run")
        options.append(self.dry_check)
        options.append(self.label("Writes force-stop the game.", dim=True))
        clear = Gtk.Button(label="Clear log")
        clear.connect("clicked", lambda *_: self.log_view.get_buffer().set_text(""))
        options.append(clear)
        root.append(options)

        self.log_view = self.textview()
        root.append(self.frame("Output", self.scroll(self.log_view, 180, True)))

    def tab_refill(self):
        grid = self.grid()
        self.refill_value = Gtk.Entry()
        self.refill_value.set_text("2000000000")
        self.refill_value.set_width_chars(16)
        self.refill_only = Gtk.Entry()
        self.refill_only.set_placeholder_text("optional: 2,5,20")
        self.refill_only.set_hexpand(True)

        refill = Gtk.Button(label="Refill all currencies")
        refill.add_css_class("suggested-action")
        refill.connect("clicked", self.on_refill)
        list_cur = Gtk.Button(label="List currencies")
        list_cur.connect("clicked", lambda *_: self.on_list_kind("currencies"))

        self.cur_id = Gtk.Entry()
        self.cur_id.set_placeholder_text("e.g. 2")
        self.cur_val = Gtk.Entry()
        self.cur_val.set_text("2000000000")
        set_cur = Gtk.Button(label="Set this currency")
        set_cur.connect("clicked", self.on_set_currency)

        grid.attach(self.label("Value for every currency"), 0, 0, 1, 1)
        grid.attach(self.refill_value, 1, 0, 1, 1)
        grid.attach(refill, 2, 0, 1, 1)
        grid.attach(self.label("Only these IDs (optional)"), 0, 1, 1, 1)
        grid.attach(self.refill_only, 1, 1, 2, 1)
        grid.attach(list_cur, 0, 2, 1, 1)
        grid.attach(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), 0, 3, 3, 1)
        grid.attach(self.label("Single currency ID"), 0, 4, 1, 1)
        grid.attach(self.cur_id, 1, 4, 1, 1)
        grid.attach(self.label("Value"), 0, 5, 1, 1)
        grid.attach(self.cur_val, 1, 5, 1, 1)
        grid.attach(set_cur, 2, 5, 1, 1)
        grid.attach(self.label("Tip: 'List currencies' shows IDs and current values. ID 2 is the coin balance.", True), 0, 6, 3, 1)
        return grid

    def tab_own(self):
        grid = self.grid()
        self.own_type = Gtk.DropDown.new_from_strings(
            ["characters", "outfits", "boards", "portraits", "frames", "backgrounds"]
        )
        self.own_type.set_hexpand(True)
        self.own_ids = Gtk.Entry()
        self.own_ids.set_hexpand(True)
        self.own_ids.set_placeholder_text("e.g. holly songYi  |  outfits: holly partyOutfit")
        self.own_all = Gtk.CheckButton(label="All of this type (ignore IDs)")
        own = Gtk.Button(label="Own")
        own.add_css_class("suggested-action")
        own.connect("clicked", self.on_own)

        grid.attach(self.label("Type"), 0, 0, 1, 1)
        grid.attach(self.own_type, 1, 0, 1, 1)
        grid.attach(self.label("IDs"), 0, 1, 1, 1)
        grid.attach(self.own_ids, 1, 1, 1, 1)
        grid.attach(self.own_all, 1, 2, 1, 1)
        grid.attach(own, 1, 3, 1, 1)
        grid.attach(self.label("Examples: holly songYi  |  outfits: holly partyOutfit  |  tick All to unlock everything of that type.", True), 0, 4, 2, 1)
        return grid

    def tab_disown(self):
        grid = self.grid()
        self.dis_type = Gtk.DropDown.new_from_strings(
            ["characters", "outfits", "boards", "portraits", "frames", "backgrounds"]
        )
        self.dis_type.set_hexpand(True)
        self.dis_ids = Gtk.Entry()
        self.dis_ids.set_hexpand(True)
        self.dis_ids.set_placeholder_text("e.g. holly songYi  |  outfits: holly partyOutfit")
        disown = Gtk.Button(label="Disown")
        disown.connect("clicked", self.on_disown)

        grid.attach(self.label("Type"), 0, 0, 1, 1)
        grid.attach(self.dis_type, 1, 0, 1, 1)
        grid.attach(self.label("IDs"), 0, 1, 1, 1)
        grid.attach(self.dis_ids, 1, 1, 1, 1)
        grid.attach(disown, 1, 2, 1, 1)
        grid.attach(self.label("The selected character/outfit/board falls back automatically. Default outfits cannot be removed.", True), 0, 3, 2, 1)
        return grid

    def tab_custom(self):
        grid = self.grid()
        self.custom_target = Gtk.DropDown.new_from_strings(
            ["currency", "upgrade", "score", "multiplier", "json", "select"]
        )
        self.custom_target.set_hexpand(True)
        self.custom_args = Gtk.Entry()
        self.custom_args.set_hexpand(True)
        self.custom_args.set_placeholder_text("e.g. 2 500000")
        apply = Gtk.Button(label="Apply")
        apply.add_css_class("suggested-action")
        apply.connect("clicked", self.on_custom)

        grid.attach(self.label("Target"), 0, 0, 1, 1)
        grid.attach(self.custom_target, 1, 0, 1, 1)
        grid.attach(self.label("Arguments"), 0, 1, 1, 1)
        grid.attach(self.custom_args, 1, 1, 1, 1)
        grid.attach(apply, 1, 2, 1, 1)
        grid.attach(
            self.label(
                "currency 2 500000  |  upgrade jetpack 6  |  score 999999999  |  "
                "multiplier 99  |  json wallet currencies.2.value 123  |  "
                "select char holly partyOutfit",
                True,
            ),
            0,
            3,
            2,
            1,
        )
        return grid

    def tab_browse(self):
        grid = self.grid()
        self.list_type = Gtk.DropDown.new_from_strings(
            ["characters", "outfits", "boards", "portraits", "frames", "backgrounds", "currencies"]
        )
        self.list_type.set_hexpand(True)
        self.list_search = Gtk.Entry()
        self.list_search.set_placeholder_text("search (optional)")
        self.list_search.set_hexpand(True)
        self.list_char = Gtk.Entry()
        self.list_char.set_placeholder_text("character (only for outfits)")
        self.list_char.set_hexpand(True)
        self.list_missing = Gtk.CheckButton(label="Only missing")
        self.list_owned = Gtk.CheckButton(label="Only owned")
        run = Gtk.Button(label="List")
        run.add_css_class("suggested-action")
        run.connect("clicked", self.on_list)

        grid.attach(self.label("Type"), 0, 0, 1, 1)
        grid.attach(self.list_type, 1, 0, 1, 1)
        grid.attach(self.label("Search"), 0, 1, 1, 1)
        grid.attach(self.list_search, 1, 1, 1, 1)
        grid.attach(self.label("Character"), 0, 2, 1, 1)
        grid.attach(self.list_char, 1, 2, 1, 1)
        grid.attach(self.list_missing, 1, 3, 1, 1)
        grid.attach(self.list_owned, 1, 4, 1, 1)
        grid.attach(run, 1, 5, 1, 1)
        return grid

    def tab_backup(self):
        grid = self.grid()
        backup = Gtk.Button(label="Backup now")
        backup.connect("clicked", self.on_backup)
        undo = Gtk.Button(label="Undo last change")
        undo.connect("clicked", self.on_undo)
        self.restore_dir = Gtk.Entry()
        self.restore_dir.set_hexpand(True)
        self.restore_dir.set_placeholder_text("/path/to/backup/folder")
        restore = Gtk.Button(label="Restore")
        restore.connect("clicked", self.on_restore)

        grid.attach(backup, 0, 0, 1, 1)
        grid.attach(undo, 1, 0, 1, 1)
        grid.attach(self.label("Restore folder"), 0, 1, 1, 1)
        grid.attach(self.restore_dir, 1, 1, 1, 1)
        grid.attach(restore, 2, 1, 1, 1)
        grid.attach(self.label("Backups are stored in ~/.subway-tool/backups. Every write also saves an automatic undo snapshot.", True), 0, 2, 3, 1)
        return grid

    # ---------- async plumbing ----------
    def ns(self, **kwargs):
        return Args(
            serial=self.serial.get_text().strip() or None,
            start=self.start_check.get_active(),
            dry_run=self.dry_check.get_active(),
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
                GLib.idle_add(self._after, text, ok)

        threading.Thread(target=worker, daemon=True).start()

    def _after(self, text, ok):
        if text:
            self.append_log(text)
        elif ok:
            self.append_log("OK")
        self.refresh_async()
        return False

    def append_log(self, text):
        buffer = self.log_view.get_buffer()
        prefix = "" if buffer.get_char_count() == 0 else "\n"
        buffer.insert(buffer.get_end_iter(), prefix + text)
        mark = buffer.create_mark(None, buffer.get_end_iter(), False)
        self.log_view.scroll_mark_onscreen(mark)

    def _initial_refresh(self):
        self.refresh_async()
        return False

    def refresh_async(self):
        args = self.ns()

        def worker():
            with OP_LOCK:
                st.SERIAL = args.serial
                out = io.StringIO()
                try:
                    with contextlib.redirect_stdout(out):
                        st.cmd_status(args)
                except Exception as exc:
                    out.write(f"Status error: {exc}\n")
                text = out.getvalue()
                GLib.idle_add(self._set_status, text)

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, text):
        self.status_view.get_buffer().set_text(text)
        return False

    # ---------- actions ----------
    def on_refill(self, *_):
        args = self.ns(
            value=self.refill_value.get_text().strip() or "2000000000",
            only=self.refill_only.get_text().strip() or None,
        )
        self.run_async(lambda: st.cmd_refill(args), args)

    def on_set_currency(self, *_):
        args = self.ns(
            target="currency",
            values=[self.cur_id.get_text().strip(), self.cur_val.get_text().strip()],
        )
        self.run_async(lambda: st.cmd_set(args), args)

    def on_own(self, *_):
        kind = self.dropdown_value(self.own_type)
        if self.own_all.get_active():
            items = ["all"]
        else:
            items = self.parse_ids(self.own_ids.get_text())
        if not items:
            self.append_log("Enter one or more IDs, or tick 'All of this type'.")
            return
        args = self.ns(type=kind, items=items)
        self.run_async(lambda: st.cmd_own(args), args)

    def on_disown(self, *_):
        kind = self.dropdown_value(self.dis_type)
        items = self.parse_ids(self.dis_ids.get_text())
        if not items:
            self.append_log("Enter one or more IDs to remove.")
            return
        args = self.ns(type=kind, items=items)
        self.run_async(lambda: st.cmd_disown(args), args)

    def on_custom(self, *_):
        target = self.dropdown_value(self.custom_target)
        try:
            values = shlex.split(self.custom_args.get_text().strip())
        except ValueError as exc:
            self.append_log(f"ERROR: {exc}")
            return
        if target == "select":
            if not values:
                self.append_log("Use: select char holly partyOutfit  |  select board guardboard")
                return
            args = self.ns(type=values[0], items=values[1:])
            self.run_async(lambda: st.cmd_select(args), args)
            return
        if target in ("currency", "upgrade") and len(values) != 2:
            self.append_log(f"Use: {target} <name/id> <value>")
            return
        if target in ("score", "multiplier") and len(values) != 1:
            self.append_log(f"Use: {target} <value>")
            return
        if target == "json" and len(values) < 3:
            self.append_log("Use: json <file> <dotted.path> <value>")
            return
        args = self.ns(target=target, values=values)
        self.run_async(lambda: st.cmd_set(args), args)

    def on_list(self, *_):
        kind = self.dropdown_value(self.list_type)
        extra = []
        if kind == "outfits":
            char = self.list_char.get_text().strip()
            if not char:
                self.append_log("Enter a character for the outfit list.")
                return
            extra = [char]
        args = self.ns(
            type=kind,
            extra=extra,
            owned=self.list_owned.get_active(),
            missing=self.list_missing.get_active(),
            search=self.list_search.get_text().strip() or None,
        )
        self.run_async(lambda: st.cmd_list(args), args)

    def on_list_kind(self, kind):
        args = self.ns(type=kind, extra=[])
        self.run_async(lambda: st.cmd_list(args), args)

    def on_backup(self, *_):
        args = self.ns()
        self.run_async(lambda: st.cmd_backup(args), args)

    def on_undo(self, *_):
        args = self.ns()
        self.run_async(lambda: st.cmd_undo(args), args)

    def on_restore(self, *_):
        path = self.restore_dir.get_text().strip()
        if not path:
            self.append_log("Enter the path to a backup folder.")
            return
        args = self.ns(dir=path)
        self.run_async(lambda: st.cmd_restore(args), args)


class App(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="com.lander.subwaytool",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.get_active_window()
        if window is None:
            window = MainWindow(self)
        window.present()


def main():
    smoke = "--smoke-test" in sys.argv
    app = App()
    if smoke:
        GLib.timeout_add(1200, lambda: (app.quit(), False)[1])
    app.run([sys.argv[0]])


if __name__ == "__main__":
    main()
