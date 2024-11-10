#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import os
import json
import subprocess
from pathlib import Path

class HyprSwitcher(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='hypr-switcher')
        self.windows = []
        self.filtered_windows = []
        self.list_has_focus = False

    def do_activate(self):
        self.win = Gtk.ApplicationWindow(application=self)
        self.win.set_title("HyprSwitcher")
        self.win.set_default_size(600, 400)

        css_provider = Gtk.CssProvider()
        config_dir = Path(os.getenv('XDG_CONFIG_HOME', Path.home() / '.config')) / 'hypr-switcher'
        config_dir.mkdir(parents=True, exist_ok=True)
        css_file = config_dir / 'style.css'

        if not css_file.exists():
            css_file.write_text(DEFAULT_CSS)

        css_provider.load_from_path(str(css_file))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.win.set_child(main_box)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_css_classes(['search-box'])

        search_label = Gtk.Label(label="Search: ")
        search_label.set_css_classes(['search-label'])
        search_box.append(search_label)

        self.search_entry = Gtk.Entry()
        self.search_entry.connect('changed', self.on_search_changed)
        self.search_entry.set_hexpand(True)
        search_box.append(self.search_entry)

        main_box.append(search_box)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self.on_key_pressed)
        self.search_entry.add_controller(key_controller)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        main_box.append(scrolled)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.set_css_classes(['window-list'])
        self.list_box.connect('row-activated', self.on_row_activated)
        scrolled.set_child(self.list_box)

        list_key_controller = Gtk.EventControllerKey()
        list_key_controller.connect('key-pressed', self.on_list_key_pressed)
        self.list_box.add_controller(list_key_controller)

        focus_controller = Gtk.EventControllerFocus()
        focus_controller.connect('enter', self.on_list_focus_enter)
        focus_controller.connect('leave', self.on_list_focus_leave)
        self.list_box.add_controller(focus_controller)

        self.load_windows()
        self.display_windows(self.windows)

        self.search_entry.grab_focus()
        self.win.present()

    def on_list_focus_enter(self, controller):
        self.list_has_focus = True

    def on_list_focus_leave(self, controller):
        self.list_has_focus = False

    def load_windows(self):
        try:
            result = subprocess.run(['hyprctl', 'clients', '-j'],
                                 capture_output=True, text=True)
            clients = json.loads(result.stdout)

            workspace_result = subprocess.run(['hyprctl', 'activeworkspace', '-j'],
                                           capture_output=True, text=True)
            active_workspace = json.loads(workspace_result.stdout)['id']

            self.windows = []
            for client in clients:
                if not client['class'] or client['class'] in ['unset', 'UNSET']:
                    continue

                self.windows.append({
                    'title': client['title'],
                    'class': client['class'],
                    'workspace': client['workspace']['id'],
                    'address': client['address'],
                    'active': client['workspace']['id'] == active_workspace
                })

            # Sort windows: active workspace first, then by title
            self.windows.sort(key=lambda x: (-x['active'], x['title'].lower()))

        except Exception as e:
            print(f"Error loading windows: {e}")
            self.windows = []

    def display_windows(self, windows_to_show):
        while True:
            child = self.list_box.get_first_child()
            if child is None:
                break
            self.list_box.remove(child)

        self.filtered_windows = windows_to_show
        for window in windows_to_show:
            self.list_box.append(self.create_window_row(window))

        if self.list_has_focus:
            first_row = self.list_box.get_row_at_index(0)
            if first_row:
                self.list_box.select_row(first_row)

    def create_window_row(self, window):
        list_box_row = Gtk.ListBoxRow()
        list_box_row.window_data = window

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_css_classes(['window-row'])

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_hexpand(True)

        title_label = Gtk.Label(label=window['title'])
        title_label.set_css_classes(['window-title'])
        title_label.set_halign(Gtk.Align.START)
        text_box.append(title_label)

        info_label = Gtk.Label(
            label=f"{window['class']} (Workspace {window['workspace']})")
        info_label.set_css_classes(['window-info'])
        info_label.set_halign(Gtk.Align.START)
        text_box.append(info_label)

        row.append(text_box)
        list_box_row.set_child(row)

        return list_box_row

    def on_search_changed(self, entry):
        search_text = entry.get_text().lower()
        if search_text:
            filtered = [
                window for window in self.windows
                if search_text in window['title'].lower() or
                   search_text in window['class'].lower()
            ]
            filtered.sort(key=lambda x: (
                not x['title'].lower().startswith(search_text),
                not x['class'].lower().startswith(search_text),
                not x['active'],
                x['title'].lower()
            ))
        else:
            filtered = self.windows

        self.display_windows(filtered)

    def focus_window(self, window):
        try:
            subprocess.run(['hyprctl', 'dispatch', 'workspace',
                          str(window['workspace'])])

            subprocess.run(['hyprctl', 'dispatch', 'focuswindow',
                          f'address:{window["address"]}'])

            self.win.close()
        except Exception as e:
            print(f"Error focusing window: {e}")

    def on_row_activated(self, list_box, row):
        if row and hasattr(row, 'window_data'):
            self.focus_window(row.window_data)

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Down:
            first_row = self.list_box.get_row_at_index(0)
            if first_row:
                self.list_box.select_row(first_row)
                first_row.grab_focus()
                self.list_has_focus = True
            return True
        elif keyval == Gdk.KEY_Up:
            last_row = self.list_box.get_row_at_index(len(self.filtered_windows) - 1)
            if last_row:
                self.list_box.select_row(last_row)
                last_row.grab_focus()
                self.list_has_focus = True
            return True
        elif keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False

    def move_selection(self, direction):
        current_row = self.list_box.get_selected_row()
        if current_row:
            current_index = current_row.get_index()
            if direction == 'up' and current_index > 0:
                new_row = self.list_box.get_row_at_index(current_index - 1)
                self.list_box.select_row(new_row)
                new_row.grab_focus()
            elif direction == 'down' and current_index < len(self.filtered_windows) - 1:
                new_row = self.list_box.get_row_at_index(current_index + 1)
                self.list_box.select_row(new_row)
                new_row.grab_focus()

    def on_list_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Up:
            current_row = self.list_box.get_selected_row()
            if current_row and current_row.get_index() == 0:
                self.search_entry.grab_focus()
                self.list_box.unselect_all()
                self.list_has_focus = False
            else:
                self.move_selection('up')
            return True
        elif keyval == Gdk.KEY_Down:
            self.move_selection('down')
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_Right):
            selected_row = self.list_box.get_selected_row()
            if selected_row:
                self.focus_window(selected_row.window_data)
            return True
        elif keyval == Gdk.KEY_Escape:
            self.win.close()
            return True
        return False

