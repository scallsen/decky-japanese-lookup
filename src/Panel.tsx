import {
  ButtonItem,
  DialogButton,
  Dropdown,
  DropdownItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  TextField,
  ToggleField,
} from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import {
  clearAnkiBuffer,
  downloadModels,
  exportAnkiBuffer,
  getAllSettings,
  getStatus,
  installAnkiExportRuntime,
  installRuntime,
  PluginStatus,
  Region,
  setSetting,
} from "./api";
import { LookupSection } from "./LookupPanel";
import { openRegionEditor } from "./RegionEditor";
import { QrCode } from "./QrCode";

interface CaptureArea {
  region: Region;
  button: string | null;
}

const TRIGGER_OPTIONS = [
  { data: "off", label: "None" },
  { data: "L4", label: "L4" },
  { data: "R4", label: "R4" },
  { data: "L5", label: "L5" },
  { data: "R5", label: "R5" },
];

// shape for newly-added areas — the default area already covers the usual
// bottom-third text box, so a second one probably wants more of the screen
const NEW_AREA_REGION: Region = { x: 0.1, y: 0.08, w: 0.8, h: 0.84 };

// Cheap at-a-glance preview of where a region sits on screen — a grey box
// standing in for the display, with a blue box for the region, positioned
// with the same x/y/w/h-as-percentage math as the visual region editor
// (RegionEditor.tsx), just without the screenshot or drag handling.
const AreaThumbnail: FC<{ region: Region }> = ({ region }) => (
  <div
    style={{
      position: "relative",
      width: "100%",
      aspectRatio: "16 / 9",
      background: "rgba(255,255,255,0.06)",
      border: "1px solid rgba(255,255,255,0.15)",
      borderRadius: 4,
      overflow: "hidden",
      marginBottom: 8,
    }}
  >
    <div
      style={{
        position: "absolute",
        left: `${region.x * 100}%`,
        top: `${region.y * 100}%`,
        width: `${region.w * 100}%`,
        height: `${region.h * 100}%`,
        background: "rgba(79,195,247,0.35)",
        border: "1px solid #4fc3f7",
        boxSizing: "border-box",
      }}
    />
  </div>
);

const BACKEND_OPTIONS = [
  { data: "rapidocr", label: "Local (RapidOCR, offline)" },
  { data: "gemini", label: "Cloud (Gemini Vision)" },
];

