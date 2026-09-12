import {
  ButtonItem,
  DialogButton,
  Dropdown,
  Field,
  PanelSection,
  PanelSectionRow,
  Router,
  TextField,
  ToggleField,
} from "@decky/ui";
import { FC, useEffect, useRef, useState } from "react";
import { FaGamepad } from "react-icons/fa";
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
  UNKNOWN_APP_KEY,
} from "./api";
import { LookupSection } from "./LookupPanel";
import { openRegionEditor } from "./RegionEditor";
import { QrCode } from "./QrCode";

interface CaptureArea {
  region: Region;
  button: string | null;
}

interface CaptureProfile {
  display_name: string;
  areas: CaptureArea[];
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

// Steam caches per-app icons locally (works offline in gaming mode) and
// exposes them via these undocumented store globals — not in @decky/ui's
// types, so read them off `window` directly.
const getAppIconUrl = (appid?: string | null): string | null => {
  if (!appid) return null;
  try {
    const w = window as any;
    const overview = w.appStore?.GetAppOverviewByAppID?.(Number(appid));
    return (overview && w.appStore?.GetIconURLForApp?.(overview)) || null;
  } catch {
    return null;
  }
};

// Small square game icon for the capture-area header; falls back to a
// generic gamepad glyph when Steam has no cached icon for the appid (or
// there's no appid at all, i.e. the "Default" profile).
const AppThumbnail: FC<{ appid?: string | null; size?: number }> = ({ appid, size = 32 }) => {
  const url = getAppIconUrl(appid);
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: 6,
        overflow: "hidden",
        flexShrink: 0,
        background: "rgba(255,255,255,0.08)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {url ? (
        <img
          src={url}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      ) : (
        <FaGamepad size={size * 0.55} style={{ opacity: 0.5 }} />
      )}
    </div>
  );
};

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

  const defaultAreas: CaptureArea[] =
    Array.isArray(settings?.capture_areas) && settings.capture_areas.length > 0
      ? settings.capture_areas
      : [{ region: { x: 0.03, y: 0.62, w: 0.94, h: 0.36 }, button: "L5" }];

  const profiles: Record<string, CaptureProfile> = settings?.capture_profiles ?? {};
  const runningApp = Router.MainRunningApp;
  // no appid (no game running, or Steam can't report one) shares one
  // generic bucket — there's no per-game identity to key a profile on
  const editingKey = runningApp?.appid || UNKNOWN_APP_KEY;
  const editingProfile = profiles[editingKey];
  const hasCustomProfile = !!editingProfile?.areas?.length;
  const areas: CaptureArea[] = hasCustomProfile ? editingProfile.areas : defaultAreas;

  // editing with no saved profile yet writes one on the first change,
  // seeded from whatever Default showed — that's the "automatic save"
  const updateAreas = (next: CaptureArea[]) => {
    update("capture_profiles", {
      ...profiles,
      [editingKey]: {
        display_name: runningApp?.display_name ?? "Unknown game",
        areas: next,
      },
    });
  };

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
        <PanelSectionRow>
          <div
            style={{
              display: "flex",
              gap: 10,
              alignItems: "center",
              padding: 6,
              borderRadius: 4,
              background: "rgba(255,255,255,0.06)",
              border: "1px solid rgba(255,255,255,0.1)",
              marginBottom: 8,
            }}
          >
            <AppThumbnail appid={runningApp?.appid} />
            <div style={{ fontSize: 13, fontWeight: 600 }}>
              {runningApp ? runningApp.display_name : "Game not detected"}
            </div>
          </div>
        </PanelSectionRow>
        {areas.map((area, i) => (
          <div
            key={i}
            style={{
              borderTop: i > 0 ? "1px solid rgba(255,255,255,0.1)" : "none",
              // the previous area's "Delete" button (shown once i > 1) carries
              // its own bottom padding, so it needs no extra margin on top of
              // that to match the gap above the first divider (after i === 1,
              // which follows a plain row with no built-in padding)
              marginTop: i > 1 ? 0 : i === 1 ? 12 : 0,
              paddingTop: i > 0 ? 12 : 0,
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
                <ButtonItem
                  layout="below"
                  bottomSeparator="none"
                  onClick={() => deleteArea(i)}
                >
                  Delete
                </ButtonItem>
              </PanelSectionRow>
            )}
          </div>
        ))}
        <div
          style={{
            borderTop: "1px solid rgba(255,255,255,0.1)",
            // matches the area-to-area divider spacing: no extra margin
            // above when the last area's own "Delete" button (which has its
            // own bottom padding) precedes it, otherwise the full margin.
            // No paddingTop below the line either — "Add capture area" is a
            // ButtonItem, which (like Delete) already carries its own top
            // padding.
            marginTop: areas.length > 1 ? 0 : 12,
          }}
        >
          <PanelSectionRow>
            <ButtonItem layout="below" bottomSeparator="none" onClick={addArea}>
              Add capture area
            </ButtonItem>
          </PanelSectionRow>
        </div>
      </PanelSection>

      <PanelSection title="Anki">
        <PanelSectionRow>
          <ToggleField
            label="Enable Anki integration"
            description="Buffer +Anki taps, then export them as a .apkg you scan onto your phone"
            checked={!!settings.anki_enabled}
            onChange={(v) => update("anki_enabled", v)}
            bottomSeparator={settings.anki_enabled ? "standard" : "none"}
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
              <Field childrenLayout="below" bottomSeparator="standard">
                <TextField
                  label="Sentence field name"
                  value={settings.anki_sentence_field}
                  onChange={(e) => update("anki_sentence_field", e.target.value)}
                />
              </Field>
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

      <PanelSection title="Advanced settings">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            bottomSeparator="none"
            onClick={() => update("capture_profiles", {})}
          >
            Delete all capture areas
          </ButtonItem>
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

      <PanelSection title="About / sources">
        <PanelSectionRow>
          <div style={{ fontSize: 10, opacity: 0.6, lineHeight: 1.5 }}>
            VN Lookup is GPL-3.0-or-later; capture, controller-hook, and
            overlay code are ported from Decky-Translator (cat-in-a-box).
            The built-in dictionary downloads Jitendex (jitendex.org, CC
            BY-SA 4.0), built from JMdict/EDICT by the Electronic Dictionary
            Research and Development Group (edrdg.org) and Tatoeba example
            sentences (CC BY 2.0 FR). Full credits and license in the
            project README/LICENSE on GitHub.
          </div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