DEFAULT_CSS = """
window {
    background-color: #1a1b26;
    color: #a9b1d6;
}

/* Hide scrollbar */
scrolledwindow undershoot.top,
scrolledwindow undershoot.bottom,
scrolledwindow overshoot.top,
scrolledwindow overshoot.bottom,
scrolledwindow scrollbar {
    opacity: 0;
    -gtk-icon-size: 0;
    min-width: 0;
    min-height: 0;
}

.search-box {
    margin: 8px 12px;
    padding: 0;
}

.search-label {
    font-family: monospace;
    font-size: 14px;
    color: #7aa2f7;
    margin-right: 8px;
}

entry {
    font-family: monospace;
    font-size: 14px;
    background: transparent;
    color: #a9b1d6;
    border: none;
    box-shadow: none;
    padding: 0;
    margin: 0;
    min-height: 0;
    outline: none;
    -gtk-outline-radius: 0;
}

.window-list {
    margin: 0 8px;
    background: transparent;
}

.window-row {
    padding: 8px 12px;
    background-color: transparent;
    color: #a9b1d6;
}

.window-title {
    font-family: monospace;
    font-size: 13px;
    color: #7aa2f7;
}

.window-info {
    font-family: monospace;
    font-size: 12px;
    color: #565f89;
}

row {
    padding-left: 12px;
    transition: none;
}

.window-list {
    counter-reset: row-number;
}

row {
    counter-increment: row-number;
}

row:not(:selected)::before {
    content: " " counter(row-number) ")";
    font-family: monospace;
    color: #565f89;
    margin-right: 8px;
}

row:selected {
    background: transparent;
}

row:selected::before {
    content: ">" counter(row-number) ")";
    font-family: monospace;
    color: #7aa2f7;
    margin-right: 8px;
}

row:selected .window-title {
    color: #7aa2f7;
}

row:selected .window-info {
    color: #a9b1d6;
}

/* Removes default GTK selection styling */
row:selected:focus {
    outline: none;
    box-shadow: none;
}
"""

if __name__ == '__main__':
    app = HyprSwitcher()
    app.run()
