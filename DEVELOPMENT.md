# Development

This is for building the plugin from source, deploying it to a Deck over SSH,
and contributing changes. If you just want to use the plugin, follow the
[README](README.md)'s [Install](README.md#install) section instead — it uses
a prebuilt zip and needs no computer, Node, pnpm, or SSH.

---

## What you need

- A **Steam Deck** on Wi-Fi.
- A **computer running macOS or Linux** on the same network, to build the
  plugin and copy it to the Deck. (Windows should work through WSL, but is
  untested.)

---

## Building from source

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
git clone https://github.com/scallsen/decky-japanese-lookup.git
cd decky-japanese-lookup
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

Continue with the README's [First launch on the Deck](README.md#first-launch-on-the-deck).

---

## Updating a source install

On your computer, from the `decky-japanese-lookup` folder:

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

**Japanese Lookup doesn't show up in Decky after deploying**
Restart the Deck, then check again. If it's still missing, rerun
`./deploy.sh` and look for errors in its output.

For everything else (capture, OCR, lookup, Anki export), see the README's own
[Troubleshooting](README.md#troubleshooting) section.

---

## Checks to run before opening a pull request

```bash
pnpm lint && pnpm typecheck && pnpm build   # frontend: ESLint, tsc, rollup
pip install ruff pytest
ruff check . && pytest -q                   # backend: lint + unit tests
```
