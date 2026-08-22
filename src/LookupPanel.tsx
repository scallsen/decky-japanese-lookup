// Native lookup UI: the last captured line as focusable word chips;
// selecting a chip shows dictionary entries below and can create an Anki
// card directly. Runs entirely local — no Firefox/Yomitan involved.

import {
  ButtonItem,
  DialogButton,
  Focusable,
  PanelSection,
  PanelSectionRow,
} from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import {
  createAnkiCard,
  DictEntry,
  getLookupStatus,
  importDictionaries,
  installLookupRuntime,
  LookupStatus,
  lookupWord,
  Token,
  tokenizeLine,
} from "./api";

// POS classes that gamepad focus skips (still touch-tappable): particles,
// auxiliaries — you rarely look them up, and skipping them makes D-pad
// navigation step word-to-word instead of morpheme-to-morpheme.
const GRAMMAR_POS = new Set(["助詞", "助動詞"]);

const isContentWord = (t: Token) =>
  t.selectable && !GRAMMAR_POS.has(t.pos);

// below this, the OCR read is shaky enough to flag — not a hard science,
// just a heads-up that the capture area/game text might need a look
const LOW_CONFIDENCE_THRESHOLD = 0.6;

// Yomitan-style scan: candidate lookup keys from the tapped token outward,
// longest first. For each window, try the raw surface and the surface with
// the last token in dictionary form (気になっ… → 気になる). The backend
// returns entries for the first key that hits, so compounds win when the
// dictionary knows them.
const candidatesAt = (tokens: Token[], i: number): string[] => {
  const cands: string[] = [];
  const maxW = Math.min(5, tokens.length - i);
  for (let w = maxW; w >= 2; w--) {
    const slice = tokens.slice(i, i + w);
    const surface = slice.map((t) => t.surface).join("");
    const withDictForm =
      slice.slice(0, -1).map((t) => t.surface).join("") +
      slice[slice.length - 1].dict_form;
    cands.push(surface);
    if (withDictForm !== surface) cands.push(withDictForm);
  }
  const t = tokens[i];
  cands.push(t.dict_form, t.lemma.split("-")[0], t.surface, t.reading);
  return [...new Set(cands.filter(Boolean))];
};

