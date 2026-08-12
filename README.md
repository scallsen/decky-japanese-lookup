# VN Lookup — Steam Deck VN sentence mining, without leaving gaming mode

> ⚠️ **Work in progress.** This is a personal project, not a polished release —
> setup is manual, some flows are rough, and things may break or change
> without notice. Use at your own risk. I plan on overhauling the install process significantly, remove redundant settings, and improve the Anki card generator.

A [Decky Loader](https://decky.xyz/) plugin: hold a back button while reading a
visual novel, and the current text-box line is screenshot-captured, OCR'd
on-device, cleaned up, and turned into an Anki card — either directly via a
built-in dictionary, or via Yomitan in Firefox.

Built on the shoulders of
[Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator) (capture,
hidraw trigger, and overlay techniques are ported from it) and the research in
[rentry.co/deckmining](https://rentry.co/deckmining).

---

## Setup

You need **one trip to Desktop Mode** (Steam button → Power → Switch to
Desktop) to do all of this.

### 1. SSH access (Desktop Mode, on the Deck)

```bash
passwd                      # set a password for the "deck" user if you haven't
sudo systemctl enable --now sshd
```

From your Mac:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519          # if you don't have one
ssh-copy-id deck@steamdeck.local                    # or the Deck's IP
ssh deck@steamdeck.local                            # verify passwordless login
```

If `steamdeck.local` doesn't resolve, find the IP in Settings → Internet on
the Deck and use that everywhere instead.

### 2. Decky Loader (from your Mac, over SSH)

```bash
ssh -t deck@steamdeck.local \
  'curl -L https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/install_release.sh | sh'
```

### 3. Anki (required — both lookup paths create cards via AnkiConnect)

Still in Desktop Mode:

```bash
flatpak install -y flathub net.ankiweb.Anki
```

In the desktop Steam client, add it as a non-Steam game
(Games → Add a Non-Steam Game → Browse → `/usr/bin/flatpak`), right-click →
Properties, and set:

- Target: `/usr/bin/flatpak`
- Launch options: `run --env=LC_ALL=C.UTF-8 --branch=stable --arch=x86_64 --command=anki --file-forwarding net.ankiweb.Anki @@ @@`

(The `LC_ALL` fix is required — flatpak Anki crashes on the Deck without it.)

In Anki: Tools → Add-ons → Get Add-ons → code `2055492159` (AnkiConnect),
restart Anki.

### 4. Firefox + Yomitan (optional — only for the fallback mining flow)

Skip this if you're fine using the plugin's built-in dictionary (Part 3
below).

```bash
flatpak install -y flathub org.mozilla.firefox
```

Add it as a non-Steam game the same way as Anki, with launch options
`run --branch=stable --arch=x86_64 --command=firefox org.mozilla.firefox`.

Then in Firefox:

1. Install [Yomitan](https://addons.mozilla.org/firefox/addon/yomitan/) and
   import dictionaries.
2. Yomitan Settings → **Clipboard**: enable both *background clipboard text
   monitoring* and *search page clipboard text monitoring*.
3. Yomitan Settings → **Anki**: enable, URL `http://127.0.0.1:8765`, map your
   note type's fields. Leave the Picture field **unmapped** — the plugin
   fills it with the actual game screenshot after card creation.
4. Set Firefox's homepage to `http://localhost:8766/` (the plugin's built-in
   texthooker page).

> Clipboard delivery between gamescope windows needs **SteamOS ≥ 3.7.14**.
> `wl-copy` does not work under gamescope — the plugin copies via Steam's own
> CEF instance instead, don't bother installing clipboard tools.

---

## Build & deploy from your Mac

```bash
pnpm i                                     # once; or: npm i -g pnpm first
cp .vscode/defsettings.json .vscode/settings.json
$EDITOR .vscode/settings.json              # set deckip/deckpass/key path
./deploy.sh                                # build → rsync → restart Decky
```

`deploy.sh` builds the frontend and rsyncs the plugin straight into
`~/homebrew/plugins/vn-lookup/` on the Deck, then restarts `plugin_loader`.
No Docker, no zip step. Backend logs land in
`/home/deck/homebrew/logs/vn-lookup/`.

### First run, on the Deck (gaming mode)

Open the Quick Access menu (…) → VN Lookup:

1. **Install OCR runtime** (creates a venv in
   `~/homebrew/data/vn-lookup/venv` with RapidOCR + ONNX Runtime).
2. **Download OCR models** (PP-OCRv5, handles Japanese natively).
3. Check the Status section: Controller *hooked*, PipeWire *ok*.
4. Press **Capture now (test)** with a game running.

---

## Using it

**Built-in dictionary (no Firefox needed):** hold the capture button (**L5**
by default) over a text box → the line appears in the VN Lookup panel split
into tappable word chips → tap a chip for a definition → **➕ Create Anki
card** makes the card directly, with the sentence and game screenshot
attached automatically. First time, run **Install lookup runtime** and
**Download dictionary** from the Lookup section of the panel.

**Yomitan fallback:** hold the capture button, switch to Firefox — the line
is on the texthooker page and Yomitan's search may already be open — hover
and create the card as usual. The plugin watches AnkiConnect and attaches
the game screenshot to the new note within a few seconds. If Anki wasn't
running at capture time, use **"Attach last capture to newest card"** in the
panel to do it manually.

---

## Known limitations

- VN-style single-speaker text boxes only; no dialogue-log/multi-speaker
  parsing.
- Yomitan's Firefox background page can be idle-killed after ~30s, silently
  stopping its clipboard monitor — the texthooker page doesn't have this
  problem, so prefer it if clipboard delivery seems flaky.
- Capture region and hold time may need tuning per game (sliders +
  "Capture now" in the panel).
