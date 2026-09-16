// Full-screen visual region editor: the current game frame as the canvas,
// the capture region as a box on top of it. Touch: drag the box to move,
// drag corner handles to resize. Gamepad: D-pad moves, L1/R1 resize width,
// L2/R2 resize height, X auto-detects, A saves. Auto-detect snaps the box
// to the union of OCR-detected Japanese text.

import {
  DialogButton,
  Focusable,
  GamepadButton,
  GamepadEvent,
  ModalRoot,
  Navigation,
  QuickAccessTab,
  showModal,
} from "@decky/ui";
import { CSSProperties, FC, useEffect, useRef, useState } from "react";
import {
  captureEditorFrame,
  detectRegion,
  getEditorFrame,
  Region,
  SCREEN_ASPECT_RATIO,
} from "./api";

const MIN = 0.05;
const STEP = 0.01;

const clampRegion = (r: Region): Region => {
  const w = Math.min(1, Math.max(MIN, r.w));
  const h = Math.min(1, Math.max(MIN, r.h));
  return {
    x: Math.min(1 - w, Math.max(0, r.x)),
    y: Math.min(1 - h, Math.max(0, r.y)),
    w,
    h,
  };
};

// Opens the editor with a FRESH frame: close all UI first (a capture is
// the composited screen — any visible UI would be photographed), grab the
// frame, then bring the QAM back and mount the modal. Falls back to the
// latest pipeline capture when fresh capture fails (e.g. no game running).
export const openRegionEditor = (
  title: string,
  initial: Region,
  onSave: (region: Region, image: string | null) => void
) => {
  Navigation.CloseSideMenus();
  setTimeout(async () => {
    const fresh = await captureEditorFrame();
    let image = fresh.ok ? fresh.image : undefined;
    let msg = fresh.ok ? undefined : fresh.error;
    if (!image) {
      const last = await getEditorFrame();
      if (last.ok && last.image) {
        image = last.image;
        msg = `${msg ?? "capture failed"} — showing last capture`;
      }
    }
    // mount the modal directly over the game — do NOT reopen the QAM
    // first: a freshly opened QAM steals gamepad focus from the modal,
    // which kills the bumper/trigger controls and the footer legend
    showModal(
      <RegionEditorModal
        title={title}
        onSave={onSave}
        initial={initial}
        initialImage={image}
        initialMessage={msg}
      />
    );
  }, 500);
};

type DragMode =
  | { kind: "move"; startX: number; startY: number; orig: Region }
  | { kind: "resize"; corner: "nw" | "ne" | "sw" | "se"; startX: number; startY: number; orig: Region }
  | null;

const handleStyle = (corner: string): CSSProperties => ({
  position: "absolute",
  width: 28,
  height: 28,
  ...(corner.includes("n") ? { top: -14 } : { bottom: -14 }),
  ...(corner.includes("w") ? { left: -14 } : { right: -14 }),
  borderRadius: "50%",
  background: "#4fc3f7",
  border: "3px solid #fff",
  boxSizing: "border-box",
  touchAction: "none",
});

