// Trigger watcher: polls the backend's hidraw button state and fires the
// capture pipeline when a mapped back button is held long enough. Each
// button can capture a different screen layout (text box / alt region /
// full screen), so games with multiple text layouts get one button per
// layout. Polling (rather than events) mirrors Decky-Translator — it is
// robust against missed packets and multiple frontend instances.

import { getButtonState } from "./api";

export type TriggerButton = "L4" | "R4" | "L5" | "R5";
export type CaptureMode = "box" | "alt" | "fullscreen";
export type ButtonMap = Partial<Record<TriggerButton, CaptureMode | "off">>;

export const TRIGGER_BUTTONS: TriggerButton[] = ["L4", "R4", "L5", "R5"];

interface PressState {
  pressStart: number | null;
  fired: boolean;
}

export class TriggerWatcher {
  private interval: ReturnType<typeof setInterval> | null = null;
  private pollMs = 100;

  private map: ButtonMap = { L5: "box" };
  private holdMs = 250;

  private press: Record<string, PressState> = {};
  private cooldownUntil = 0;

  constructor(private onTrigger: (mode: CaptureMode) => void) {}

  configure(map: ButtonMap, holdMs: number) {
    this.map = map;
    this.holdMs = holdMs;
    this.press = {};
  }

  start() {
    if (this.interval) return;
    this.interval = setInterval(() => void this.poll(), this.pollMs);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  private async poll() {
    const watched = TRIGGER_BUTTONS.filter(
      (b) => this.map[b] && this.map[b] !== "off"
    );
    if (watched.length === 0) return;

    let pressed: Set<string>;
    try {
      const state = await getButtonState();
      if (!state?.success) return;
      pressed = new Set(state.buttons);
    } catch {
      return; // backend not up yet; try again next tick
    }

    const now = Date.now();
    for (const button of watched) {
      const st = (this.press[button] ??= { pressStart: null, fired: false });
      if (pressed.has(button)) {
        if (st.pressStart === null) {
          st.pressStart = now;
          st.fired = false;
        }
        if (!st.fired && now >= this.cooldownUntil &&
            now - st.pressStart >= this.holdMs) {
          st.fired = true;
          this.cooldownUntil = now + 800;
          this.onTrigger(this.map[button] as CaptureMode);
        }
      } else {
        st.pressStart = null;
        st.fired = false;
      }
    }
  }
}
