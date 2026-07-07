# VN Lookup — Steam Deck VN sentence mining, without leaving gaming mode

A [Decky Loader](https://decky.xyz/) plugin: hold a back button while reading a
visual novel, and the current text-box line is screenshot-captured, OCR'd
on-device, cleaned up, and delivered to Yomitan for dictionary lookup and Anki
card creation — with the game screenshot and the full sentence on the card.

```
back button (L5)
   │  hidraw monitor (backend) + 100ms poller (frontend)
   ▼
PipeWire screen capture (gamescope video source, via GStreamer)
   ▼
crop to text-box region → RapidOCR (local venv) ─or─ Gemini Vision (cloud)
   ▼
rule-based cleanup (join lines, fix ー misreads, strip speaker name…)
   ▼
┌────────────────────────────┬───────────────────────────────┐
│ texthooker page             │ Steam CEF clipboard copy      │
│ http://localhost:8766/      │ (gamescope syncs it to        │
│ (WebSocket push, hover with │  Firefox → Yomitan clipboard  │
│  Yomitan in Firefox)        │  monitor auto-opens search)   │
└────────────────────────────┴───────────────────────────────┘
   ▼
you create the card in Yomitan → plugin watches AnkiConnect and
attaches the game screenshot (+ sentence) to the new note automatically
```

An in-game overlay pill shows each stage. On total OCR failure you get a red
error with the reason; on dubious results you get the raw OCR text so you can
tell *why* a lookup didn't work (bad OCR vs. bad region vs. nothing detected).

Built on the shoulders of
[Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator) (capture,
hidraw trigger, and overlay techniques are ported from it) and the research in
[rentry.co/deckmining](https://rentry.co/deckmining).

---

## Part 1 — One-time Steam Deck setup

You need **one trip to Desktop Mode** (Steam button → Power → Switch to
Desktop). Everything in this section happens once.

### 1.1 SSH access (in Desktop Mode, on the Deck)

Open **Konsole** and run:

```bash
passwd                      # set a password for the "deck" user if you haven't
sudo systemctl enable --now sshd
```

Optionally enable **Developer Mode** (Settings → System → "Enable Developer
Mode", then Settings → Developer → "CEF Remote Debugging") — not required for
deploys, but it lets you inspect the plugin frontend from your Mac at
`http://steamdeck.local:8081`.

### 1.2 SSH key from your Mac

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519          # if you don't have one
ssh-copy-id deck@steamdeck.local                    # or the Deck's IP
ssh deck@steamdeck.local                            # verify passwordless login
```

If `steamdeck.local` doesn't resolve, find the IP in Settings → Internet on
the Deck and use that everywhere instead.

### 1.3 Decky Loader (can be done from your Mac over SSH)

```bash
ssh -t deck@steamdeck.local \
  'curl -L https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/install_release.sh | sh'
```

### 1.4 Firefox + Anki flatpaks (still in the same Desktop Mode session)

```bash
flatpak install -y flathub org.mozilla.firefox net.ankiweb.Anki
```

In the **desktop Steam client**, add both as non-Steam games
(Games → Add a Non-Steam Game → Browse → `/usr/bin/flatpak`), then set their
properties (right-click → Properties):

| Entry   | Target             | Launch options |
|---------|--------------------|----------------|
| Firefox | `/usr/bin/flatpak` | `run --branch=stable --arch=x86_64 --command=firefox org.mozilla.firefox` |
| Anki    | `/usr/bin/flatpak` | `run --env=LC_ALL=C.UTF-8 --branch=stable --arch=x86_64 --command=anki --file-forwarding net.ankiweb.Anki @@ @@` |

(The `LC_ALL` fix is required — flatpak Anki crashes on the Deck without it.
Rename the entries to "Firefox" and "Anki" so the gaming-mode switcher is
readable.)

### 1.5 Yomitan + dictionaries (in Firefox)

1. Install [Yomitan](https://addons.mozilla.org/firefox/addon/yomitan/).
2. Import dictionaries (JMdict, etc.) in Yomitan settings.
3. Yomitan Settings → **Clipboard**: enable **both**
   *background clipboard text monitoring* and
   *search page clipboard text monitoring*.
4. Yomitan Settings → **Anki**: enable, URL `http://127.0.0.1:8765`, pick your
   note type and map fields (e.g. `{expression}`, `{reading}`, `{glossary}`,
   `{sentence}`). Leave the Picture field **unmapped** — this plugin fills it
   with the actual game screenshot after card creation ({screenshot} would
   only capture the browser tab).
5. Set Firefox's homepage to `http://localhost:8766/` — the plugin's built-in
   texthooker page.

### 1.6 AnkiConnect (in Anki)

Tools → Add-ons → Get Add-ons → code `2055492159`, restart Anki. If Yomitan
gets a CORS error later, add `"null"` and your
`moz-extension://<UUID>` origin (UUID from `about:debugging#/runtime/this-firefox`)
to the add-on's `webCorsOriginList` config.

> **Note**: clipboard delivery between gamescope windows requires
> **SteamOS ≥ 3.7.14** (gamescope's cross-XWayland clipboard sync fix). The
> texthooker page works on any version.

---

## Part 2 — Build & deploy from your Mac

Deploys go straight from this working copy to the Deck over SSH — no
GitHub round-trip involved. From the repo directory:

```bash
pnpm i                                     # once; or: npm i -g pnpm first
cp .vscode/defsettings.json .vscode/settings.json
$EDITOR .vscode/settings.json              # set deckip/deckpass/key path
./deploy.sh                                # build → rsync → restart Decky
```

`deploy.sh` builds the frontend with rollup and rsyncs
`dist/ main.py plugin.json package.json py_modules/` straight into
`~/homebrew/plugins/vn-lookup/` on the Deck, then restarts `plugin_loader`.
No Docker, no zip step.

VS Code tasks (⇧⌘B / Run Task) wrap the same loop: **build**, **deploy**,
**deploy-only** (skip rebuild), **decky-log** (tail the backend log),
**restartdecky**.

Iteration loop: edit → `./deploy.sh` → plugin reloads on the Deck in ~10s.
Backend logs land in `/home/deck/homebrew/logs/vn-lookup/`; frontend console
is visible via CEF debugging (`steamdeck.local:8081`) if you enabled it.

### First run, on the Deck (gaming mode)

Open the Quick Access menu (…) → VN Lookup:

1. **Install OCR runtime** (~400 MB: creates a venv in
   `~/homebrew/data/vn-lookup/venv` with RapidOCR + ONNX Runtime — survives
   SteamOS updates, never touches the OS partition).
2. **Download OCR models** (~22 MB: PP-OCRv5 detection + recognition, which
   handles Japanese natively).
3. Check the Status section: Controller *hooked*, PipeWire *ok*.
4. Press **Capture now (test)** with a game running.

---

## Part 3 — The mining workflow

1. Launch your VN.
2. Steam button → Library → launch **Firefox** (texthooker page loads) and
   **Anki**. Both keep running in the background — gamescope does not pause
   unfocused apps.
3. Steam button → back to the VN.
4. On a line you want to mine: **hold L5** (configurable) → overlay pill shows
   capture → OCR → the cleaned line.
5. Steam button → Firefox. The line is on the texthooker page (and, if
   clipboard delivery worked, Yomitan's search page has already opened it).
   Hover-lookup with Yomitan, click ➕ to create the card.
6. Within a few seconds the plugin notices the new note via AnkiConnect and
   attaches the **game screenshot** (full frame or text-box crop — your
   choice) and the full sentence if Yomitan left that field empty. The
   overlay flashes "Anki card enriched".
7. Steam button → back to the VN. Next line.

If Anki wasn't running at the time, the QAM panel's
**"Attach last capture to newest card"** button does the same thing manually.

---

## Settings reference (QAM panel)

| Setting | Default | Notes |
|---|---|---|
| Capture button | `L5` | L4/R4/L5/R5 — read via raw hidraw, works regardless of Steam Input bindings |
| Hold time | 250 ms | 0 = instant fire |
| OCR backend | Local (RapidOCR) | or Gemini Vision (needs API key; the text-box crop is sent to Google) |
| Region | bottom 62–98 %, 3 % margins | fractions of the screen; tune per game with the sliders + "Capture now" |
| Strip speaker name | on | removes `【名前】` / `名前「` prefixes |
| Card image | Full screenshot | or the text-box crop |
| Picture / Sentence field | `Picture` / `Sentence` | must match your Anki note type exactly |

## Failure modes you'll actually see

| Overlay message | Meaning |
|---|---|
| `Capture failed: PipeWire video source not found` | No game running / gamescope source vanished (happens right after mode switches) |
| `Local OCR runtime not installed…` | Run the two setup buttons in the panel |
| `No text detected in the capture region` | Region misaligned or textbox empty — check with "Capture now" and adjust sliders |
| `Text doesn't look Japanese…` + text shown | OCR grabbed UI/garbage — raw text is displayed so you can tell what it saw |
| Yellow `raw OCR:` line under an error | Partial result — what the engine actually read before cleanup rejected it |

## Repo map

```
main.py                      # Decky backend: pipeline, callables, Anki watcher
py_modules/vnlookup/
  hid_monitor.py             # raw hidraw button monitor (ported from Decky-Translator)
  capture.py                 # PipeWire/GStreamer capture in gamescope
  deps.py                    # on-device venv bootstrap (RapidOCR + ONNX)
  models.py                  # PP-OCRv5 model downloader (Japanese subset)
  ocr.py / ocr_worker.py     # backend↔venv OCR subprocess boundary
  cleanup.py                 # rule-based Japanese OCR cleanup
  deliver.py                 # texthooker web page + WebSocket server (aiohttp)
  anki.py                    # AnkiConnect client (screenshot enrichment)
  settings.py                # JSON settings persistence
src/
  index.tsx                  # plugin entry: trigger watcher, events, overlay mount
  input.ts                   # back-button poller (hold-to-fire)
  Overlay.tsx                # in-game status overlay (useUIComposition)
  Panel.tsx                  # Quick Access settings panel
  clipboard.ts               # CEF clipboard copy (gamescope syncs it out)
deploy.sh                    # build + rsync + restart loop (no Docker)
refs/                        # cloned reference repos (gitignored)
```

## Known constraints

- Yomitan's Firefox background page can be idle-killed after ~30 s, silently
  stopping its clipboard monitor ([yomitan#777]). The texthooker page is the
  reliable path — it doesn't depend on Yomitan's background page at all.
- `wl-copy` does not work under gamescope (no data-control protocol); don't
  bother installing clipboard tools on the Deck. The plugin copies from
  Steam's own CEF instead.
- VN-style single-speaker text boxes only; no dialogue-log/multi-speaker
  parsing.

[yomitan#777]: https://github.com/yomidevs/yomitan/issues/777
