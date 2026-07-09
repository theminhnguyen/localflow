"""Menüleisten-App (rumps): Status, Sprache, Verlauf, Handy-Kopplung, Berechtigungen.

UI-Updates passieren ausschließlich über einen rumps.Timer auf dem Haupt-Thread —
der Controller (andere Threads) setzt nur .state / .history_dirty / .last_error.
"""

import logging
import subprocess

import rumps

from . import config
from .server import lan_ip

log = logging.getLogger("localflow.menubar")

ICONS = {"loading": "🎙…", "idle": "🎙", "rec": "🔴", "busy": "⏳"}
LANGS = [("Automatisch", "auto"), ("Deutsch", "de"), ("Englisch", "en")]


class MenubarApp(rumps.App):
    def __init__(self, controller):
        super().__init__(ICONS["loading"], quit_button=None)
        self.controller = controller
        self._shown_state = None
        self._ready_shown = False
        self._build_menu()
        self._timer = rumps.Timer(self._tick, 0.3)
        self._timer.start()

    # ---- Haupt-Thread-Tick: Icon, Status-Zeile, Verlauf, Fehler ----

    def _tick(self, _):
        c = self.controller
        if c.state != self._shown_state:
            self._shown_state = c.state
            self.title = ICONS.get(c.state, ICONS["idle"])

        if not self._ready_shown and c.engine.loaded:
            self._ready_shown = True
            from .hotkey import KEY_NAMES

            key = c.cfg.get("hotkey", "alt_r")
            self.status_item.title = f"Bereit — {KEY_NAMES.get(key, key)} halten & sprechen"

        if c.history_dirty:
            c.history_dirty = False
            self._refresh_history()

        if c.last_error:
            msg, c.last_error = c.last_error, ""
            try:
                rumps.notification("LocalFlow", "", msg)
            except Exception:
                log.warning("Hinweis: %s", msg)

    # ---- Menü ----

    def _build_menu(self):
        cfg = self.controller.cfg
        self.status_item = rumps.MenuItem("Modell lädt… (erster Start: Download)")
        self.status_item.set_callback(None)

        lang_menu = rumps.MenuItem("Sprache")
        for label, code in LANGS:
            item = rumps.MenuItem(label, callback=self._make_lang_cb(code))
            item.state = 1 if cfg.get("language", "auto") == code else 0
            lang_menu.add(item)

        self.history_menu = rumps.MenuItem("Verlauf")

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
        self._refresh_history()

    def _make_lang_cb(self, code):
        def cb(sender):
            self.controller.set_language(code)
            for item in self.menu["Sprache"].values():
                item.state = 1 if item.title == sender.title else 0
        return cb

    def _refresh_history(self):
        # rumps legt das Untermenü (NSMenu) erst an, wenn es Einträge hat —
        # clear() auf einem noch leeren Submenü wirft AttributeError. Das ist
        # nur der Erst-Aufbau (nichts zu leeren), daher gezielt überspringen.
        try:
            self.history_menu.clear()
        except AttributeError:
            pass
        entries = config.load_history()[:8]
        if not entries:
            empty = rumps.MenuItem("(leer)")
            empty.set_callback(None)
            self.history_menu.add(empty)
            return
        for e in entries:
            label = e["text"][:60] + ("…" if len(e["text"]) > 60 else "")
            self.history_menu.add(
                rumps.MenuItem(label, callback=self._make_copy_cb(e["text"]))
            )

    def _make_copy_cb(self, text):
        def cb(_):
            subprocess.run(["pbcopy"], input=text.encode("utf-8"))
        return cb

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
        ok, no = "✅", "❌ fehlt"
        rumps.alert(
            title="LocalFlow — Berechtigungen",
            message=(
                f"Eingabemonitoring (Hotkey): {ok if s['input_monitoring'] else no}\n"
                f"Bedienungshilfen (Einfügen): {ok if s['accessibility'] else no}\n\n"
                "Falls etwas fehlt: Systemeinstellungen → Datenschutz & Sicherheit,\n"
                "dort 'Terminal' bei beiden Punkten aktivieren\n"
                "und LocalFlow neu starten."
            ),
        )

    def _quit(self, _):
        self.controller.shutdown()
        rumps.quit_application()
