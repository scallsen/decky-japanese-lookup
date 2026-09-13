# Japanese Lookup — read Japanese games on the Steam Deck, and mine words into Anki

> ⚠️ **Work in progress.** This is a personal project, not a polished release.
> There's no one-click install yet, some flows are rough, and things may
> change without notice. Use at your own risk.

A [Decky Loader](https://decky.xyz/) plugin for reading Japanese visual novels
(or any game with text boxes) without leaving gaming mode:

1. **Press a back button** (L5 by default) while a line of Japanese is on screen.
2. The plugin screenshots the text box, **reads the text on-device** (OCR — no
   internet needed), and opens the side menu with the line split into words.
3. **Move over a word** to see its dictionary definition.
4. Optionally **add the word to your Anki queue**, then later **scan a QR code**
   with your phone to import all queued cards into AnkiMobile or AnkiDroid.

Everything runs locally on the Deck. No Anki, browser, or account is needed
on the Deck itself.

---

## Contents

- [What you need](#what-you-need)
- [Install](#install) — one-time, about 20–30 minutes
- [First launch on the Deck](#first-launch-on-the-deck)
- [Everyday use](#everyday-use)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)
- [Optional: Yomitan in Firefox](#optional-yomitan-in-firefox)
- [Known limitations](#known-limitations)
- [Credits & data sources](#credits--data-sources)

---

## What you need

- A **Steam Deck** on Wi-Fi.
- A **computer running macOS or Linux** on the same network, to build the plugin
  and copy it to the Deck. (Windows should work through WSL, but is untested.)
- About **600 MB free** on the Deck for the OCR engine and dictionary.
- *(Only for Anki)* **AnkiMobile** (iOS) or **AnkiDroid** (Android) on a phone
  on the same Wi-Fi.

There's no prebuilt download yet — you build the plugin from this repository
and a script copies it to your Deck over the network. The steps below walk
you through it.

---

## Install

### Step 1 — Prepare the Deck (Desktop Mode)

This is the only time you need Desktop Mode. On the Deck, press the
**Steam button → Power → Switch to Desktop**, then open **Konsole** (from the
app launcher, under *System*).

1. **Set a password** for the `deck` user, if you've never done so. You'll
   need it again in Step 4.

   ```bash
   passwd
   ```

2. **Turn on SSH**, so your computer can copy files to the Deck:

   ```bash
   sudo systemctl enable --now sshd
   ```

3. **Install Decky Loader.** Open a browser on the Deck, go to
   [decky.xyz](https://decky.xyz/), download the installer, and run it
   (choose the *release* version). Or paste this into Konsole:

   ```bash
   curl -L https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/install_release.sh | sh
   ```

4. **Note the Deck's address.** It's usually `steamdeck.local`. If that doesn't
   work later on, use its IP address instead: *Settings → Internet →* select
   your Wi-Fi network, and look for the IP address (e.g. `192.168.1.42`).

You can now switch back to gaming mode (the *Return to Gaming Mode* icon on
the desktop).

### Step 2 — Connect your computer to the Deck

On your computer, open a terminal.

1. **Create an SSH key** (skip if `~/.ssh/id_ed25519` already exists; just
   press Enter at every prompt):

   ```bash
   ssh-keygen -t ed25519
   ```

2. **Copy it to the Deck.** It asks for the `deck` password from Step 1:

   ```bash
   ssh-copy-id deck@steamdeck.local
   ```

3. **Check it works.** This should log you in *without* asking for a password.
   Type `exit` to leave again.

   ```bash
   ssh deck@steamdeck.local
   ```

Replace `steamdeck.local` with the Deck's IP address everywhere if it doesn't
connect.

### Step 3 — Get the code and build tools

You need [Node.js](https://nodejs.org/) 22 or newer, and `pnpm`:

```bash
npm install -g pnpm
```

Then download this repository and install its dependencies:

```bash
git clone https://github.com/scallsen/steam-deck-vn-lookup.git
cd steam-deck-vn-lookup
pnpm install
```

### Step 4 — Tell the deploy script about your Deck

Create your local settings file from the template:

```bash
cp .vscode/defsettings.json .vscode/settings.json
```

Open `.vscode/settings.json` in any text editor and fill in:

| Setting    | What to put there                                                     |
| ---------- | --------------------------------------------------------------------- |
| `deckip`   | `steamdeck.local`, or the Deck's IP address                           |
| `deckpass` | The `deck` password from Step 1 (needed to install the plugin as root) |
| `deckkey`  | Leave as is, unless your SSH key isn't `~/.ssh/id_ed25519`             |

Leave the other values alone. This file is ignored by git, so your password
stays on your computer.

### Step 5 — Install the plugin on the Deck

```bash
./deploy.sh
```

This builds the plugin, copies it to the Deck, and restarts Decky. It should
end with `==> Done.` Run the same command again any time you want to reinstall.

---

## First launch on the Deck

Back in gaming mode, press the **`…` (Quick Access) button**, open the
**Decky** tab (the plug icon), and select **Japanese Lookup**.

The first time, the panel shows a few one-time download buttons. Make sure
the Deck is on Wi-Fi, then press each one and wait for it to finish before
moving on:

| Section | Button                                      | Size     |
| ------- | ------------------------------------------- | -------- |
| Lookup  | **Install lookup runtime**                  | ~60 MB   |
| Lookup  | **Download dictionary (Jitendex)**          | ~70 MB   |
| Setup   | **1. Install OCR runtime**                  | ~400 MB  |
| Setup   | **2. Download OCR models**                  | ~22 MB   |

The OCR runtime takes a few minutes. The buttons disappear once everything is
installed. If one fails, a red error appears underneath — press it again to
retry.

That's it — you're ready to go.

---

## Everyday use

### 1. Capture a line

Start your game. When a line of Japanese text is on screen, **press L5**.

A brief outline flashes over the area being read, and the Quick Access menu
opens on Japanese Lookup with the line shown as words.

> Captures only work while a game is running, so the plugin never tries to
> read the Steam menus.

### 2. Look up words

- **With the D-pad:** move over a word and pause — the definition appears
  below. Press **A** to jump into the definitions and scroll through them.
- **With the touchscreen:** tap a word.

Grammar words (particles etc.) are skipped by the D-pad but can still be
tapped. Close the menu with **B** or `…` and keep playing.

### 3. Save words for Anki *(optional)*

1. Scroll down to the **Anki** section and turn on **Enable Anki integration**.
   Optionally change the **Deck name** (default: *Steam Deck Vocabulary*).
2. When looking up a word, press **A** on a definition (or tap **+ Anki**).
   You'll see *✓ Added … to Anki queue*.

Each card has the word on the front, and the reading, meaning, word type, the
full sentence, and the game's name on the back.

Your queue is kept on the Deck until you export it, so you can collect words
over several play sessions. Press the **eye button** next to the card count to
preview the cards and remove any you don't want.

### 4. Send your cards to your phone

1. Make sure your phone is on the **same Wi-Fi** as the Deck.
2. In the **Anki** section, press **Export via QR code**. (The very first time,
   this button says **Install Anki export runtime** — press it, wait, then
   press it again.)
3. **Scan the QR code** with your phone's camera and open the link.
4. When the download finishes, choose **Open in Anki** (AnkiMobile /
   AnkiDroid). The cards are imported into your deck.
5. Once you've checked the cards arrived, press **Clear Anki queue** so they
   aren't exported twice.

The QR link only works for about 5 minutes. If it has expired, just export
again.

### Adjusting the capture area

By default, **L5** reads the bottom third of the screen, where most visual
novels put their text box. If a game puts its text elsewhere, or the plugin
picks up names, buttons, or other clutter:

1. **With the game running and its text box on screen**, open Japanese Lookup
   and press **Change area** in the **Capture area** section. The menu closes
   and a screenshot of the game appears with a blue box on top.
2. Drag the box over the text box (or use the D-pad to move it, **L1/R1** to
   change its width and **L2/R2** its height). **X** tries to find the text
   automatically.
3. Press **A** to save.

Changes are saved **for the game that's currently running**; other games keep
using the default area.

You can also change which back button triggers the capture (L4, R4, L5, or R5)
using the drop-down next to *Change area*, and press **Add capture area** to
give a second button its own area (e.g. one for the text box, one for the whole
screen).

To reset every game back to the default area, use **Advanced settings →
Delete all capture areas**.

---

## Updating

On your computer, from the `steam-deck-vn-lookup` folder:

```bash
git pull
pnpm install
./deploy.sh
```

Your settings, downloaded dictionary, and Anki queue are kept.

---

## Troubleshooting

**`ssh` / `./deploy.sh` can't reach `steamdeck.local`**
Use the Deck's IP address instead (Settings → Internet → your network), both
in the commands and in `.vscode/settings.json`. Make sure the Deck is awake
and on the same network.

**`./deploy.sh` asks for a password or says "Permission denied"**
Your SSH key isn't set up — redo [Step 2](#step-2--connect-your-computer-to-the-deck).
If it fails at the *Installing as root* step, check `deckpass` in
`.vscode/settings.json` matches the Deck's `deck` password.

**Japanese Lookup doesn't show up in Decky**
Restart the Deck, then check again. If it's still missing, rerun
`./deploy.sh` and look for errors in its output.

**Pressing L5 does nothing**
- Make sure a game is running (it doesn't work from the Steam menus).
- Check the capture area's drop-down is set to **L5** and not *None*.
- Open **Advanced settings → Show debug info**. *Controller* should say
  **hooked** and *PipeWire* should say **ok**. If not, restart the Deck.

**"No text found" or "Accuracy low – check capture area"**
The box probably doesn't sit exactly over the text. See
[Adjusting the capture area](#adjusting-the-capture-area). Very small or
stylised fonts can also read poorly.

**A word shows "No dictionary hits"**
The OCR most likely misread a character. Try capturing the line again, or
select the word next to it.

**The QR code won't open on my phone**
Your phone must be on the same Wi-Fi as the Deck (not mobile data or a guest
network). The link expires after about 5 minutes — press *Export via QR code*
again for a new one.

**Something else broke**
Logs are on the Deck in `~/homebrew/logs/vn-lookup/` (one file per start).
To see the end of the newest one from your computer:

```bash
ssh deck@steamdeck.local 'cd ~/homebrew/logs/vn-lookup && tail -n 100 "$(ls -t | head -1)"'
```

Please include it if you open an issue.

---

## Optional: Yomitan in Firefox

If you prefer [Yomitan](https://github.com/yomidevs/yomitan) (for example to
use your own dictionaries or send cards straight to a desktop Anki), the
plugin also shows every captured line on a local page at
`http://localhost:8766/` and copies it to the clipboard. **You don't need any
of this for the built-in lookup.**

Requires **SteamOS 3.7.14 or newer** for the clipboard to reach Firefox.

1. In Desktop Mode, install Firefox (`flatpak install -y flathub org.mozilla.firefox`)
   and add it to Steam as a non-Steam game, with launch options
   `run --branch=stable --arch=x86_64 --command=firefox org.mozilla.firefox`.
2. In Firefox, install [Yomitan](https://addons.mozilla.org/firefox/addon/yomitan/)
   and import dictionaries.
3. In Yomitan's settings, under **Clipboard**, turn on both clipboard monitoring
   options.
4. Set Firefox's homepage to `http://localhost:8766/`.
5. *(For Anki cards via Yomitan)* Install desktop Anki
   (`flatpak install -y flathub net.ankiweb.Anki`), add it as a non-Steam game
   with launch options
   `run --env=LC_ALL=C.UTF-8 --branch=stable --arch=x86_64 --command=anki --file-forwarding net.ankiweb.Anki @@ @@`
   (the `LC_ALL` part is required, or Anki crashes), install the
   [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on
   (code `2055492159`), and point Yomitan's **Anki** settings at
   `http://127.0.0.1:8765`.

Then: press L5 in-game, switch to Firefox, and hover the line to look it up.

---

## Known limitations

- Made for single text boxes, as in visual novels; no support for dialogue
  logs or several speakers on screen at once.
- The capture area may need adjusting per game.
- Exported Anki cards don't include a screenshot of the game (yet).
- Yomitan's clipboard monitor in Firefox can stop after ~30 seconds idle; the
  `localhost:8766` page doesn't have this problem.

---

## Credits & data sources

**Code.** Screen capture, the back-button monitor, and the in-game overlay are
ported from [Decky-Translator](https://github.com/cat-in-a-box/Decky-Translator)
by Alexander Timoshuk, licensed GPL-3.0. Because of that, this whole project is
licensed **GPL-3.0-or-later** (see [LICENSE](LICENSE)) — anyone redistributing
a modified build needs to keep it open under the same terms. Capture-area
tuning is informed by the research at
[rentry.co/deckmining](https://rentry.co/deckmining). Project scaffolding comes
from [decky-plugin-template](https://github.com/SteamDeckHomebrew/decky-plugin-template).

**Dictionary data.** The plugin ships no dictionary — the built-in lookup
downloads [Jitendex](https://jitendex.org/) (or any other Yomitan-format
dictionary you supply) at runtime, into a local database on your Deck.
Jitendex itself is built from, and credits:

- [JMdict/EDICT](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project)
  by the [Electronic Dictionary Research and Development Group](https://www.edrdg.org/)
  at Monash University — used under EDRDG's [licence terms](https://www.edrdg.org/edrdg/licence.html).
- [Tatoeba](https://tatoeba.org/) example sentences (CC BY 2.0 FR).
- [JmdictFurigana](https://github.com/Doublevil/JmdictFurigana) furigana data
  (CC BY-SA).
- Jitendex's own compiled data is CC BY-SA 4.0 —
  see [jitendex.org/pages/legal](https://jitendex.org/pages/legal.html).

The dictionary format is [Yomitan](https://github.com/yomidevs/yomitan)'s.

**Other runtime dependencies**, downloaded on the Deck rather than bundled:
[RapidOCR](https://github.com/RapidAI/RapidOCR) and
[ONNX Runtime](https://github.com/microsoft/onnxruntime) (Apache-2.0 / MIT)
for OCR; [fugashi](https://github.com/polm/fugashi) +
[unidic-lite](https://github.com/polm/unidic-lite) for splitting sentences
into words; [genanki](https://github.com/kerrickstaley/genanki) (MIT) for
building the exported Anki deck. The optional Yomitan setup additionally uses
[AnkiConnect](https://github.com/FooSoft/anki-connect), installed as an Anki
add-on rather than by the plugin.

---

## License

GPL-3.0-or-later — see [LICENSE](LICENSE).
