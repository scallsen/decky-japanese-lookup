// Read-only preview of the Anki card buffer, opened from the eye button
// next to the buffered-card count in the Anki section.

import { ModalRoot } from "@decky/ui";
import { FC, useEffect, useState } from "react";
import { BufferedCard, getAnkiBuffer } from "./api";

export const AnkiBufferModal: FC<{ closeModal?: () => void }> = ({ closeModal }) => {
  const [cards, setCards] = useState<BufferedCard[] | null>(null);

  useEffect(() => {
    void getAnkiBuffer().then((r) => setCards(r.cards));
  }, []);

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
          cards.map((c, i) => (
            <div
              key={c.id}
              style={{
                borderTop: i > 0 ? "1px solid rgba(255,255,255,0.1)" : "none",
                padding: "10px 0",
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 600 }}>
                {c.expression}
                {c.reading ? (
                  <span style={{ fontWeight: 400, opacity: 0.7 }}> ({c.reading})</span>
                ) : null}
              </div>
              {c.glosses ? (
                <div style={{ fontSize: 12, opacity: 0.85, marginTop: 2 }}>{c.glosses}</div>
              ) : null}
              {c.sentence ? (
                <div style={{ fontSize: 12, opacity: 0.65, marginTop: 4 }}>{c.sentence}</div>
              ) : null}
              {c.game ? (
                <div style={{ fontSize: 11, opacity: 0.5, marginTop: 4 }}>{c.game}</div>
              ) : null}
            </div>
          ))
        )}
      </div>
    </ModalRoot>
  );
};
