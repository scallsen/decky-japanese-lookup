import { Router, staticClasses } from "@decky/ui";
import {
  addEventListener,
  removeEventListener,
  definePlugin,
  routerHook,
  toaster,
} from "@decky/api";
import { FaBookOpen } from "react-icons/fa";

import { captureAndMine, getAllSettings, VnlEvent } from "./api";
import { copyToClipboard } from "./clipboard";
import { TriggerWatcher, TriggerButton } from "./input";
import { OverlayState, VnLookupOverlay } from "./Overlay";
import { Panel } from "./Panel";

export default definePlugin(() => {
  const overlayState = new OverlayState();

  const watcher = new TriggerWatcher(() => {
    // The hidraw monitor sees the button even inside Steam menus/QAM, and
    // the capture grabs whatever gamescope composites — so only fire while
    // a game is actually running to avoid OCRing the Steam UI.
    if (!Router.MainRunningApp) return;
    void captureAndMine().catch((e) => {
      toaster.toast({ title: "VN Lookup", body: `capture failed: ${e}` });
    });
  });

  const applySettings = (s: Record<string, any>) => {
    watcher.configure(
      (s.trigger_button as TriggerButton) ?? "L5",
      typeof s.trigger_hold_ms === "number" ? s.trigger_hold_ms : 250
    );
  };

  // the backend may still be starting when the frontend loads — retry
  // until the first settings fetch succeeds so a configured trigger
  // button isn't silently replaced by the default
  let settingsLoaded = false;
  const loadInitialSettings = async (attempt = 0): Promise<void> => {
    try {
      applySettings(await getAllSettings());
      settingsLoaded = true;
    } catch {
      if (!settingsLoaded && attempt < 30) {
        setTimeout(() => void loadInitialSettings(attempt + 1), 1000);
      }
    }
  };
  void loadInitialSettings();
  watcher.start();

  const onEvent = (ev: VnlEvent) => {
    if (ev.stage === "done" && ev.text && ev.copy_to_clipboard) {
      copyToClipboard(ev.text);
    }
    overlayState.handleEvent(ev);
  };
  addEventListener<[VnlEvent]>("vnl_event", onEvent);

  const onSettings = (s: Record<string, any>) => applySettings(s);
  addEventListener<[Record<string, any>]>("vnl_settings", onSettings);

  routerHook.addGlobalComponent("VnLookupOverlay", () => (
    <VnLookupOverlay state={overlayState} />
  ));

  return {
    name: "VN Lookup",
    titleView: <div className={staticClasses.Title}>VN Lookup</div>,
    content: <Panel overlayState={overlayState} />,
    icon: <FaBookOpen />,
    alwaysRender: true,
    onDismount() {
      watcher.stop();
      removeEventListener("vnl_event", onEvent);
      removeEventListener("vnl_settings", onSettings);
      routerHook.removeGlobalComponent("VnLookupOverlay");
    },
  };
});
