# LocalFlow 🎙️

[![CI](https://github.com/theminhnguyen/localflow/actions/workflows/ci.yml/badge.svg)](https://github.com/theminhnguyen/localflow/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/theminhnguyen/localflow?label=release)](https://github.com/theminhnguyen/localflow/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

*[Auf Deutsch lesen](README.de.md)*

**A dictation app like [Wispr Flow](https://wisprflow.ai) — but 100% local, free, and offline.**
Your voice is turned into text right on your Mac (Whisper). Nothing goes to the
cloud, no subscription, no account.

- **On Mac:** hold a key, speak, release — the text appears at your cursor, in **any** app.
- **On iPhone:** a web app on your home WLAN — tap to record, copy the text, or send it **straight to your Mac's cursor**.

---

## What it does

| Feature | LocalFlow |
|---|---|
| System-wide dictation on Mac | ✅ hold a key & speak |
| Hands-free mode | ✅ double-tap the key to lock recording on |
| Local speech recognition | ✅ Whisper (`large-v3-turbo`) on the Apple-Silicon GPU |
| German + 90 languages | ✅ auto-detect or pin one |
| ✨ AI polish | ✅ local LLM (LM Studio/Ollama): fixes false starts, formats lists |
| Filler-word removal (um, uh…) | ✅ rule-based, always on |
| Personal dictionary & snippets | ✅ |
| iPhone as a remote mic | ✅ "→ Mac" inserts text at your Mac's cursor |
| Transcribe audio files | ✅ voice memo/meeting → text file |
| Dictate on the go | ✅ automatic if Tailscale is installed |
| Launch at login | ✅ toggle in settings |
| Guided first-run setup | ✅ walks through every step |
| Web settings page | ✅ reachable from your iPhone too |
| Update check | ✅ silent, daily, no auto-download — toggle in settings |
| Diagnostics & logs | ✅ "🩺 Diagnostics" menu |
| Cost / internet | **$0 / offline** (Wispr Flow: $15/mo + cloud) |

Every feature can be switched on/off individually — from the menu bar or the [web settings page](#settings).

## Requirements

- Apple Silicon Mac (M1/M2/M3/M4) — tested on an **M1 Pro**
- Optional, for AI polish: a local LLM via **LM Studio** *or* **Ollama** (e.g. a
  Gemma model) — LocalFlow auto-detects whichever is running

## Install

1. Grab the latest DMG from the **[releases page](https://github.com/theminhnguyen/localflow/releases/latest)**
   (`LocalFlow-x.y.z.dmg`) — built automatically on every tagged release.
2. Open the DMG, drag **LocalFlow** into **Applications**.
3. In *Applications*, launch it via **right-click → Open** (only needed the first
   time — the app is signed ad-hoc, not with a paid Apple certificate).
4. A **setup assistant** walks you through microphone access, the two required
   permissions (auto-restarting once they're granted), and downloads the Whisper
   model with a progress bar. That's it.

The app bundles Python and every dependency — nothing else to install. Re-run the
assistant anytime from *🩺 Diagnostics → "Restart setup"*.

**Build the DMG yourself:** `bash packaging/build_dmg.sh` → `dist/LocalFlow-x.y.z.dmg`.

### From source (for development)

```bash
cd ~/Downloads/localflow
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m localflow.main
```

### AI polish (optional)

A local LLM smooths out each dictation: false starts ("meet at 2 — actually 3")
get resolved, spoken lists become bullet points, grammar gets a light pass.
LocalFlow **auto-detects** one of two backends; without either, everything still
works (just rule-based cleanup).

**Option A — LM Studio** (GUI, easiest): open [LM Studio](https://lmstudio.ai),
load a chat model, *Developer → Local Server → Start* (port 1234).

**Option B — Ollama** (CLI):
```bash
brew install ollama
brew services start ollama
ollama pull gemma3:4b
```

Force a backend in `~/.localflow/config.json` (`"llm_backend"`: `"auto"` |
`"lmstudio"` | `"ollama"`); `"llm_model"` is a substring match (e.g. `"gemma"`).

### macOS permissions

The setup assistant handles this automatically. Manually, under *System Settings
→ Privacy & Security*, LocalFlow needs **Microphone**, **Accessibility** (to
paste text), and **Input Monitoring** (to catch the dictation key). Check status
via *🩺 Diagnostics → Check permissions*; restart LocalFlow after granting.

## Using it

- **Hold the right Option key (⌥)**, speak, **release** — text lands at your cursor.
- **Hands-free:** double-tap ⌥ → recording locks on (a chime confirms it), speak
  as long as you like, tap once to finish.
- Start the next dictation immediately, even while the previous one is still
  processing — everything lands in the right order.
- Menu bar status: 🎙 ready · 🔴 recording · ⏳ transcribing.
- **Transcribe audio file…** in the menu turns a voice memo/recording into a
  text file next to the original.

## Settings

Two ways to reach every toggle:

- **Menu bar** (🎙 → ⚙️ Settings) — quick, right there.
- **Web page** (🎙 → ⚙️ Settings → "Open settings in browser") — a cleaner view
  that also works **from your iPhone** (same link as the dictation app below).
  Changes apply instantly, no restart.

## iPhone setup

1. Start LocalFlow on your Mac.
2. Menu bar → *📱 Pair phone → Show QR code*.
3. Scan it with your iPhone camera → Safari opens `https://<mac-ip>:8790`.
4. Certificate warning: **"Show Details → visit this website"** (self-signed;
   required because Safari needs HTTPS for microphone access).
5. *Share → "Add to Home Screen"* to make it feel like a real app.

**Remote mic:** toggle the **"→ Mac"** chip — dictated text lands straight at
your Mac's cursor (can be disabled in settings).

**On the go:** with [Tailscale](https://tailscale.com) (free plan) set up on
both devices, a second QR code appears automatically in the pairing menu — your
phone can dictate from anywhere, as long as the Mac is running.

## Privacy

Everything runs on your Mac — Whisper and the optional LLM never leave it, no
cloud calls.

- **Dictated text is not written to the log by default** — only `[N chars]`.
  Enable for debugging via ⚙️ → "Log dictated text".
- **History** (recent dictations, for the menu and phone) lives only in
  `~/.localflow/history.json`. Clear it anytime, or set `"history_keep": 0` in
  `config.json` to disable it entirely.
- **The only network calls:** the one-time Whisper model download, and — if
  enabled — the update check against the GitHub Releases API (toggle in settings).
- A **pairing token** protects `/api/*` from anyone else on the same WLAN; reset
  it anytime via *📱 Pair phone → Reset pairing…*.

Full details (data locations, every config key) in the [German README](README.de.md#datenschutz).

## Tests

```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_e2e.py   # fast
.venv/bin/python -m pytest tests/test_e2e.py -q -s                # with the model
```

## How it works

```
Mac:    ⌥ ──► mic ──► Whisper (mlx) ──► rule cleanup ──► ✨ LLM ──► ⌘V at cursor
Phone:  tap ──► HTTPS upload ──► (Mac) Whisper ──► cleanup ──► back, or straight to Mac cursor
```

Recording and processing are decoupled (a queue keeps order even if you dictate
faster than it can transcribe), a watchdog rescues recordings if a key-release
event gets lost, and silent recordings are dropped before they reach Whisper
(which otherwise hallucinates text from silence).

## Contributing

See [CHANGELOG.md](CHANGELOG.md) for version history and
[docs/PLAN-PROFESSIONALISIERUNG.md](docs/PLAN-PROFESSIONALISIERUNG.md) for the
roadmap. PRs welcome — `pytest tests/ -q --ignore=tests/test_e2e.py` must pass.

## License

MIT — see [LICENSE](LICENSE).
