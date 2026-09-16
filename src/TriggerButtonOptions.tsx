// Capture area trigger-button picker, using Valve's own Steam Deck button
// glyphs (assets/icons, pulled from the Steam Deck source files — each one
// already has its code, e.g. "L4", drawn into the artwork). "cutout" is
// the light/white-on-transparent variant for the normal dark row
// background; "dark" is a color-swapped variant for whenever a row is
// highlighted (its background goes solid white, so the light icon
// disappears into it).
//
// This used to be a native Dropdown, but neither its D-pad-driven row
// highlight nor a tap-and-hold highlight fire real mouse enter/leave (or
// anything else exposed to plugins), so there was no way to know which row
// to swap. It's now @decky/ui's Menu/MenuItem + showContextMenu — a popup
// anchored to the triggering button (not inline, not a full modal), whose
// MenuItem exposes both a real onMouseEnter and onGamepadFocus/onGamepadBlur
// (via FooterLegendProps), so the highlight state is ours either way.

import { DialogButton, Menu, MenuItem, showContextMenu } from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import { FaChevronDown } from "react-icons/fa";
import cutoutL1 from "../assets/icons/cutout/sd_l1.svg";
import cutoutL2 from "../assets/icons/cutout/sd_l2.svg";
import cutoutL3 from "../assets/icons/cutout/shared_l3.svg";
import cutoutL4 from "../assets/icons/cutout/sd_l4.svg";
import cutoutL5 from "../assets/icons/cutout/sd_l5.svg";
import cutoutR1 from "../assets/icons/cutout/sd_r1.svg";
import cutoutR2 from "../assets/icons/cutout/sd_r2.svg";
import cutoutR3 from "../assets/icons/cutout/shared_r3.svg";
import cutoutR4 from "../assets/icons/cutout/sd_r4.svg";
import cutoutR5 from "../assets/icons/cutout/sd_r5.svg";
import darkL1 from "../assets/icons/dark/sd_l1.svg";
import darkL2 from "../assets/icons/dark/sd_l2.svg";
import darkL3 from "../assets/icons/dark/shared_l3.svg";
import darkL4 from "../assets/icons/dark/sd_l4.svg";
import darkL5 from "../assets/icons/dark/sd_l5.svg";
import darkR1 from "../assets/icons/dark/sd_r1.svg";
import darkR2 from "../assets/icons/dark/sd_r2.svg";
import darkR3 from "../assets/icons/dark/shared_r3.svg";
import darkR4 from "../assets/icons/dark/sd_r4.svg";
import darkR5 from "../assets/icons/dark/sd_r5.svg";
import { TRIGGER_BUTTONS, TriggerButton } from "./input";

const BUTTON_ICON_LIGHT: Record<TriggerButton, string> = {
  L1: cutoutL1, R1: cutoutR1,
  L2: cutoutL2, R2: cutoutR2,
  L3: cutoutL3, R3: cutoutR3,
  L4: cutoutL4, R4: cutoutR4,
  L5: cutoutL5, R5: cutoutR5,
};

const BUTTON_ICON_DARK: Record<TriggerButton, string> = {
  L1: darkL1, R1: darkR1,
  L2: darkL2, R2: darkR2,
  L3: darkL3, R3: darkR3,
  L4: darkL4, R4: darkR4,
  L5: darkL5, R5: darkR5,
};

const BUTTON_CATEGORY: Record<TriggerButton, string> = {
  L1: "Bumper", R1: "Bumper",
  L2: "Trigger", R2: "Trigger",
  L3: "Stick", R3: "Stick",
  L4: "Button", R4: "Button",
  L5: "Button", R5: "Button",
};

// small enough to sit inside the same button chrome as the plain-text
// "Change area" DialogButton next to it, rather than forcing it taller
const ICON_SIZE = 18;

export const TriggerButtonIcon: FC<{
  code: string;
  dark?: boolean;
  size?: number;
}> = ({ code, dark, size = ICON_SIZE }) =>
  code === "off" ? null : (
    <img
      src={(dark ? BUTTON_ICON_DARK : BUTTON_ICON_LIGHT)[code as TriggerButton]}
      width={size}
      height={size}
    />
  );

