# TODO / handoff notes

## Anki card styling — follow-up to the buffer/QR export feature (not yet implemented)

**Status:** the buffer + QR `.apkg` export feature (PR #4, branch
`worktree-anki-buffer-qr-export`) is implemented, deployed, and confirmed
working on-device. This note tracks an agreed-but-unimplemented follow-up
from that same work: card layout/styling.

### The problem

`py_modules/vnlookup/anki_export_worker.py` builds `genanki.Model(...)`
without passing a `css` string, so genanki's hardcoded default is used:

```css
.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}
```

No CJK font coverage, and 20px reads small on a phone. `.apkg` files do
carry full layout (HTML templates + CSS), not just field content, so this
is fixable.

### The subtlety that matters (already researched, confirmed from source — don't re-derive)

Because every export reuses the **same deterministic `model_id`** (a hash
of the configured note-type name, via `stable_id()` in
`py_modules/vnlookup/anki_export.py`) so cards merge instead of
duplicating, naively adding a `css` string is not enough on its own —
there's a real risk that any styling the user later customizes *by hand*
in Anki's card template editor gets silently overwritten by a future
export. Confirmed via Anki's own import source
(`rslib/src/import_export/package/apkg/import/notes.rs` in
github.com/ankitects/anki):

- On a note-type-ID collision, Anki's default policy (`IfNewer`) compares
  modification timestamps — whichever side (local vs. incoming) is newer
  wins, and the winning templates/CSS get written collection-wide for
  every note of that type, not just the imported ones.
- `genanki`'s `Package.write_to_file()` defaults its embedded `mod`
  timestamp to `time.time()` (confirmed in `genanki/package.py` /
  `genanki/model.py`) — i.e. "now," on every single export. Since real
  time only moves forward, every future export will always look newer
  than anything the user edited locally in between, and will clobber it.

### The agreed fix (two changes, both in `anki_export_worker.py`)

1. **Add a sensible default `css`** to the `genanki.Model(...)` call —
   larger font size (24–28px, `em`-based so Anki's own font-size setting
   still scales it), a CJK-aware font stack (e.g. `"Hiragino Sans",
   "Noto Sans JP", "Yu Gothic", sans-serif` — mirror the stack already
   used in `src/LookupPanel.tsx`), generous `line-height` (1.4–1.6).

2. **Freeze the export timestamp** — pass a fixed constant (not
   `time.time()`) as the `timestamp` argument to
   `genanki.Package(deck).write_to_file(out_path, timestamp=FROZEN_TS)`.
   Effect: the plugin's embedded notetype always looks *older* than any
   local edit the user makes afterward (which is stamped with the real
   current time by Anki itself), so `IfNewer` always keeps the user's
   customization instead of overwriting it. First-ever import still gets
   the plugin's default CSS from step 1; nothing changes if the user never
   touches it manually.

   Tradeoff to note in code/comments: this also means any *structural*
   note-type change we ship later (e.g. a new field) won't propagate to a
   collection where the user has customized the note type — that would
   need a fresh `model_id` (e.g. via a note-type rename in settings) to
   intentionally take effect. Acceptable for a personal-use plugin.

### Not yet done
- [ ] Add `css` to the `genanki.Model(...)` call
- [ ] Add frozen `timestamp` to `Package.write_to_file(...)`
- [ ] Maybe surface a short note in the Panel.tsx Anki section's helper
      text confirming manual styling edits in Anki are safe/persistent