export const LookupSection: FC<{
  sentence: string | null;
  confidence: number | null;
  ankiEnabled: boolean;
}> = ({ sentence, confidence, ankiEnabled }) => {
  const [status, setStatus] = useState<LookupStatus | null>(null);
  const [tokens, setTokens] = useState<Token[]>([]);
  const [sel, setSel] = useState<[number, number] | null>(null); // token index range
  const [focused, setFocused] = useState<number | null>(null);
  const [entries, setEntries] = useState<DictEntry[] | null>(null);
  const [message, setMessage] = useState("");
  const alive = useRef(true);
  const tokenizedFor = useRef<string | null>(null);
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const entriesRef = useRef<HTMLDivElement | null>(null);
  const wantFocusMove = useRef(false);
  const sectionRef = useRef<HTMLDivElement | null>(null);

  const refresh = async () => {
    try {
      const s = await getLookupStatus();
      if (alive.current) setStatus(s);
      return s;
    } catch {
      return null;
    }
  };

  useEffect(() => {
    alive.current = true;
    void refresh();
    const t = setInterval(async () => {
      const s = await refresh();
      // keep polling snappy only while something is installing/importing
      if (!s?.runtime.installing && !s?.dictionary.importing) return;
    }, 2000);
    return () => {
      alive.current = false;
      clearInterval(t);
      if (hoverTimer.current) clearTimeout(hoverTimer.current);
    };
  }, []);

  // tokenize whenever a new sentence arrives and the runtime is ready
  useEffect(() => {
    if (!sentence || !status?.runtime_installed) return;
    if (tokenizedFor.current === sentence) return;
    tokenizedFor.current = sentence;
    setSel(null);
    setEntries(null);
    void tokenizeLine(sentence).then((r) => {
      if (alive.current && r.ok && r.tokens) setTokens(r.tokens);
    });
  }, [sentence, status?.runtime_installed]);

  // scroll back to the top of the Lookup section (title included) once the
  // fresh sentence's words actually render — doing this off the capture
  // event itself (rather than here) raced the async tokenize call above,
  // scrolling before the new words (or the QAM) had actually rendered
  useEffect(() => {
    if (tokens.length > 0) {
      sectionRef.current?.scrollIntoView({ block: "start" });
    }
  }, [tokens]);

  // D-pad rests on a word for a beat → look it up without pressing A.
  // Debounced so scrolling across the sentence doesn't fire per word.
  const onWordFocus = (i: number) => {
    setFocused(i);
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    hoverTimer.current = setTimeout(() => void doLookup(i), 350);
  };

  const onWordBlur = (i: number) => {
    setFocused((cur) => (cur === i ? null : cur));
  };

  // A-press/tap moves focus into the definition once it renders (Steam's
  // gamepad focus follows DOM focus); hover-lookups must not steal focus.
  useEffect(() => {
    if (!wantFocusMove.current || !entries?.length) return;
    wantFocusMove.current = false;
    const t = setTimeout(() => {
      entriesRef.current
        ?.querySelector<HTMLElement>("[tabindex], button")
        ?.focus();
    }, 50);
    return () => clearTimeout(t);
  }, [entries]);

  const doLookup = async (i: number, moveFocus = false) => {
    if (hoverTimer.current) clearTimeout(hoverTimer.current);
    wantFocusMove.current = moveFocus;
    setSel([i, i]);
    setEntries(null);
    setMessage("");
    const t = tokens[i];
    const r = await lookupWord(candidatesAt(tokens, i));
    if (!alive.current) return;
    let all = r.entries ?? [];

    // highlight the tokens the match actually covered
    const matched = all[0]?.matched ?? t.surface;
    let acc = 0;
    let j = i;
    while (j < tokens.length && acc < matched.length) {
      acc += tokens[j].surface.length;
      j++;
    }
    setSel([i, Math.max(i, j - 1)]);

    // compound matched: also offer the tapped word's own entries below it
    if (matched.length > t.surface.length) {
      const base = await lookupWord([
        t.dict_form, t.lemma.split("-")[0], t.surface, t.reading,
      ]);
      if (!alive.current) return;
      const seen = new Set(all.map((e) => e.expression + "|" + e.reading));
      all = all.concat(
        (base.entries ?? []).filter(
          (e) => !seen.has(e.expression + "|" + e.reading)));
    }
    setEntries(all);
  };

  const addCard = async (e: DictEntry) => {
    setMessage("Buffering…");
    const r = await createAnkiCard(
      e.expression, e.reading, e.glosses, sentence ?? "");
    setMessage(r.ok ? `✓ Buffered (${e.expression}) — ${r.buffered} pending` : `✗ ${r.error}`);
  };

  // ---- setup states ------------------------------------------------------

  if (status && !status.runtime_installed) {
    return (
      <PanelSection title="Lookup">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={status.runtime.installing}
            onClick={() => void installLookupRuntime().then(refresh)}
          >
            {status.runtime.installing
              ? `Installing… (${status.runtime.step})`
              : "Install lookup runtime (~60 MB)"}
          </ButtonItem>
        </PanelSectionRow>
        {status.runtime.error ? (
          <PanelSectionRow>
            <div style={{ fontSize: 11, color: "#e74c3c" }}>
              {status.runtime.error}
            </div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    );
  }

  if (status && !status.dictionary.ready) {
    const d = status.dictionary;
    return (
      <PanelSection title="Lookup">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={d.importing}
            onClick={() => void importDictionaries(true).then(refresh)}
          >
            {d.importing
              ? `${d.step}… ${Math.round(d.progress * 100)}%`
              : "Download dictionary (Jitendex, ~70 MB)"}
          </ButtonItem>
        </PanelSectionRow>
        {d.pending_zips.length > 0 && !d.importing ? (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => void importDictionaries(false).then(refresh)}
            >
              Import {d.pending_zips.length} zip(s) from dicts folder
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
        {d.error ? (
          <PanelSectionRow>
            <div style={{ fontSize: 11, color: "#e74c3c" }}>{d.error}</div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>
    );
  }

  // ---- main lookup UI ----------------------------------------------------

  return (
    <div ref={sectionRef}>
      <PanelSection title="Lookup">
        {sentence === null ? (
          <PanelSectionRow>
            <div style={{ fontSize: 12, opacity: 0.7 }}>
              Capture a sentence first, then analyze here.
            </div>
          </PanelSectionRow>
        ) : sentence === "" ? (
          <PanelSectionRow>
            <div style={{ fontSize: 12, color: "#e0a04f" }}>
              No text found – check capture area, or image quality may be too
              low to scan
            </div>
          </PanelSectionRow>
        ) : (
          <>
            <PanelSectionRow>
              <Focusable
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "baseline",
                  fontSize: 19,
                  lineHeight: 1.7,
                  fontFamily: '"Noto Sans CJK JP", "Hiragino Sans", sans-serif',
                  padding: entries !== null ? "2px 0 8px" : "2px 0",
                  borderBottom: entries !== null
                    ? "1px solid rgba(255,255,255,0.1)"
                    : "none",
                }}
              >
                {tokens.map((t, i) => {
                  const inSel = !!sel && i >= sel[0] && i <= sel[1];
                  const isFocused = focused === i;
                  // DialogButton = native gamepad focus. The width/minWidth
                  // overrides beat its default width:100% class so words sit
                  // side by side and wrap like a sentence. The transparent
                  // background also kills Steam's own focus highlight, so we
                  // paint our own from onGamepadFocus state.
                  return isContentWord(t) ? (
                    <DialogButton
                      key={i}
                      style={{
                        width: "fit-content",
                        minWidth: 0,
                        margin: 0,
                        padding: "0 2px",
                        fontSize: 19,
                        lineHeight: 1.7,
                        background: isFocused
                          ? "rgba(255,255,255,0.9)"
                          : inSel
                          ? "rgba(26,159,255,0.35)"
                          : "transparent",
                        color: isFocused ? "#111" : "#e8e8e8",
                        borderRadius: 3,
                        borderBottom: isFocused
                          ? "2px solid transparent"
                          : "2px dotted rgba(255,255,255,0.3)",
                        boxShadow: "none",
                        transition: "background 0.1s, color 0.1s",
                      }}
                      onClick={() => void doLookup(i, true)}
                      onGamepadFocus={() => onWordFocus(i)}
                      onGamepadBlur={() => onWordBlur(i)}
                      onOKActionDescription="Look up"
                    >
                      {t.surface}
                    </DialogButton>
                  ) : (
                    <span
                      key={i}
                      style={{
                        opacity: t.selectable ? 0.75 : 0.55,
                        background: inSel ? "rgba(26,159,255,0.35)" : undefined,
                        borderRadius: 3,
                        padding: "0 1px",
                      }}
                      onClick={t.selectable ? () => void doLookup(i, true) : undefined}
                    >
                      {t.surface}
                    </span>
                  );
                })}
              </Focusable>
            </PanelSectionRow>

            {typeof confidence === "number" && confidence < LOW_CONFIDENCE_THRESHOLD && (
              <PanelSectionRow>
                <div style={{ fontSize: 12, color: "#e0a04f" }}>
                  Accuracy low – check capture area
                </div>
              </PanelSectionRow>
            )}

            {message ? (
              <PanelSectionRow>
                <div style={{ fontSize: 12, color: "#dcae3c" }}>{message}</div>
              </PanelSectionRow>
            ) : null}

            {entries !== null && entries.length === 0 && (
              <PanelSectionRow>
                <div style={{ fontSize: 12, color: "#e0a04f" }}>
                  No dictionary hits — the OCR may have misread a character
                  (the full line is also on the texthooker page in Firefox).
                </div>
              </PanelSectionRow>
            )}

            <div ref={entriesRef}>
            {(entries ?? []).map((e, i) => (
              <PanelSectionRow key={i}>
                <Focusable
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 4,
                    padding: "6px 2px",
                    borderTop: i > 0 ? "1px solid rgba(255,255,255,0.1)" : "none",
                  }}
                  tabIndex={0}
                  onActivate={ankiEnabled ? () => void addCard(e) : undefined}
                  onOKActionDescription={ankiEnabled ? "Buffer Anki card" : undefined}
                >
                  {/* the entry itself is the gamepad-focus/scroll-into-view
                      target (tabIndex here, not just on the +Anki button) so
                      landing on an entry and D-pad-down to the next one both
                      work even when Anki is disabled and no button renders */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 6,
                    }}
                  >
                    <div style={{ fontSize: 18, minWidth: 0 }}>
                      <b style={{ color: "#fff" }}>{e.expression}</b>
                      {e.reading && e.reading !== e.expression ? (
                        <span style={{ opacity: 0.8 }}>【{e.reading}】</span>
                      ) : null}
                      {e.pitch ? (
                        <span style={{ fontSize: 12, opacity: 0.7 }}>
                          {" "}[{e.pitch.join(",")}]
                        </span>
                      ) : null}
                      {e.frequency ? (
                        <span
                          style={{
                            fontSize: 11,
                            marginLeft: 6,
                            padding: "1px 5px",
                            borderRadius: 4,
                            background: "rgba(79,195,247,0.2)",
                            color: "#9fdcf9",
                          }}
                        >
                          {e.frequency}
                        </span>
                      ) : null}
                    </div>
                    {ankiEnabled && (
                      <DialogButton
                        style={{
                          width: "fit-content",
                          minWidth: 0,
                          padding: "4px 10px",
                          fontSize: 13,
                          flexShrink: 0,
                        }}
                        focusable={false}
                        onClick={() => void addCard(e)}
                      >
                        + Anki
                      </DialogButton>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: 13,
                      whiteSpace: "pre-wrap",
                      opacity: 0.92,
                      maxHeight: 240,
                      overflowY: "auto",
                    }}
                  >
                    {e.glosses}
                  </div>
                  {e.dicts.length > 0 && (
                    <div style={{ fontSize: 10, opacity: 0.45 }}>
                      {e.dicts.join(" · ")}
                    </div>
                  )}
                </Focusable>
              </PanelSectionRow>
            ))}
            </div>
          </>
        )}
      </PanelSection>
    </div>
  );
};
