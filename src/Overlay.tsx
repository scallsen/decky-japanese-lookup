// In-game status overlay. The useUIComposition hook (found by scanning
// webpack modules, same trick as Decky-Translator) is what makes Steam
// composite our React tree over the running game.

import { findModuleChild } from "@decky/ui";
import { FC, ReactNode, useEffect, useState } from "react";
import type { Region, VnlEvent } from "./api";

enum UIComposition {
  Hidden = 0,
  Notification = 1,
  Overlay = 2,
  Opaque = 3,
  OverlayKeyboard = 4,
}

const useUIComposition: (composition: UIComposition) => void = findModuleChild(
  (m) => {
    if (typeof m !== "object") return undefined;
    for (const prop in m) {
      if (
        typeof m[prop] === "function" &&
        m[prop].toString().includes("AddMinimumCompositionStateRequest") &&
        m[prop].toString().includes("ChangeMinimumCompositionStateRequest") &&
        m[prop].toString().includes("RemoveMinimumCompositionStateRequest") &&
        !m[prop].toString().includes("m_mapCompositionStateRequests")
      ) {
        return m[prop];
      }
    }
  }
);

const CompositionRequest: FC<{ level: UIComposition }> = ({ level }) => {
  useUIComposition(level);
  return null;
};

export interface OverlayModel {
  visible: boolean;
  stage: string;
  text?: string;
  raw?: string;
  message?: string;
  warning?: string | null;
  confidence?: number;
  clients?: number;
  previewRegion?: Region | null;
}

type Listener = (model: OverlayModel) => void;

export class OverlayState {
  private model: OverlayModel = { visible: false, stage: "" };
  private listeners = new Set<Listener>();
  private hideTimer: ReturnType<typeof setTimeout> | null = null;
  private previewTimer: ReturnType<typeof setTimeout> | null = null;

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.model);
    return () => this.listeners.delete(fn);
  }

  private set(model: OverlayModel) {
    this.model = model;
    this.listeners.forEach((fn) => fn(model));
  }

  private scheduleHide(ms: number) {
    if (this.hideTimer) clearTimeout(this.hideTimer);
    this.hideTimer = setTimeout(
      () => this.set({ ...this.model, visible: false }), ms);
  }

  // Show the capture region as a rectangle over the game while the user
  // drags the sliders; auto-hides shortly after the last adjustment.
  showRegionPreview(region: Region) {
    if (this.previewTimer) clearTimeout(this.previewTimer);
    this.set({ ...this.model, previewRegion: region });
    this.previewTimer = setTimeout(
      () => this.set({ ...this.model, previewRegion: null }), 2500);
  }

  handleEvent(ev: VnlEvent) {
    if (this.hideTimer) clearTimeout(this.hideTimer);
    switch (ev.stage) {
      case "capturing":
        // hide everything: the overlay itself would be captured (and then
        // OCR'd) since the screenshot is of the composited screen
        this.set({ visible: false, stage: "capturing" });
        break;
      case "ocr":
        this.set({ visible: true, stage: "ocr" });
        break;
      case "done":
        this.set({
          visible: true, stage: "done", text: ev.text, raw: ev.raw,
          warning: ev.warning, confidence: ev.confidence, clients: ev.clients,
        });
        this.scheduleHide(ev.warning ? 6000 : 4000);
        break;
      case "error":
        this.set({
          visible: true, stage: "error",
          message: ev.message, raw: ev.raw,
        });
        this.scheduleHide(7000);
        break;
      case "anki":
        // brief unobtrusive confirmation that a card got its screenshot
        this.set({ visible: true, stage: "anki" });
        this.scheduleHide(2000);
        break;
    }
  }
}

export const VnLookupOverlay: FC<{ state: OverlayState }> = ({ state }) => {
  const [model, setModel] = useState<OverlayModel>({ visible: false, stage: "" });

  useEffect(() => state.subscribe(setModel), [state]);

  if (!model.visible && !model.previewRegion) return null;

  const isError = model.stage === "error";
  const border = isError ? "#c0392b" : model.warning ? "#c87f0a" : "#2c6e49";

  let body: ReactNode;
  switch (model.stage) {
    case "capturing":
      body = <span>📷 Capturing…</span>;
      break;
    case "ocr":
      body = <span>🔎 Reading text…</span>;
      break;
    case "anki":
      body = <span>🃏 Anki card enriched</span>;
      break;
    case "error":
      body = (
        <>
          <div style={{ fontWeight: 600 }}>⚠ {model.message}</div>
          {model.raw ? (
            <div style={{ opacity: 0.85, fontSize: "0.85em", marginTop: 4 }}>
              raw OCR: {model.raw}
            </div>
          ) : null}
        </>
      );
      break;
    default: // done
      body = (
        <>
          <div style={{ fontSize: "1.15em", lineHeight: 1.5 }}>{model.text}</div>
          <div style={{ opacity: 0.7, fontSize: "0.78em", marginTop: 4 }}>
            {typeof model.confidence === "number"
              ? `confidence ${(model.confidence * 100).toFixed(0)}%`
              : ""}
            {model.clients !== undefined
              ? ` · ${model.clients} reader${model.clients === 1 ? "" : "s"} connected`
              : ""}
          </div>
          {model.warning ? (
            <div style={{ color: "#f0b458", fontSize: "0.85em", marginTop: 2 }}>
              {model.warning}
            </div>
          ) : null}
        </>
      );
  }

  const preview = model.previewRegion;

  return (
    <>
      <CompositionRequest level={UIComposition.Notification} />
      {preview && (
        <div
          style={{
            position: "fixed",
            left: `${preview.x * 100}vw`,
            top: `${preview.y * 100}vh`,
            width: `${preview.w * 100}vw`,
            height: `${preview.h * 100}vh`,
            zIndex: 7001,
            border: "3px dashed #4fc3f7",
            background: "rgba(79, 195, 247, 0.12)",
            boxSizing: "border-box",
            pointerEvents: "none",
          }}
        >
          <span
            style={{
              position: "absolute",
              top: 2,
              left: 6,
              color: "#4fc3f7",
              fontSize: 13,
              fontWeight: 600,
              textShadow: "0 0 4px #000",
            }}
          >
            OCR region
          </span>
        </div>
      )}
      {model.visible && (
      <div
        style={{
          // top of the screen: VN text boxes (and the capture region) live
          // at the bottom, so a lingering result pill can't be re-captured
          position: "fixed",
          left: "50%",
          top: "4%",
          transform: "translateX(-50%)",
          zIndex: 7002,
          maxWidth: "86vw",
          background: "rgba(10, 10, 14, 0.92)",
          border: `2px solid ${border}`,
          borderRadius: 10,
          padding: "10px 16px",
          color: "#f2f2f2",
          fontFamily: '"Noto Sans CJK JP", "Hiragino Sans", sans-serif',
          fontSize: 16,
          pointerEvents: "none",
        }}
      >
        {body}
      </div>
      )}
    </>
  );
};
