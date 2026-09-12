# VN Lookup — Steam Deck VN sentence mining, without leaving gaming mode

> ⚠️ **Work in progress.** This is a personal project, not a polished release —
> setup is manual, some flows are rough, and things may break or change
> without notice. Use at your own risk. I plan on overhauling the install process significantly, remove redundant settings, and improve the Anki card generator.

A [Decky Loader](https://decky.xyz/) plugin: hold a back button while reading a
visual novel, and the current text-box line is screenshot-captured, OCR'd
on-device, cleaned up, and turned into an Anki card — either directly via a
built-in dictionary (buffered locally, then exported as a `.apkg` you scan
onto your phone with AnkiMobile/AnkiDroid — no AnkiConnect needed), or via
Yomitan in Firefox.

Built on the shoulders of
[Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator) (capture,
hidraw trigger, and overlay code are ported from it — see
[Credits](#credits--data-sources)) and the research in
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

### 3. Anki

The built-in dictionary path needs **no Anki setup on the Deck at all** —
cards are buffered locally and exported as a single `.apkg` on demand,
served briefly over your LAN and rendered as a QR code you scan straight
into [AnkiMobile](https://apps.apple.com/app/ankimobile-flashcards/id373493387)
or [AnkiDroid](https://play.google.com/store/apps/details?id=com.ichi2.anki)
on your phone. Nothing needs to be running on the Deck at capture or export
time.

The rest of this section is only needed if you also want the **Yomitan
fallback** (Part 4), which creates cards through Yomitan's own Anki
integration and does need a desktop Anki with AnkiConnect running on the
Deck — skip to [Part 4](#4-firefox--yomitan-optional--only-for-the-fallback-mining-flow)
if you don't:

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

Skip this if you're fine using the plugin's built-in dictionary — it needs
none of this (see Part 3 above).

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
   note type's fields. This talks directly to AnkiConnect — the plugin has
   no part in it and doesn't attach a screenshot to these cards.
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
into tappable word chips → tap a chip for a definition → **➕ Anki** buffers
the card locally (nothing is sent anywhere yet). First time, run **Install
lookup runtime** and **Download dictionary** from the Lookup section of the
panel.

When you're ready to bring cards over to your phone, open the panel's
**Anki** section and tap **Export via QR** (first tap installs the small
export runtime, ~5 MB) — it packages everything buffered into one `.apkg`,
serves it briefly over your LAN, and shows a QR code. Scan it, tap "Open in
Anki" on your phone, and the cards import. The buffer isn't cleared
automatically, so you can keep adding to it across sessions — use **Clear
buffer** once you've confirmed the import.

**Yomitan fallback:** hold the capture button, switch to Firefox — the line
is on the texthooker page and Yomitan's search may already be open — hover
and create the card as usual. This talks straight to AnkiConnect (Part 3
above), independently of the plugin's own buffer/export flow.

---

## Known limitations

- VN-style single-speaker text boxes only; no dialogue-log/multi-speaker
  parsing.
- Yomitan's Firefox background page can be idle-killed after ~30s, silently
  stopping its clipboard monitor — the texthooker page doesn't have this
  problem, so prefer it if clipboard delivery seems flaky.
- Capture region and hold time may need tuning per game (sliders +
  "Capture now" in the panel).
- Exported cards carry the sentence and dictionary fields only — no game
  screenshot. Dropping AnkiConnect meant dropping the live enrichment step
  that used to attach it; may come back to the export flow later.

---

## Credits & data sources

**Code.** Screen capture, the hidraw back-button monitor, and the in-game
overlay's UI-composition hook are ported from
[Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator) by
Alexander Timoshuk, licensed GPL-3.0. Because of that, this whole project is
licensed **GPL-3.0-or-later** (see [LICENSE](LICENSE)) rather than a more
permissive license — anyone redistributing a modified build needs to keep it
open under the same terms. Capture-region tuning is informed by the research
at [rentry.co/deckmining](https://rentry.co/deckmining). Project scaffolding
comes from
[decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template).

**Dictionary data.** The plugin ships no dictionary — the built-in lookup
downloads and imports [Jitendex](https://jitendex.org/) (or any other
Yomitan-format dictionary you supply) at runtime, into your own local SQLite
database. Jitendex itself is built from, and credits:

- [JMdict/EDICT](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project)
  by the [Electronic Dictionary Research and Development Group](https://www.edrdg.org/)
  at Monash University — used under EDRDG's [licence terms](https://www.edrdg.org/edrdg/licence.html).
- [Tatoeba](https://tatoeba.org/) example sentences (CC BY 2.0 FR).
- [JmdictFurigana](https://github.com/Doublevil/JmdictFurigana) furigana data
  (CC BY-SA).
- Jitendex's own compiled data is CC BY-SA 4.0 —
  see [jitendex.org/pages/legal](https://jitendex.org/pages/legal.html).

The dictionary format (and the fallback lookup path) is
[Yomitan](https://github.com/yomidevs/yomitan)'s.

**Other runtime dependencies**, installed on-device rather than bundled:
[RapidOCR](https://github.com/RapidAI/RapidOCR) and
[ONNX Runtime](https://github.com/microsoft/onnxruntime) (Apache-2.0 / MIT)
for on-device OCR; [fugashi](https://github.com/polm/fugashi) +
[unidic-lite](https://github.com/polm/unidic-lite) for Japanese tokenization;
[genanki](https://github.com/kerrickstaley/genanki) (MIT) for building the
exported `.apkg`. The Yomitan fallback path (optional) additionally relies
on [AnkiConnect](https://github.com/FooSoft/anki-connect), installed as an
Anki add-on rather than by the plugin.

---

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
