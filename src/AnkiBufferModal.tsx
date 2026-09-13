// Read-only preview of the Anki card buffer, opened from the eye button
// next to the buffered-card count in the Anki section. Renders each card
// as it will actually come out of the export — same front/back split as
// anki_export_worker.py's genanki template, respecting which fields are
// actually configured (a blank field-name setting is skipped there too).

import { DialogButton, ModalRoot } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { FaTimes } from "react-icons/fa";
import { BufferedCard, getAnkiBuffer, removeAnkiBufferCard } from "./api";

// mirrors ROLE_ORDER / CARD_KEY in py_modules/vnlookup/anki_export_worker.py
const ROLE_ORDER = [
  "expression",
  "reading",
  "glossary",
  "word_type",
  "sentence",
  "game",
] as const;
type Role = (typeof ROLE_ORDER)[number];

const ROLE_CARD_KEY: Record<Role, keyof BufferedCard> = {
  expression: "expression",
  reading: "reading",
  glossary: "glosses",
  word_type: "word_type",
  sentence: "sentence",
  game: "game",
};

// mirrors the role -> settings-key map built in main.py's export_anki_buffer
const ROLE_SETTING_KEY: Record<Role, string> = {
  expression: "anki_expression_field",
  reading: "anki_reading_field",
  glossary: "anki_glossary_field",
  word_type: "anki_word_type_field",
  sentence: "anki_sentence_field",
  game: "anki_game_field",
};

// a blank field-name setting means that role is skipped on export — same
// check as main.py's `name = (s.get(key) or "").strip(); if name: ...`
const activeRoles = (settings: Record<string, any>): Role[] =>
  ROLE_ORDER.filter((r) => !!(settings[ROLE_SETTING_KEY[r]] || "").toString().trim());

// mirrors the .r-* role classes in anki_export_worker.py's _CSS: glossary +
// sentence are the main content (medium), reading/word_type are small
// secondary detail, game is the smallest, purely-reference info
const BACK_ROLE_STYLE: Record<Exclude<Role, "expression">, { fontSize: number; opacity: number }> = {
  reading: { fontSize: 11, opacity: 0.55 },
  glossary: { fontSize: 14, opacity: 0.92 },
  word_type: { fontSize: 11, opacity: 0.55 },
  sentence: { fontSize: 14, opacity: 0.92 },
  game: { fontSize: 10, opacity: 0.5 },
};

const CardPreview: FC<{
  card: BufferedCard;
  roles: Role[];
  onRemove: () => void;
  removing: boolean;
}> = ({ card, roles, onRemove, removing }) => {
  const front = roles.length ? card[ROLE_CARD_KEY[roles[0]]] : "";
  const backRoles = roles.slice(1).filter((r) => card[ROLE_CARD_KEY[r]]);

  return (
    <div
      style={{
        position: "relative",
        border: "1px solid rgba(255,255,255,0.15)",
        borderRadius: 6,
        overflow: "hidden",
        background: "rgba(255,255,255,0.04)",
      }}
    >
      <DialogButton
        style={{
          position: "absolute",
          top: 6,
          right: 6,
          width: 26,
          height: 26,
          minWidth: 0,
          padding: 0,
          borderRadius: 4,
        }}
        disabled={removing}
        onClick={onRemove}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <FaTimes size={11} />
        </div>
      </DialogButton>
      <div
        style={{
          padding: "10px 36px 10px 12px",
          fontSize: 15,
          fontWeight: 600,
          textAlign: "center",
        }}
      >
        {front || <span style={{ opacity: 0.5 }}>(no front field configured)</span>}
      </div>
      {backRoles.length > 0 && (
        <>
          <div style={{ borderTop: "1px solid rgba(255,255,255,0.15)" }} />
          <div style={{ padding: "10px 12px", display: "flex", flexDirection: "column", gap: 6 }}>
            {backRoles.map((r) => (
              <div
                key={r}
                style={{
                  ...BACK_ROLE_STYLE[r as Exclude<Role, "expression">],
                  whiteSpace: "pre-wrap",
                  textAlign: "center",
                }}
              >
                {card[ROLE_CARD_KEY[r]]}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
};

export const AnkiBufferModal: FC<{ settings: Record<string, any>; closeModal?: () => void }> = ({
  settings,
  closeModal,
}) => {
  const [cards, setCards] = useState<BufferedCard[] | null>(null);
  const [removing, setRemoving] = useState<Set<string>>(new Set());

  useEffect(() => {
    void getAnkiBuffer().then((r) => setCards(r.cards));
  }, []);

  const roles = activeRoles(settings);

  const handleRemove = async (id: string) => {
    setRemoving((prev) => new Set(prev).add(id));
    try {
      await removeAnkiBufferCard(id);
      setCards((prev) => prev && prev.filter((c) => c.id !== id));
    } finally {
      setRemoving((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  return (
    <ModalRoot bAllowFullSize onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 10 }}>
        Buffered cards{cards ? ` (${cards.length})` : ""}
      </div>
      <div style={{ maxHeight: "65vh", overflowY: "auto" }}>
        {cards === null ? (
          <div style={{ fontSize: 13, opacity: 0.7 }}>Loading…</div>
        ) : cards.length === 0 ? (
          <div style={{ fontSize: 13, opacity: 0.7 }}>No cards buffered.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {cards.map((c) => (
              <CardPreview
                key={c.id}
                card={c}
                roles={roles}
                removing={removing.has(c.id)}
                onRemove={() => void handleRemove(c.id)}
              />
            ))}
          </div>
        )}
      </div>
    </ModalRoot>
  );
};
