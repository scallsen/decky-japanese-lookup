import { Navigation, QuickAccessTab, Router, staticClasses } from "@decky/ui";
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
import { TriggerButton, TriggerWatcher } from "./input";
import { OverlayState, VnLookupOverlay } from "./Overlay";
import { Panel } from "./Panel";

export default definePlugin(() => {
  const overlayState = new OverlayState();

  const watcher = new TriggerWatcher((button) => {
    // The hidraw monitor sees the button even inside Steam menus/QAM, and
    // the capture grabs whatever gamescope composites — so only fire while
    // a game is actually running to avoid OCRing the Steam UI.
    if (!Router.MainRunningApp) return;
    void captureAndMine(button).catch((e) => {
      toaster.toast({ title: "VN Lookup", body: `capture failed: ${e}` });
    });
  });

  const applySettings = (s: Record<string, any>) => {
    const areas = Array.isArray(s.capture_areas) ? s.capture_areas : [];
    const watched = areas
      .map((a: any) => a?.button)
      .filter(Boolean) as TriggerButton[];
    watcher.configure(
      watched,
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
    if (ev.stage === "done" && ev.auto_open_qam) {
      // select our plugin in Decky's QAM tab before opening it.
      // deckyState is TS-private but present at runtime; internal API, so
      // fail soft — worst case the QAM opens on the last-used view.
      try {
        (window as any).DeckyPluginLoader?.deckyState?.setActivePlugin?.("VN Lookup");
      } catch {
        /* decky internals changed; QAM still opens */
      }
      Navigation.OpenQuickAccessMenu(QuickAccessTab.Decky);
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
    content: <Panel />,
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
