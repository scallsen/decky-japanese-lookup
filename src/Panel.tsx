import {
  ButtonItem,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
} from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import {
  captureAndMine,
  downloadModels,
  enrichLatestNote,
  getAllSettings,
  getStatus,
  installRuntime,
  PluginStatus,
  Region,
  setSetting,
  testLine,
} from "./api";
import { LookupSection } from "./LookupPanel";
import type { OverlayState } from "./Overlay";

const TRIGGER_OPTIONS = ["L4", "R4", "L5", "R5"].map((b) => ({
  data: b,
  label: `${b} (back button)`,
}));

const BACKEND_OPTIONS = [
  { data: "rapidocr", label: "Local (RapidOCR, offline)" },
  { data: "gemini", label: "Cloud (Gemini Vision)" },
];

const ANKI_IMAGE_OPTIONS = [
  { data: "full", label: "Full screenshot" },
  { data: "crop", label: "Text box crop" },
];

export const Panel: FC<{ overlayState: OverlayState }> = ({ overlayState }) => {
  const [status, setStatus] = useState<PluginStatus | null>(null);
  const [settings, setSettingsState] = useState<Record<string, any> | null>(null);
  const [busyMsg, setBusyMsg] = useState("");
  const alive = useRef(true);

  const refreshStatus = async () => {
    try {
      const s = await getStatus();
      if (alive.current) setStatus(s);
    } catch {
      /* backend still starting */
    }
  };

  useEffect(() => {
    alive.current = true;
    void refreshStatus();
    void getAllSettings().then((s) => alive.current && setSettingsState(s));
    const t = setInterval(refreshStatus, 2500);
    return () => {
      alive.current = false;
      clearInterval(t);
    };
  }, []);

  const update = (key: string, value: any) => {
    setSettingsState((prev) => (prev ? { ...prev, [key]: value } : prev));
    void setSetting(key, value);
  };

  const region: Region = settings?.region ?? { x: 0.03, y: 0.62, w: 0.94, h: 0.36 };
  const setRegion = (part: Partial<Region>) => {
    const next = { ...region, ...part };
    // draw the region over the game while sliding (auto-hides after 2.5s)
    overlayState.showRegionPreview(next);
    update("region", next);
  };

  if (!settings) {
    return (
      <PanelSection title="VN Lookup">
        <PanelSectionRow>Loading…</PanelSectionRow>
      </PanelSection>
    );
  }

  const runtime = status?.runtime;
  const models = status?.models;
  const setupDone = !!runtime?.installed && !!models?.installed;

  return (
    <>
      <LookupSection sentence={status?.last_result?.text ?? null} />
      <PanelSection title="Status">
        <PanelSectionRow>
          <div style={{ fontSize: 12, lineHeight: 1.6 }}>
            <div>
              Texthooker page:{" "}
              <b>http://localhost:{status?.delivery.port ?? 8766}/</b>
            </div>
            <div>
              Readers connected: <b>{status?.delivery.clients ?? "?"}</b>
              {" · "}Anki:{" "}
              <b>{status?.anki_available ? "connected" : "not running"}</b>
            </div>
            <div>
              Controller:{" "}
              <b>{status?.monitor.initialized ? "hooked" : "not found"}</b>
              {" · "}PipeWire:{" "}
              <b>{status?.capture?.pipewire_source ? "ok" : "no source"}</b>
            </div>
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={async () => {
              setBusyMsg("Capturing…");
              const r = await captureAndMine();
              setBusyMsg(r.ok ? "" : r.error ?? "failed");
            }}
          >
            Capture now (test)
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={async () => {
              const r = await testLine();
              setBusyMsg(`Test line sent to ${r.clients} reader(s)`);
            }}
          >
            Send test line to texthooker
          </ButtonItem>
        </PanelSectionRow>
        {busyMsg ? (
          <PanelSectionRow>
            <div style={{ fontSize: 12, color: "#dcae3c" }}>{busyMsg}</div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {!setupDone && (
        <PanelSection title="Setup (one-time)">
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={runtime?.installing || runtime?.installed}
              onClick={() => void installRuntime()}
            >
              {runtime?.installed
                ? "✓ OCR runtime installed"
                : runtime?.installing
                ? `Installing… (${runtime.step})`
                : "1. Install OCR runtime (~400 MB)"}
            </ButtonItem>
          </PanelSectionRow>
          {runtime?.error ? (
            <PanelSectionRow>
              <div style={{ fontSize: 11, color: "#e74c3c" }}>{runtime.error}</div>
            </PanelSectionRow>
          ) : null}
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={models?.downloading || models?.installed}
              onClick={() => void downloadModels()}
            >
              {models?.installed
                ? "✓ OCR models downloaded"
                : models?.downloading
                ? `Downloading… ${Math.round((models.progress ?? 0) * 100)}%`
                : `2. Download OCR models (~${models?.approx_size_mb ?? 22} MB)`}
            </ButtonItem>
          </PanelSectionRow>
          {models?.error ? (
            <PanelSectionRow>
              <div style={{ fontSize: 11, color: "#e74c3c" }}>{models.error}</div>
            </PanelSectionRow>
          ) : null}
        </PanelSection>
      )}

      <PanelSection title="Trigger">
        <PanelSectionRow>
          <DropdownItem
            label="Capture button"
            rgOptions={TRIGGER_OPTIONS}
            selectedOption={settings.trigger_button}
            onChange={(o) => update("trigger_button", o.data)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Hold time (ms)"
            description="How long to hold the button before capture fires"
            value={settings.trigger_hold_ms}
            min={0}
            max={1000}
            step={50}
            showValue
            onChange={(v) => update("trigger_hold_ms", v)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Open lookup after capture"
            description="Pop the Quick Access menu when a line is read"
            checked={!!settings.auto_open_qam}
            onChange={(v) => update("auto_open_qam", v)}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="OCR">
        <PanelSectionRow>
          <DropdownItem
            label="Backend"
            rgOptions={BACKEND_OPTIONS}
            selectedOption={settings.ocr_backend}
            onChange={(o) => update("ocr_backend", o.data)}
          />
        </PanelSectionRow>
        {settings.ocr_backend === "gemini" && (
          <PanelSectionRow>
            <TextField
              label="Gemini API key"
              value={settings.gemini_api_key}
              bIsPassword
              onChange={(e) => update("gemini_api_key", e.target.value)}
            />
          </PanelSectionRow>
        )}
        <PanelSectionRow>
          <ToggleField
            label="Strip speaker name"
            description="Remove 【Name】 / Name「 prefixes before lookup"
            checked={!!settings.strip_speaker_name}
            onChange={(v) => update("strip_speaker_name", v)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Region: left edge %"
            value={Math.round(region.x * 100)}
            min={0} max={80} step={1} showValue
            onChange={(v) => setRegion({ x: v / 100 })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Region: top edge %"
            value={Math.round(region.y * 100)}
            min={0} max={90} step={1} showValue
            onChange={(v) => setRegion({ y: v / 100 })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Region: width %"
            value={Math.round(region.w * 100)}
            min={10} max={100} step={1} showValue
            onChange={(v) => setRegion({ w: v / 100 })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <SliderField
            label="Region: height %"
            value={Math.round(region.h * 100)}
            min={5} max={100} step={1} showValue
            onChange={(v) => setRegion({ h: v / 100 })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Anki">
        <PanelSectionRow>
          <ToggleField
            label="Auto-enrich new cards"
            description="Attach the game screenshot to cards Yomitan creates"
            checked={!!settings.anki_auto_enrich}
            onChange={(v) => update("anki_auto_enrich", v)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <DropdownItem
            label="Card image"
            rgOptions={ANKI_IMAGE_OPTIONS}
            selectedOption={settings.anki_image}
            onChange={(o) => update("anki_image", o.data)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Deck (for created cards)"
            value={settings.anki_deck}
            onChange={(e) => update("anki_deck", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Note type"
            value={settings.anki_note_type}
            onChange={(e) => update("anki_note_type", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Expression field"
            value={settings.anki_expression_field}
            onChange={(e) => update("anki_expression_field", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Reading field (blank = skip)"
            value={settings.anki_reading_field}
            onChange={(e) => update("anki_reading_field", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Glossary field (blank = skip)"
            value={settings.anki_glossary_field}
            onChange={(e) => update("anki_glossary_field", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Picture field name"
            value={settings.anki_picture_field}
            onChange={(e) => update("anki_picture_field", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <TextField
            label="Sentence field name"
            value={settings.anki_sentence_field}
            onChange={(e) => update("anki_sentence_field", e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={async () => {
              const r = await enrichLatestNote();
              setBusyMsg(
                r.ok ? `Attached to note ${r.note_id}` : r.error ?? "failed");
            }}
          >
            Attach last capture to newest card
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
