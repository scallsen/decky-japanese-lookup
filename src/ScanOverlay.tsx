// In-game scan indicator: outlines whichever capture area is actively being
// OCR'd, directly over the running game. Only shown during the "ocr" stage
// — strictly after the frame is already captured, so there's no risk of
// the overlay itself being photographed (unlike the old status overlay,
// which had to hide itself during the "capturing" stage for that reason).
// Cleared as soon as the result (or an error) comes back.
//
// The useUIComposition hook below (the findModuleChild lookup and
// UIComposition enum) is ported from cat-in-a-box/Decky-Translator's
// Overlay.tsx, GPL-3.0-or-later — see the project LICENSE.

import { findModuleChild } from "@decky/ui";
import { addEventListener, removeEventListener } from "@decky/api";
import { FC, useEffect, useState } from "react";
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

export const ScanOverlay: FC = () => {
  const [region, setRegion] = useState<Region | null>(null);

  useEffect(() => {
    const onEvent = (ev: VnlEvent) => {
      if (ev.stage === "ocr") setRegion(ev.region ?? null);
      else if (ev.stage === "done" || ev.stage === "error") setRegion(null);
    };
    addEventListener<[VnlEvent]>("vnl_event", onEvent);
    return () => removeEventListener("vnl_event", onEvent);
  }, []);

  if (!region) return null;

  return (
    <>
      <CompositionRequest level={UIComposition.Notification} />
      <style>{`
        @keyframes vnl-scan-pulse {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
      `}</style>
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 7002,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: `${region.x * 100}%`,
            top: `${region.y * 100}%`,
            width: `${region.w * 100}%`,
            height: `${region.h * 100}%`,
            border: "2px dashed #4fc3f7",
            background: "rgba(79,195,247,0.12)",
            borderRadius: 4,
            boxSizing: "border-box",
            animation: "vnl-scan-pulse 1.1s ease-in-out infinite",
          }}
        />
      </div>
    </>
  );
};
