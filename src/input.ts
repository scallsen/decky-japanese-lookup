// Trigger watcher: polls the backend's hidraw button state and fires the
// capture pipeline when a button assigned to a capture area is pressed.
// Polling (rather than events) mirrors Decky-Translator — it is robust
// against missed packets and multiple frontend instances.

import { getButtonState } from "./api";

export type TriggerButton =
  | "L1" | "L2" | "L3" | "L4" | "L5"
  | "R1" | "R2" | "R3" | "R4" | "R5";

export const TRIGGER_BUTTONS: TriggerButton[] = [
  "L1", "L2", "L3", "L4", "L5",
  "R1", "R2", "R3", "R4", "R5",
];

const POLL_MS = 100;
// minimum gap between two captures, across all buttons
const COOLDOWN_MS = 800;

export class TriggerWatcher {
  private interval: ReturnType<typeof setInterval> | null = null;
  private watched: TriggerButton[] = [];
  // buttons currently held that have already fired for this press
  private fired = new Set<TriggerButton>();
  private cooldownUntil = 0;

  constructor(private onTrigger: (button: TriggerButton) => void) {}

  configure(watched: TriggerButton[]) {
    this.watched = watched;
    this.fired.clear();
  }

  start() {
    if (this.interval) return;
    this.interval = setInterval(() => void this.poll(), POLL_MS);
  }

  stop() {
    if (this.interval) {
      clearInterval(this.interval);
      this.interval = null;
    }
  }

  private async poll() {
    if (this.watched.length === 0) return;

    let pressed: Set<string>;
    try {
      const state = await getButtonState();
      if (!state?.success) return;
      pressed = new Set(state.buttons);
    } catch {
      return; // backend not up yet; try again next tick
    }

    const now = Date.now();
    for (const button of this.watched) {
      if (!pressed.has(button)) {
        this.fired.delete(button);
      } else if (!this.fired.has(button) && now >= this.cooldownUntil) {
        this.fired.add(button);
        this.cooldownUntil = now + COOLDOWN_MS;
        this.onTrigger(button);
      }
    }
  }
}