export const RegionEditorModal: FC<{
  title: string;
  onSave: (region: Region, image: string | null) => void;
  initial: Region;
  initialImage?: string;
  initialMessage?: string;
  closeModal?: () => void;
}> = ({ title, onSave, initial, initialImage, initialMessage, closeModal }) => {
  const [region, setRegion] = useState<Region>(initial);
  const [image, setImage] = useState<string | null>(initialImage ?? null);
  const [message, setMessage] = useState(
    initialMessage ?? (initialImage ? "" : "Loading latest capture…"));
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<DragMode>(null);
  // bumpers/triggers only emit a single down event — repeat while held
  const heldRepeat = useRef<{ code: number; timer: ReturnType<typeof setInterval> } | null>(null);

  const stopRepeat = () => {
    if (heldRepeat.current) {
      clearInterval(heldRepeat.current.timer);
      heldRepeat.current = null;
    }
  };

  useEffect(() => {
    if (!initialImage) {
      void getEditorFrame().then((r) => {
        if (r.ok && r.image) {
          setImage(r.image);
          setMessage("");
        } else {
          setMessage(r.error ?? "no capture available");
        }
      });
    }
    return stopRepeat;
  }, [initialImage]);

  const frac = (e: { clientX: number; clientY: number }) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    return {
      fx: (e.clientX - rect.left) / rect.width,
      fy: (e.clientY - rect.top) / rect.height,
    };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const { fx, fy } = frac(e);
    const dx = fx - d.startX;
    const dy = fy - d.startY;
    if (d.kind === "move") {
      setRegion(clampRegion({ ...d.orig, x: d.orig.x + dx, y: d.orig.y + dy }));
    } else {
      // west/north handles move the origin and shrink; east/south just grow
      const { orig } = d;
      const west = d.corner.includes("w");
      const north = d.corner.includes("n");
      setRegion(clampRegion({
        x: west ? orig.x + dx : orig.x,
        y: north ? orig.y + dy : orig.y,
        w: west ? orig.w - dx : orig.w + dx,
        h: north ? orig.h - dy : orig.h + dy,
      }));
    }
  };

  const startDrag = (e: React.PointerEvent, mode: DragMode) => {
    e.stopPropagation();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = mode;
  };

  const nudge = (dx: number, dy: number) =>
    setRegion((r) => clampRegion({ ...r, x: r.x + dx, y: r.y + dy }));
  const grow = (dw: number, dh: number) =>
    setRegion((r) => clampRegion({ ...r, w: r.w + dw, h: r.h + dh }));

  const autoDetect = async () => {
    setMessage("Detecting text in the capture…");
    const r = await detectRegion();
    if (r.ok && r.region) {
      setRegion(clampRegion(r.region));
      if (r.image) setImage(r.image);
      setMessage("Snapped to detected text — adjust if needed");
    } else {
      setMessage(r.error ?? "detection failed");
    }
  };

  const save = () => {
    onSave(region, image);
    closeModal?.();
    // mirrors the post-capture flow in index.tsx: closing this modal drops
    // the user back on the bare game view, so bring the QAM back up rather
    // than leaving them to reopen it by hand
    Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
  };

  const onDirection = (e: GamepadEvent) => {
    const b = e.detail.button;
    if (b === GamepadButton.DIR_UP) nudge(0, -STEP);
    else if (b === GamepadButton.DIR_DOWN) nudge(0, STEP);
    else if (b === GamepadButton.DIR_LEFT) nudge(-STEP, 0);
    else if (b === GamepadButton.DIR_RIGHT) nudge(STEP, 0);
    else return;
    e.preventDefault();
    e.stopPropagation();
  };

  const RESIZE_ACTIONS: Partial<Record<number, () => void>> = {
    [GamepadButton.BUMPER_LEFT]: () => grow(-STEP, 0),
    [GamepadButton.BUMPER_RIGHT]: () => grow(STEP, 0),
    [GamepadButton.TRIGGER_LEFT]: () => grow(0, -STEP),
    [GamepadButton.TRIGGER_RIGHT]: () => grow(0, STEP),
  };

  const onButtonDown = (e: GamepadEvent) => {
    const code = e.detail.button;
    const action = RESIZE_ACTIONS[code];
    if (action) {
      action();
      // Steam doesn't send repeats for bumpers/triggers — self-repeat
      // until the matching button-up arrives
      if (heldRepeat.current?.code !== code) {
        stopRepeat();
        heldRepeat.current = {
          code,
          timer: setInterval(action, 90),
        };
      }
    } else if (code === GamepadButton.SECONDARY) {
      void autoDetect();
    } else {
      return;
    }
    e.preventDefault();
    e.stopPropagation();
  };

  const onButtonUp = (e: GamepadEvent) => {
    if (heldRepeat.current?.code === e.detail.button) stopRepeat();
  };

  return (
    <ModalRoot bAllowFullSize onCancel={closeModal} closeModal={closeModal}>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 6 }}>
        {title}
      </div>
      <Focusable
        onActivate={save}
        onGamepadDirection={onDirection}
        onButtonDown={onButtonDown}
        onButtonUp={onButtonUp}
        onOKActionDescription="Save"
        onSecondaryActionDescription="Auto-detect"
        actionDescriptionMap={{
          [GamepadButton.DIR_UP]: "Move",
          [GamepadButton.BUMPER_LEFT]: "Width −",
          [GamepadButton.BUMPER_RIGHT]: "Width +",
          [GamepadButton.TRIGGER_LEFT]: "Height −",
          [GamepadButton.TRIGGER_RIGHT]: "Height +",
        }}
      >
        <div
          ref={canvasRef}
          onPointerMove={onPointerMove}
          onPointerUp={() => (drag.current = null)}
          onPointerCancel={() => (drag.current = null)}
          style={{
            position: "relative",
            width: "100%",
            aspectRatio: SCREEN_ASPECT_RATIO,
            background: "#000",
            overflow: "hidden",
            borderRadius: 6,
            touchAction: "none",
          }}
        >
          {image ? (
            <img
              src={`data:image/png;base64,${image}`}
              style={{
                position: "absolute",
                inset: 0,
                width: "100%",
                height: "100%",
                objectFit: "fill",
              }}
            />
          ) : null}
          <div
            onPointerDown={(e) => {
              const f = frac(e);
              startDrag(e, { kind: "move", startX: f.fx, startY: f.fy, orig: region });
            }}
            style={{
              position: "absolute",
              left: `${region.x * 100}%`,
              top: `${region.y * 100}%`,
              width: `${region.w * 100}%`,
              height: `${region.h * 100}%`,
              border: "3px dashed #4fc3f7",
              background: "rgba(79,195,247,0.15)",
              boxSizing: "border-box",
              touchAction: "none",
              cursor: "move",
            }}
          >
            {(["nw", "ne", "sw", "se"] as const).map((corner) => (
              <div
                key={corner}
                style={handleStyle(corner)}
                onPointerDown={(e) => {
                  const f = frac(e);
                  startDrag(e, {
                    kind: "resize",
                    corner,
                    startX: f.fx,
                    startY: f.fy,
                    orig: region,
                  });
                }}
              />
            ))}
          </div>
        </div>
      </Focusable>

      <div
        style={{
          display: "flex",
          gap: 8,
          marginTop: 10,
          alignItems: "center",
        }}
      >
        <DialogButton style={{ width: "fit-content", minWidth: 0 }} onClick={() => void autoDetect()}>
          Auto-detect (X)
        </DialogButton>
        <DialogButton style={{ width: "fit-content", minWidth: 0 }} onClick={save}>
          Save (A)
        </DialogButton>
        <DialogButton style={{ width: "fit-content", minWidth: 0 }} onClick={() => closeModal?.()}>
          Cancel (B)
        </DialogButton>
        <span style={{ fontSize: 12, opacity: 0.7 }}>
          {message || "Touch: drag the box or its corners"}
        </span>
      </div>
    </ModalRoot>
  );
};
