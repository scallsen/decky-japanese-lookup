// Trigger watcher: polls the backend's hidraw button state and fires the
// capture pipeline when the configured back button is held long enough.
// Polling (rather than events) mirrors Decky-Translator — it is robust
// against missed packets and multiple frontend instances.

import { getButtonState } from "./api";

export type TriggerButton = "L4" | "R4" | "L5" | "R5";

export class TriggerWatcher {
  private interval: ReturnType<typeof setInterval> | null = null;
  private pollMs = 100;

  private button: TriggerButton = "L5";
  private holdMs = 250;

  private pressStart: number | null = null;
  private fired = false;
  private cooldownUntil = 0;

  constructor(private onTrigger: () => void) {}

  configure(button: TriggerButton, holdMs: number) {
    this.button = button;
    this.holdMs = holdMs;
    this.pressStart = null;
    this.fired = false;
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
    let pressed = false;
    try {
      const state = await getButtonState();
      pressed = !!state?.success && state.buttons.includes(this.button);
    } catch {
      return; // backend not up yet; try again next tick
    }

    const now = Date.now();
    if (pressed) {
      if (this.pressStart === null) {
        this.pressStart = now;
        this.fired = false;
      }
      if (!this.fired && now >= this.cooldownUntil &&
          now - this.pressStart >= this.holdMs) {
        this.fired = true;
        this.cooldownUntil = now + 800;
        this.onTrigger();
      }
    } else {
      this.pressStart = null;
      this.fired = false;
    }
  }
}