export const Panel: FC = () => {
  const [status, setStatus] = useState<PluginStatus | null>(null);
  const [settings, setSettingsState] = useState<Record<string, any> | null>(null);
  const [busyMsg, setBusyMsg] = useState("");
  const [qrUrl, setQrUrl] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const alive = useRef(true);
  const lastLocalEdit = useRef(0);

  useEffect(() => {
    if (!qrUrl) return;
    const t = setTimeout(() => setQrUrl(null), 5 * 60 * 1000);
    return () => clearTimeout(t);
  }, [qrUrl]);

  const handleExport = async () => {
    setBusyMsg("");
    if (!status?.runtime?.anki_installed) {
      await installAnkiExportRuntime();
      setBusyMsg("Installing…");
      return;
    }
    setExporting(true);
    setQrUrl(null);
    try {
      const r = await exportAnkiBuffer();
      if (r.ok && r.url) {
        setQrUrl(r.url);
        setBusyMsg(`Exported ${r.count} card(s) — scan to import`);
      } else {
        setBusyMsg(r.error ?? "export failed");
      }
    } finally {
      setExporting(false);
    }
  };

  const refreshStatus = async () => {
    try {
      const s = await getStatus();
      if (alive.current) setStatus(s);
      // pick up settings changed elsewhere (e.g. the visual region editor
      // modal saves directly) — but never clobber an in-progress slider drag
      if (Date.now() - lastLocalEdit.current > 3000) {
        const fresh = await getAllSettings();
        if (alive.current && Date.now() - lastLocalEdit.current > 3000) {
          setSettingsState(fresh);
        }
      }
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
    lastLocalEdit.current = Date.now();
    setSettingsState((prev) => (prev ? { ...prev, [key]: value } : prev));
    void setSetting(key, value);
  };

  const areas: CaptureArea[] =
    Array.isArray(settings?.capture_areas) && settings.capture_areas.length > 0
      ? settings.capture_areas
      : [{ region: { x: 0.03, y: 0.62, w: 0.94, h: 0.36 }, button: "L5" }];

  const updateAreas = (next: CaptureArea[]) => update("capture_areas", next);

  const setAreaButton = (i: number, button: string) => {
    const next = areas.map((a, idx) => {
      if (idx === i) return { ...a, button: button === "off" ? null : button };
      // a physical button can only trigger one area — clear it elsewhere
      return a.button === button && button !== "off" ? { ...a, button: null } : a;
    });
    updateAreas(next);
  };

  const setAreaRegion = (i: number, region: Region) => {
    updateAreas(areas.map((a, idx) => (idx === i ? { ...a, region } : a)));
  };

  const addArea = () => updateAreas([...areas, { region: NEW_AREA_REGION, button: null }]);

  const deleteArea = (i: number) => updateAreas(areas.filter((_, idx) => idx !== i));

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
      <LookupSection
        sentence={status?.last_result?.text ?? null}
        confidence={status?.last_result?.confidence ?? null}
        ankiEnabled={!!settings.anki_enabled}
      />

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

      <PanelSection title="Capture area">
        {areas.map((area, i) => (
          <div
            key={i}
            style={{
              borderTop: i > 0 ? "1px solid rgba(255,255,255,0.1)" : "none",
              marginTop: i > 0 ? 4 : 0,
              paddingTop: i > 0 ? 4 : 0,
            }}
          >
            <PanelSectionRow>
              <AreaThumbnail region={area.region} />
            </PanelSectionRow>
            <PanelSectionRow>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <DialogButton
                  style={{
                    flex: "0 1 auto",
                    width: "fit-content",
                    whiteSpace: "nowrap",
                  }}
                  onClick={() =>
                    openRegionEditor(
                      "Select the area to capture",
                      area.region,
                      (r) => setAreaRegion(i, r)
                    )
                  }
                >
                  Change area
                </DialogButton>
                <Dropdown
                  rgOptions={TRIGGER_OPTIONS}
                  selectedOption={area.button ?? "off"}
                  onChange={(o) => setAreaButton(i, o.data)}
                />
              </div>
            </PanelSectionRow>
            {i > 0 && (
              <PanelSectionRow>
                <ButtonItem layout="below" onClick={() => deleteArea(i)}>
                  Delete
                </ButtonItem>
              </PanelSectionRow>
            )}
          </div>
        ))}
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={addArea}>
            Add capture area
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Anki">
        <PanelSectionRow>
          <ToggleField
            label="Enable Anki integration"
            description="Buffer +Anki taps, then export them as a .apkg you scan onto your phone"
            checked={!!settings.anki_enabled}
            onChange={(v) => update("anki_enabled", v)}
          />
        </PanelSectionRow>
        {settings.anki_enabled && (
          <>
            <PanelSectionRow>
              <TextField
                label="Deck (for exported cards)"
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
              <div style={{ fontSize: 11, opacity: 0.6 }}>
                Exporting creates/updates a plugin-owned note type with this
                name — it won't merge into an existing note type of the same
                name already in your collection.
              </div>
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
                label="Sentence field name"
                value={settings.anki_sentence_field}
                onChange={(e) => update("anki_sentence_field", e.target.value)}
              />
            </PanelSectionRow>

            <PanelSectionRow>
              <div style={{ fontSize: 12 }}>
                Buffered cards: <b>{status?.anki_buffered ?? 0}</b>
              </div>
            </PanelSectionRow>

            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={
                  (status?.anki_buffered ?? 0) === 0 ||
                  !!status?.runtime?.installing ||
                  exporting
                }
                onClick={handleExport}
              >
                {!status?.runtime?.anki_installed
                  ? status?.runtime?.installing
                    ? `Installing… (${status.runtime.step})`
                    : "Install Anki export runtime (~5 MB)"
                  : exporting
                  ? "Exporting…"
                  : "Export via QR"}
              </ButtonItem>
            </PanelSectionRow>
            {status?.runtime?.error ? (
              <PanelSectionRow>
                <div style={{ fontSize: 11, color: "#e74c3c" }}>
                  {status.runtime.error}
                </div>
              </PanelSectionRow>
            ) : null}

            {qrUrl ? (
              <>
                <PanelSectionRow>
                  <div
                    style={{ display: "flex", justifyContent: "center", padding: "8px 0" }}
                  >
                    <QrCode value={qrUrl} />
                  </div>
                </PanelSectionRow>
                <PanelSectionRow>
                  <div style={{ fontSize: 11, wordBreak: "break-all", opacity: 0.7 }}>
                    {qrUrl}
                  </div>
                </PanelSectionRow>
                <PanelSectionRow>
                  <div style={{ fontSize: 11, opacity: 0.7 }}>
                    Scan, then "Open in Anki" on your phone. Link expires in a
                    few minutes.
                  </div>
                </PanelSectionRow>
              </>
            ) : null}

            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={(status?.anki_buffered ?? 0) === 0}
                onClick={async () => {
                  await clearAnkiBuffer();
                  setQrUrl(null);
                  setBusyMsg("Buffer cleared");
                }}
              >
                Clear buffer
              </ButtonItem>
            </PanelSectionRow>

            {busyMsg ? (
              <PanelSectionRow>
                <div style={{ fontSize: 12, color: "#dcae3c" }}>{busyMsg}</div>
              </PanelSectionRow>
            ) : null}
          </>
        )}
      </PanelSection>

      <PanelSection title="Advanced setting">
        <PanelSectionRow>
          <DropdownItem
            label="OCR"
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
            label="Add capture delay"
            description="Add a small delay when activating the capture buttons"
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
            description="Automatically open the quick access menu after capture"
            checked={!!settings.auto_open_qam}
            onChange={(v) => update("auto_open_qam", v)}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Status">
        <PanelSectionRow>
          <div style={{ fontSize: 12, lineHeight: 1.6 }}>
            <div>
              Texthooker page:{" "}
              <b>http://localhost:{status?.delivery.port ?? 8766}/</b>
            </div>
            <div>
              Readers connected: <b>{status?.delivery.clients ?? "?"}</b>
            </div>
            <div>
              Controller:{" "}
              <b>{status?.monitor.initialized ? "hooked" : "not found"}</b>
              {" · "}PipeWire:{" "}
              <b>{status?.capture?.pipewire_source ? "ok" : "no source"}</b>
            </div>
          </div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
