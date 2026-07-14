"""Menüleisten-App (rumps): Status, Einstellungen, Verlauf, Kopplung, Diagnose.

UI-Updates passieren ausschließlich über einen rumps.Timer auf dem Haupt-Thread —
der Controller (andere Threads) setzt nur .state / .history_dirty / .last_error.
"""

import logging
import subprocess
import threading

import rumps

from . import autostart, config
from .server import lan_ip, tailscale_ip

log = logging.getLogger("localflow.menubar")

ICONS = {"loading": "🎙…", "idle": "🎙", "rec": "🔴", "busy": "⏳"}
LANGS = [("Automatisch", "auto"), ("Deutsch", "de"), ("Englisch", "en")]
HOTKEYS = [("Rechte Option (⌥)", "alt_r"), ("Rechte Command (⌘)", "cmd_r"),
           ("Rechte Control (⌃)", "ctrl_r"), ("F13", "f13")]
MODELS = [("Standard — schneller Start (turbo q4)", "turbo-q4"),
          ("Maximal präzise (turbo)", "turbo"),
          ("Klein & flott (small)", "small")]

# (Menü-Titel, Config-Schlüssel)
TOGGLES = [
    ("✨ KI-Feinschliff (lokales LLM)", "llm_enabled"),
    ("🚀 Schnell-Modus: KI nur bei Bedarf", "llm_smart"),
    ("👐 Freihand: Doppel-Tipp rastet ein", "handsfree"),
    ("📲 Handy darf am Mac einfügen", "phone_insert"),
    ("🕘 Verlauf fürs Handy freigeben", "share_history"),
    ("🔊 Töne", "sounds"),
    ("📝 Diktattexte ins Log schreiben (Debug)", "log_texts"),
]


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
            item = rumps.MenuItem(label, callback=self._make_choice_cb(
                "Sprache", code, self.controller.set_language))
            item.state = 1 if cfg.get("language", "auto") == code else 0
            lang_menu.add(item)

        settings = rumps.MenuItem("⚙️ Einstellungen")
        for title, key in TOGGLES:
            item = rumps.MenuItem(title, callback=self._make_toggle_cb(key))
            item.state = 1 if cfg.get(key) else 0
            settings.add(item)
        auto_item = rumps.MenuItem("🚀 Beim Anmelden starten",
                                   callback=self._toggle_autostart)
        auto_item.state = 1 if autostart.enabled() else 0
        settings.add(auto_item)
        hk_menu = rumps.MenuItem("⌨️ Diktier-Taste")
        for label, code in HOTKEYS:
            item = rumps.MenuItem(label, callback=self._make_choice_cb(
                "⌨️ Diktier-Taste", code, self._apply_hotkey, parent=settings))
            item.state = 1 if cfg.get("hotkey", "alt_r") == code else 0
            hk_menu.add(item)
        settings.add(hk_menu)
        model_menu = rumps.MenuItem("🧠 Whisper-Modell")
        for label, code in MODELS:
            item = rumps.MenuItem(label, callback=self._make_choice_cb(
                "🧠 Whisper-Modell", code, self.controller.set_model, parent=settings))
            item.state = 1 if cfg.get("model", "turbo") == code else 0
            model_menu.add(item)
        settings.add(model_menu)

        self.history_menu = rumps.MenuItem("Verlauf")

        phone = rumps.MenuItem("📱 Handy koppeln")
        phone.add(rumps.MenuItem("QR-Code anzeigen (Heim-WLAN)", callback=self._show_qr))
        if tailscale_ip():
            phone.add(rumps.MenuItem("QR-Code anzeigen (unterwegs/Tailscale)",
                                     callback=self._show_qr_tailscale))
        phone.add(rumps.MenuItem("Link kopieren", callback=self._copy_link))
        phone.add(None)
        phone.add(rumps.MenuItem("Kopplung zurücksetzen…", callback=self._reset_pairing))

        diagnose = rumps.MenuItem("🩺 Diagnose")
        diagnose.add(rumps.MenuItem("Status anzeigen", callback=self._show_status))
        diagnose.add(rumps.MenuItem("Log-Datei öffnen", callback=self._open_log))
        diagnose.add(rumps.MenuItem("Log leeren", callback=self._clear_logs))
        diagnose.add(rumps.MenuItem("Berechtigungen prüfen", callback=self._check_perms))

        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem("Audiodatei transkribieren…", callback=self._transcribe_file),
            lang_menu,
            self.history_menu,
            rumps.MenuItem("Letzten Text kopieren", callback=self._copy_last),
            None,
            phone,
            settings,
            rumps.MenuItem("Wörterbuch bearbeiten", callback=self._open_dict),
            rumps.MenuItem("Snippets bearbeiten", callback=self._open_snippets),
            None,
            diagnose,
            rumps.MenuItem("Beenden", callback=self._quit),
        ]
        self._refresh_history()

    # ---- Menü-Helfer ----

    def _make_toggle_cb(self, key):
        def cb(sender):
            new = not bool(self.controller.cfg.get(key))
            self.controller.set_toggle(key, new)
            sender.state = 1 if new else 0
            if key == "llm_enabled" and new:
                from . import llm

                st = llm.status(self.controller.cfg)
                if st["ready"]:
                    rumps.alert(
                        title="LocalFlow — KI-Feinschliff",
                        message=f"Aktiv über {st['backend']} mit Modell "
                                f"'{st['model']}'. ✨")
                else:
                    rumps.alert(
                        title="LocalFlow — KI-Feinschliff",
                        message=("Noch kein lokales LLM aktiv. Der Feinschliff bleibt "
                                 "an und greift automatisch, sobald eines läuft.\n\n"
                                 "• LM Studio: App öffnen, ein Modell laden, "
                                 "'Local Server' starten (Port 1234).\n"
                                 "• oder Ollama: 'brew services start ollama' + "
                                 "'ollama pull gemma3:4b'."))
        return cb

    def _make_choice_cb(self, menu_title, code, apply_fn, parent=None):
        def cb(sender):
            apply_fn(code)
            root = parent if parent is not None else self.menu
            for item in root[menu_title].values():
                item.state = 1 if item.title == sender.title else 0
        return cb

    def _apply_hotkey(self, code):
        self.controller.set_hotkey(code)
        from .hotkey import KEY_NAMES

        self.status_item.title = f"Bereit — {KEY_NAMES.get(code, code)} halten & sprechen"

    def _toggle_autostart(self, sender):
        if autostart.enabled():
            ok = autostart.disable()
            sender.state = 0 if ok else 1
        else:
            ok = autostart.enable()
            sender.state = 1 if ok else 0

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
        else:
            for e in entries:
                icon = "📱 " if e.get("source") == "phone" else ""
                label = icon + e["text"][:60] + ("…" if len(e["text"]) > 60 else "")
                self.history_menu.add(
                    rumps.MenuItem(label, callback=self._make_copy_cb(e["text"]))
                )
        self.history_menu.add(None)
        self.history_menu.add(rumps.MenuItem("Verlauf leeren", callback=self._clear_history))

    def _clear_history(self, _):
        config.clear_history()
        self._refresh_history()

    def _make_copy_cb(self, text):
        def cb(_):
            subprocess.run(["pbcopy"], input=text.encode("utf-8"))
        return cb

    # ---- Aktionen ----

    def _transcribe_file(self, _):
        r = subprocess.run(
            ["osascript", "-e",
             'POSIX path of (choose file with prompt '
             '"Audio- oder Videodatei transkribieren:")'],
            capture_output=True, text=True,
        )
        path = r.stdout.strip()
        if r.returncode != 0 or not path:
            return  # abgebrochen

        def work():
            try:
                out = self.controller.transcribe_file(path)
                subprocess.run(["open", "-e", out])
            except Exception:
                log.exception("Datei-Transkription fehlgeschlagen")
                self.controller._remember_error(
                    "Datei-Transkription fehlgeschlagen (Format nicht lesbar?)")

        threading.Thread(target=work, daemon=True).start()

    def _copy_last(self, _):
        entries = config.load_history()
        if entries:
            subprocess.run(["pbcopy"], input=entries[0]["text"].encode("utf-8"))

    def _url(self, ip=None):
        port = self.controller.cfg.get("server_port", 8790)
        token = config.load_or_create_token()
        # Token als URL-Fragment ("#k="): Fragmente werden vom Browser NIE mitgesendet
        # (auch nicht an den eigenen Server) und tauchen darum in keinem Zugriffs-Log auf.
        return f"https://{ip or lan_ip()}:{port}/#k={token}"

    def _copy_link(self, _):
        subprocess.run(["pbcopy"], input=self._url().encode())

    def _show_qr(self, _):
        self._render_qr(self._url(), "handy-qr.png")

    def _show_qr_tailscale(self, _):
        ts = tailscale_ip()
        if ts:
            self._render_qr(self._url(ts), "handy-qr-tailscale.png")

    def _render_qr(self, url, filename):
        import qrcode

        img = qrcode.make(url)
        path = config.CONFIG_DIR / filename
        img.save(path)
        subprocess.run(["open", str(path)])

    def _reset_pairing(self, _):
        resp = rumps.alert(
            title="LocalFlow — Kopplung zurücksetzen",
            message=("Alle bisher gekoppelten Handys verlieren den Zugriff und "
                     "müssen den QR-Code erneut scannen.\n\nFortfahren?"),
            ok="Zurücksetzen", cancel="Abbrechen",
        )
        if resp == 1:
            config.reset_token()
            rumps.alert(title="LocalFlow",
                       message="Kopplung zurückgesetzt. Zeig den neuen QR-Code "
                               "erneut an, damit sich Handys neu koppeln können.")

    def _open_dict(self, _):
        config.ensure_files()
        subprocess.run(["open", "-e", str(config.DICT_FILE)])

    def _open_snippets(self, _):
        config.ensure_files()
        subprocess.run(["open", "-e", str(config.SNIPPETS_FILE)])

    def _show_status(self, _):
        rumps.alert(title="LocalFlow — Status",
                    message=self.controller.status_report())

    def _open_log(self, _):
        logfile = config.LOG_DIR / "localflow.log"
        if logfile.exists():
            subprocess.run(["open", "-e", str(logfile)])
        else:
            rumps.alert(title="LocalFlow", message="Noch keine Log-Datei vorhanden.")

    def _clear_logs(self, _):
        n = config.clear_logs()
        rumps.alert(title="LocalFlow",
                   message=f"{n} Log-Datei(en) geleert." if n
                           else "Keine Log-Dateien gefunden.")

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
                "dort 'LocalFlow' bei beiden Punkten aktivieren\n"
                "und LocalFlow neu starten."
            ),
        )

    def _quit(self, _):
        self.controller.shutdown()
        rumps.quit_application()