// closed selector button — fills the row next to "Change area", left-
// aligned (no extra padding of our own, so the left inset matches the
// button's own top/bottom padding), with a chevron for menu affordance.
//
// A tap that picks an option in the popup this opens can leave a stray
// mouseenter (or a focus handoff) firing on this button *after* the popup
// is gone, with no reliable follow-up event to clear it again. On the A-
// button path this never happens — Steam hands real DOM focus back here,
// which is also what paints its native white fill. So on close, force the
// same thing to happen for a tap: pull real focus back onto this element
// (matching the entriesRef pattern in LookupPanel.tsx), so touch ends up
// in the exact same state a gamepad pick already lands in. The manual
// background fill stays as a fallback for whatever that doesn't catch —
// white now, to match Steam's own fill (and the dark icon variant, which
// was clearly drawn to sit on white) instead of introducing another color.
export const TriggerButtonSelector: FC<{
  code: string | null;
  onOpen: (parent: EventTarget, resetHighlight: () => void) => void;
}> = ({ code, onOpen }) => {
  const [gamepadFocused, setGamepadFocused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const dark = gamepadFocused || hovered;
  const buttonRef = useRef<HTMLDivElement>(null);

  const resetHighlight = () => {
    setGamepadFocused(false);
    setHovered(false);
    buttonRef.current?.focus();
  };

  return (
    <DialogButton
      ref={buttonRef}
      style={{
        flex: 1,
        minWidth: 0,
        background: dark ? "rgba(255,255,255,0.9)" : undefined,
      }}
      onGamepadFocus={() => setGamepadFocused(true)}
      onGamepadBlur={() => setGamepadFocused(false)}
      onClick={(e) => {
        if (e.currentTarget) onOpen(e.currentTarget, resetHighlight);
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: "100%",
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {code ? (
            <TriggerButtonIcon code={code} dark={dark} />
          ) : (
            <span style={{ color: dark ? "#0E141B" : undefined }}>None</span>
          )}
        </div>
        <FaChevronDown
          size={10}
          color={dark ? "#0E141B" : undefined}
          style={{ opacity: 0.7, flexShrink: 0 }}
        />
      </div>
    </DialogButton>
  );
};

const OPTIONS: { data: "off" | TriggerButton; label: string }[] = [
  { data: "off", label: "None" },
  ...TRIGGER_BUTTONS.map((b) => ({ data: b, label: BUTTON_CATEGORY[b] })),
];

// MenuItem has no onMouseLeave at all (only onMouseEnter) — so per-item
// local hover state can never be cleared by mouse/touch, and a scroll or
// tap can leave several items stuck dark with nothing to un-set them.
// Tracking a single "which one is hovered" value at the list level instead
// sidesteps that entirely: entering a new item overwrites it, which
// un-highlights whichever was previously marked — no leave event needed.
const TriggerMenuItem: FC<{
  opt: (typeof OPTIONS)[number];
  isCurrent: boolean;
  isHovered: boolean;
  onHover: () => void;
  onPick: (button: string | null) => void;
}> = ({ opt, isCurrent, isHovered, onHover, onPick }) => (
  <MenuItem
    onMouseEnter={onHover}
    onGamepadFocus={onHover}
    onSelected={() => onPick(opt.data === "off" ? null : opt.data)}
  >
    <span style={{ display: "flex", alignItems: "center", gap: 14 }}>
      {opt.data !== "off" && <TriggerButtonIcon code={opt.data} dark={isHovered} />}
      <span
        style={{
          color: isHovered ? "#0E141B" : isCurrent ? "#fff" : undefined,
        }}
      >
        {opt.label}
      </span>
    </span>
  </MenuItem>
);

const TriggerButtonMenuContent: FC<{
  current: string | null;
  onPick: (button: string | null) => void;
  onClose: () => void;
}> = ({ current, onPick, onClose }) => {
  const [hovered, setHovered] = useState<string | null>(null);

  // onCancel only covers the gamepad Cancel button, not a tap outside the
  // menu — but every dismiss path (pick, cancel, tap-away) unmounts this
  // component either way, so that's the one signal that reliably covers
  // all of them.
  useEffect(() => onClose, [onClose]);

  return (
    <Menu label="Capture button">
      {OPTIONS.map((opt) => (
        <TriggerMenuItem
          key={opt.data}
          opt={opt}
          isCurrent={(current ?? "off") === opt.data}
          isHovered={hovered === opt.data}
          onHover={() => setHovered(opt.data)}
          onPick={onPick}
        />
      ))}
    </Menu>
  );
};

// popup anchored to the triggering button — call with the DOM element that
// was clicked/activated (e.g. a DialogButton's onClick event target).
// onClose fires whether the menu was dismissed by picking or cancelling,
// so the caller can clear its own hover state (see TriggerButtonSelector).
export const openTriggerButtonMenu = (
  parent: EventTarget,
  current: string | null,
  onPick: (button: string | null) => void,
  onClose: () => void
) => {
  showContextMenu(
    <TriggerButtonMenuContent current={current} onPick={onPick} onClose={onClose} />,
    parent
  );
};
