"""Menüleisten-App (rumps): Status, Einstellungen, Verlauf, Kopplung, Diagnose.

UI-Updates passieren ausschließlich über einen rumps.Timer auf dem Haupt-Thread —
der Controller (andere Threads) setzt nur .state / .history_dirty / .last_error.
"""

import logging
import subprocess
import threading

import rumps

from . import autostart, config, onboarding
from .inserter import copy_to_clipboard
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
    ("🔄 Auf Updates prüfen", "update_check"),
]


class MenubarApp(rumps.App):
    def __init__(self, controller):
        super().__init__(ICONS["loading"], quit_button=None)
        self.controller = controller
        self._shown_state = None
        self._ready_shown = False
        self._in_tick = False  # Reentranz-Schutz (rumps.alert blockiert modal)
        # Onboarding: läuft nur beim allerersten Start (oder nach manuellem
        # Reset über 🩺 → "Einrichtung erneut starten"), getrieben vom selben
        # Tick wie der Rest der App — siehe onboarding.py für die Details.
        self._onb_active = not onboarding.is_onboarded()
        self._onb_stage = onboarding.WELCOME
        self._onb_initial_perms = None
        self._onb_download_started = False
        self._build_menu()
        self._timer = rumps.Timer(self._tick, 0.3)
        self._timer.start()

    # ---- Haupt-Thread-Tick: Icon, Status-Zeile, Verlauf, Fehler ----

    def _tick(self, _):
        if self._in_tick:
            return  # falls ein verschachtelter Timer-Fire während eines
                     # blockierenden rumps.alert() durchkäme
        self._in_tick = True
        try:
            self._tick_body()
        finally:
            self._in_tick = False

    def _tick_body(self):
        c = self.controller
        if c.state != self._shown_state:
            self._shown_state = c.state
            self.title = ICONS.get(c.state, ICONS["idle"])

        if self._onb_active:
            self._onboarding_tick()
            return  # keine weiteren Alerts/Status-Updates, solange Einrichtung läuft

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

        if c.update_available and self.update_item.hidden:
            self.update_item.title = f"⬆️ Update {c.update_available['tag']} verfügbar…"
            self.update_item.hidden = False

        if c.update_check_message:
            msg, c.update_check_message = c.update_check_message, ""
            rumps.alert(title="LocalFlow — Update-Check", message=msg)

    # ---- Menü ----

    def _build_menu(self):
        cfg = self.controller.cfg
        self.status_item = rumps.MenuItem("Modell lädt… (erster Start: Download)")
        self.status_item.set_callback(None)

        # Dauerhaft im Menü, aber unsichtbar bis eine neuere Version gefunden
        # wird (.hidden statt Ein-/Ausbauen — vermeidet Anker-Key-Fallstricke
        # bei rumps, siehe insert_before/after-Doku).
        self.update_item = rumps.MenuItem("⬆️ Update verfügbar…", callback=self._open_update)
        self.update_item.hidden = True

        lang_menu = rumps.MenuItem("Sprache")
        for label, code in LANGS:
            item = rumps.MenuItem(label, callback=self._make_choice_cb(
                "Sprache", code, self.controller.set_language))
            item.state = 1 if cfg.get("language", "auto") == code else 0
            lang_menu.add(item)

        settings = rumps.MenuItem("⚙️ Einstellungen")
        settings.add(rumps.MenuItem("Einstellungen im Browser öffnen…",
                                    callback=self._open_settings_page))
        settings.add(None)
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
        diagnose.add(rumps.MenuItem("Jetzt nach Updates suchen", callback=self._check_updates_now))
        diagnose.add(rumps.MenuItem("Einrichtung erneut starten", callback=self._restart_onboarding))

        self.menu = [
            self.status_item,
            self.update_item,
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
            copy_to_clipboard(text)
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
            copy_to_clipboard(entries[0]["text"])

    def _url(self, ip=None, path=""):
        port = self.controller.cfg.get("server_port", 8790)
        token = config.load_or_create_token()
        # Token als URL-Fragment ("#k="): Fragmente werden vom Browser NIE mitgesendet
        # (auch nicht an den eigenen Server) und tauchen darum in keinem Zugriffs-Log auf.
        return f"https://{ip or lan_ip()}:{port}/{path}#k={token}"

    def _copy_link(self, _):
        copy_to_clipboard(self._url())

    def _open_settings_page(self, _):
        # 127.0.0.1 statt LAN-IP: wir öffnen sie vom Mac selbst aus, und das
        # Zertifikat deckt 127.0.0.1 immer ab (siehe server.ensure_cert()).
        subprocess.run(["open", self._url(ip="127.0.0.1", path="settings")])

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

        lines = [
            f"Eingabemonitoring (Hotkey): {ok if s['input_monitoring'] else no}",
            f"Bedienungshilfen (Einfügen): {ok if s['accessibility'] else no}",
            "",
            f"Diese App läuft aus:\n{onboarding.running_app_path()}",
        ]

        others = onboarding.other_app_copies()
        if others:
            lines += [
                "",
                "⚠️ ACHTUNG: Es gibt weitere LocalFlow-Kopien auf diesem Mac:",
                *[f"  • {p}" for p in others],
                "",
                "macOS behandelt jede Kopie als EIGENE App — die Berechtigungen "
                "gelten nur für die, die du dort freigegeben hast. Lösche die "
                "überzähligen Kopien und starte nur die aus /Programme.",
            ]
        elif not (s["input_monitoring"] and s["accessibility"]):
            lines += [
                "",
                "Fehlt etwas? Systemeinstellungen → Datenschutz & Sicherheit → "
                "dort 'LocalFlow' aktivieren und LocalFlow neu starten.",
                "",
                "Hinweis: Stehen dort mehrere 'LocalFlow'-Einträge, entferne die "
                "alten mit dem Minus-Knopf und aktiviere nur einen.",
            ]

        rumps.alert(title="LocalFlow — Berechtigungen", message="\n".join(lines))

    def _open_update(self, _):
        info = self.controller.update_available
        if info:
            subprocess.run(["open", info["url"]])

    def _check_updates_now(self, _):
        # Netzwerk-Aufruf im Hintergrund; das Ergebnis holt sich der nächste
        # Menü-Tick über controller.update_check_message (Haupt-Thread-Regel).
        threading.Thread(
            target=lambda: self.controller.check_for_update_now(manual=True),
            daemon=True,
        ).start()

    # ---- Einrichtungs-Assistent (nur beim allerersten Start) ----

    def _onboarding_tick(self):
        try:
            self._onboarding_step()
        except Exception:
            log.exception("Einrichtung fehlgeschlagen — überspringe, App startet normal")
            self._abort_onboarding()

    def _abort_onboarding(self):
        """Bricht die Einrichtung defensiv ab. Wird aus einem except-Block
        gerufen -> darf unter KEINEN Umständen selbst eine Exception werfen
        (kein rumps.alert hier, das war schon der Fehlerauslöser)."""
        try:
            from . import __version__

            onboarding.mark_onboarded(__version__)
        except Exception:
            log.exception("Onboarding-Marker konnte nicht gesetzt werden")
        self._onb_active = False

    def _onboarding_step(self):
        stage = self._onb_stage
        if stage == onboarding.WELCOME:
            rumps.alert(
                title="Willkommen bei LocalFlow — Schritt 1 von 4",
                message=("LocalFlow diktiert komplett lokal auf deinem Mac — "
                         "keine Cloud, kein Abo.\n\nGleich fragt macOS nach ein "
                         "paar Berechtigungen und lädt einmalig das Spracherkennungs-"
                         "Modell (~600 MB). Das dauert nur beim ersten Start."),
            )
            self._onb_stage = onboarding.MICROPHONE
        elif stage == onboarding.MICROPHONE:
            rumps.alert(
                title="Schritt 2 von 4 — Mikrofon",
                message=("Als Nächstes fragt macOS nach dem Mikrofon-Zugriff — "
                         "bitte erlauben, sonst kann LocalFlow nicht zuhören.\n\n"
                         "Klicke OK, um kurz das Mikrofon zu testen."),
            )
            self._try_mic_prompt()
            self._onb_stage = onboarding.PERMISSIONS
            self._onb_initial_perms = None
        elif stage == onboarding.PERMISSIONS:
            self._onboarding_permissions_step()
        elif stage == onboarding.RESTART:
            self._onboarding_restart_step()
        elif stage == onboarding.MODEL:
            self._onboarding_model_step()
        elif stage == onboarding.DONE:
            self._finish_onboarding()

    def _try_mic_prompt(self):
        """Öffnet kurz das Mikrofon, um den macOS-Berechtigungs-Dialog auszulösen.

        Erfolg ist nicht zuverlässig abfragbar (macOS liefert das erst beim
        nächsten echten Zugriff) — wir blockieren also nicht darauf.
        """
        try:
            import sounddevice as sd

            with sd.InputStream(samplerate=16000, channels=1, dtype="float32"):
                pass
        except Exception:
            log.debug("Mikrofon-Probe fehlgeschlagen (kein Gerät? bereits entschieden?)",
                     exc_info=True)

    def _onboarding_permissions_step(self):
        import time

        from .hotkey import permissions_status, request_permissions

        if self._onb_initial_perms is None:
            # Erster Tick in diesem Schritt: Dialoge/Fenster EINMALIG anstoßen,
            # danach nur noch still pollen (kein Dialog-Spam pro Tick).
            request_permissions()
            self._onb_initial_perms = dict(permissions_status())
            self._onb_perm_wait_since = time.monotonic()
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference."
                                    "security?Privacy_ListenEvent"])
            subprocess.run(["open", "x-apple.systempreferences:com.apple.preference."
                                    "security?Privacy_Accessibility"])
            rumps.alert(
                title="Schritt 3 von 4 — Berechtigungen",
                message=("Bitte aktiviere 'LocalFlow' in BEIDEN gerade geöffneten "
                         "Fenstern (Eingabemonitoring + Bedienungshilfen).\n\n"
                         "Wichtig: Aktiviere die App unter '/Programme' — falls dort "
                         "mehrere 'LocalFlow'-Einträge stehen, entferne die alten "
                         "mit dem Minus-Knopf.\n\n"
                         "Danach geht es automatisch weiter."),
            )
            self.status_item.title = "⏳ Warte auf Berechtigungen…"
            return

        current = permissions_status()
        action = onboarding.permissions_step_action(self._onb_initial_perms, current)
        if action == "wait":
            # Ausweg aus der Warteschleife: CGPreflight* meldet bei ad-hoc
            # signierten Apps auch nach dem Setzen der Häkchen weiterhin False
            # (Wert ist pro Prozess gecacht). Ohne diesen Ausstieg würde der
            # Assistent hier endlos hängen — genau der Bug, den der Nutzer sah.
            waited = time.monotonic() - getattr(self, "_onb_perm_wait_since", 0)
            if waited > onboarding.PERMISSION_WAIT_TIMEOUT_S:
                self._onb_stage = onboarding.RESTART
            return
        self._onb_stage = onboarding.RESTART if action == "restart" else onboarding.MODEL

    def _onboarding_restart_step(self):
        # Marker JETZT setzen, VOR dem Neustart: sonst sieht die frisch
        # gestartete Instanz "nicht onboarded" und beginnt von vorn —
        # eine Endlosschleife (Nutzer-Bug: "fängt immer wieder neu an").
        # Nach dem Neustart übernimmt der normale Betrieb; fehlende
        # Berechtigungen meldet die App dann über 🩺 Diagnose statt den
        # Assistenten erneut zu starten.
        try:
            from . import __version__

            onboarding.mark_onboarded(__version__)
        except Exception:
            log.exception("Onboarding-Marker konnte vor dem Neustart nicht gesetzt werden")

        rumps.alert(
            title="Fast fertig — LocalFlow startet neu",
            message=("LocalFlow startet jetzt einmal neu, damit die erteilten "
                     "Berechtigungen greifen.\n\nFalls die Diktier-Taste danach "
                     "nicht reagiert: 🩺 Diagnose → 'Berechtigungen prüfen' zeigt "
                     "dir, was noch fehlt."),
        )
        try:
            onboarding.restart_app()  # ersetzt den Prozess -> kehrt bei Erfolg nie zurück
        except Exception:
            log.exception("Automatischer Neustart fehlgeschlagen")
            rumps.alert(
                title="LocalFlow",
                message=("Bitte beende LocalFlow jetzt über 'Beenden' und öffne es "
                         "danach erneut — die Einrichtung ist gespeichert."),
            )
            self.controller.shutdown()
            rumps.quit_application()

    def _onboarding_model_step(self):
        if not self._onb_download_started:
            self._onb_download_started = True
            self.status_item.title = "Lädt Whisper-Modell… 0%"
            rumps.alert(
                title="Schritt 4 von 4 — Spracherkennung laden",
                message=("LocalFlow lädt jetzt einmalig das Whisper-Modell "
                         "(~600 MB). Je nach Internetverbindung dauert das ein "
                         "bis zwei Minuten — LocalFlow macht danach von selbst weiter."),
            )
            threading.Thread(target=self._download_model_bg, daemon=True).start()
            return

        if self.controller.engine.loaded:
            self._onb_stage = onboarding.DONE

    def _download_model_bg(self):
        def on_progress(pct):
            self.status_item.title = f"Lädt Whisper-Modell… {pct}%"

        try:
            onboarding.download_with_progress(self.controller.engine.repo, on_progress)
        except Exception:
            # Kein Beinbruch: controller.start() hat engine.warmup_async() schon
            # parallel angestoßen und versucht den Download so oder so erneut.
            log.debug("Fortschritts-Download im Onboarding fehlgeschlagen", exc_info=True)

    def _finish_onboarding(self):
        from . import __version__

        onboarding.mark_onboarded(__version__)
        self._onb_active = False
        rumps.alert(
            title="Fertig! 🎉",
            message=("LocalFlow ist eingerichtet.\n\nHalte die rechte Options-"
                     "taste (⌥), sprich, lass los — dein Text erscheint an der "
                     "Cursor-Position."),
        )

    def _restart_onboarding(self, _):
        resp = rumps.alert(
            title="LocalFlow — Einrichtung",
            message="Den Einrichtungsassistenten jetzt erneut durchlaufen?",
            ok="Starten", cancel="Abbrechen",
        )
        if resp == 1:
            onboarding.reset_onboarding()
            self._onb_stage = onboarding.WELCOME
            self._onb_initial_perms = None
            self._onb_download_started = False
            self._onb_active = True

    def _quit(self, _):
        self.controller.shutdown()
        rumps.quit_application()
