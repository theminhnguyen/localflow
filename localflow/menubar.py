"""Menüleisten-App (rumps): Status, Sprache, Verlauf, Handy-Kopplung, Berechtigungen."""

import logging
import subprocess
import threading

import rumps

from . import config
from .server import lan_ip

log = logging.getLogger("localflow.menubar")

ICON_IDLE = "🎙"
ICON_REC = "🔴"
ICON_BUSY = "⏳"
ICON_LOADING = "🎙…"

LANGS = [("Automatisch", "auto"), ("Deutsch", "de"), ("Englisch", "en")]


class MenubarApp(rumps.App):
    def __init__(self, controller):
        super().__init__(ICON_LOADING, quit_button=None)
        self.controller = controller  # FlowController aus main.py
        self._build_menu()

    # ---- Status-Icon (thread-sicher von überall aufrufbar) ----

    def set_state(self, state: str) -> None:
        icons = {"idle": ICON_IDLE, "rec": ICON_REC, "busy": ICON_BUSY,
                 "loading": ICON_LOADING}
        self.title = icons.get(state, ICON_IDLE)

    # ---- Menü ----

    def _build_menu(self):
        cfg = self.controller.cfg
        self.status_item = rumps.MenuItem("Modell lädt…")
        self.status_item.set_callback(None)

        lang_menu = rumps.MenuItem("Sprache")
        for label, code in LANGS:
            item = rumps.MenuItem(label, callback=self._make_lang_cb(code))
            item.state = 1 if cfg.get("language", "auto") == code else 0
            lang_menu.add(item)

        self.history_menu = rumps.MenuItem("Verlauf")
        self._refresh_history()

        port = cfg.get("server_port", 8790)
        phone = rumps.MenuItem("📱 Handy koppeln")
        phone.add(rumps.MenuItem("QR-Code anzeigen", callback=self._show_qr))
        phone.add(rumps.MenuItem(f"Link kopieren (https://{lan_ip()}:{port})",
                                 callback=self._copy_link))

        self.menu = [
            self.status_item,
            None,
            lang_menu,
            self.history_menu,
            rumps.MenuItem("Letzten Text kopieren", callback=self._copy_last),
            None,
            phone,
            rumps.MenuItem("Wörterbuch bearbeiten", callback=self._open_dict),
            rumps.MenuItem("Snippets bearbeiten", callback=self._open_snippets),
            None,
            rumps.MenuItem("Berechtigungen prüfen", callback=self._check_perms),
            rumps.MenuItem("Beenden", callback=self._quit),
        ]

    def _make_lang_cb(self, code):
        def cb(sender):
            self.controller.set_language(code)
            for item in self.menu["Sprache"].values():
                item.state = 1 if item.title == sender.title else 0
        return cb

    def set_ready(self, model_name: str):
        hotkey = self.controller.cfg.get("hotkey", "alt_r")
        from .hotkey import KEY_NAMES
        key_label = KEY_NAMES.get(hotkey, hotkey)
        self.status_item.title = f"Bereit — {key_label} halten & sprechen"
        self.set_state("idle")
        log.info("Bereit. Modell: %s", model_name)

    def _refresh_history(self):
        # rumps erlaubt das Neubefüllen von Submenüs nur begrenzt; einfach neu setzen
        try:
            self.history_menu.clear()
        except Exception:
            pass
        entries = config.load_history()[:8]
        if not entries:
            empty = rumps.MenuItem("(leer)")
            empty.set_callback(None)
            self.history_menu.add(empty)
            return
        for e in entries:
            label = e["text"][:60] + ("…" if len(e["text"]) > 60 else "")
            self.history_menu.add(rumps.MenuItem(label, callback=self._make_copy_cb(e["text"])))

    def _make_copy_cb(self, text):
        def cb(_):
            subprocess.run(["pbcopy"], input=text.encode("utf-8"))
        return cb

    def notify_result(self, text: str):
        """Nach jedem Diktat: Verlauf im Menü aktualisieren."""
        self._refresh_history()

    # ---- Callbacks ----

    def _copy_last(self, _):
        entries = config.load_history()
        if entries:
            subprocess.run(["pbcopy"], input=entries[0]["text"].encode("utf-8"))

    def _copy_link(self, _):
        port = self.controller.cfg.get("server_port", 8790)
        subprocess.run(["pbcopy"], input=f"https://{lan_ip()}:{port}".encode())

    def _show_qr(self, _):
        import qrcode

        port = self.controller.cfg.get("server_port", 8790)
        url = f"https://{lan_ip()}:{port}"
        img = qrcode.make(url)
        path = config.CONFIG_DIR / "handy-qr.png"
        img.save(path)
        subprocess.run(["open", str(path)])

    def _open_dict(self, _):
        config.ensure_files()
        subprocess.run(["open", "-e", str(config.DICT_FILE)])

    def _open_snippets(self, _):
        config.ensure_files()
        subprocess.run(["open", "-e", str(config.SNIPPETS_FILE)])

    def _check_perms(self, _):
        from .hotkey import permissions_status, request_permissions

        request_permissions()
        s = permissions_status()
        ok = "✅"
        no = "❌ fehlt"
        msg = (
            f"Eingabemonitoring (Hotkey): {ok if s['input_monitoring'] else no}\n"
            f"Bedienungshilfen (Einfügen): {ok if s['accessibility'] else no}\n\n"
            "Falls etwas fehlt: Systemeinstellungen → Datenschutz & Sicherheit,\n"
            "dort 'Terminal' aktivieren und LocalFlow neu starten."
        )
        rumps.alert(title="LocalFlow — Berechtigungen", message=msg)

    def _quit(self, _):
        self.controller.shutdown()
        rumps.quit_application()
