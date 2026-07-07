import { callable } from "@decky/api";

export interface VnlEvent {
  stage: "capturing" | "ocr" | "done" | "error" | "anki";
  message?: string;
  text?: string;
  raw?: string;
  confidence?: number;
  warning?: string | null;
  clients?: number;
  copy_to_clipboard?: boolean;
  auto_open_qam?: boolean;
  note_id?: number;
  picture?: boolean;
  sentence?: boolean;
}

export interface PluginStatus {
  monitor: { running: boolean; initialized: boolean; device_path: string | null };
  runtime: { installed: boolean; lookup_installed: boolean; installing: boolean; step: string; error: string | null };
  models: { installed: boolean; downloading: boolean; progress: number; error: string | null; approx_size_mb: number };
  capture: { pipewire_source?: boolean; pngenc?: boolean; dims?: [number, number] | null; error?: string };
  delivery: { port: number; clients: number };
  anki_available: boolean;
  busy: boolean;
  last_result?: { text: string; raw: string; confidence: number } | null;
}

export interface Token {
  surface: string;
  dict_form: string;
  lemma: string;
  reading: string;
  pos: string;
  selectable: boolean;
}

export interface DictEntry {
  expression: string;
  reading: string;
  matched: string;
  glosses: string;
  tags: string;
  dicts: string[];
  frequency: string | null;
  pitch: number[] | null;
}

export interface LookupStatus {
  runtime_installed: boolean;
  runtime: { installing: boolean; step: string; error: string | null };
  dictionary: {
    dictionaries: string[];
    term_count: number;
    pending_zips: string[];
    importing: boolean;
    progress: number;
    step: string;
    error: string | null;
    ready: boolean;
  };
}

export interface Region { x: number; y: number; w: number; h: number }

export const captureAndMine = callable<[button?: string], { ok: boolean; error?: string }>("capture_and_mine");
export const getButtonState = callable<[], { success: boolean; buttons: string[] }>("get_button_state");
export const getStatus = callable<[], PluginStatus>("get_status");
export const getAllSettings = callable<[], Record<string, any>>("get_all_settings");
export const setSetting = callable<[key: string, value: any], { ok: boolean }>("set_setting");
export const installRuntime = callable<[], { started: boolean }>("install_runtime");
export const downloadModels = callable<[], { started: boolean }>("download_models");
export const testLine = callable<[], { ok: boolean; clients: number }>("test_line");
export const enrichLatestNote = callable<[], { ok: boolean; error?: string; note_id?: number }>("enrich_latest_note");

// visual region editor
export const getEditorFrame = callable<[], { ok: boolean; image?: string; error?: string }>("get_editor_frame");
export const captureEditorFrame = callable<[], { ok: boolean; image?: string; error?: string }>("capture_editor_frame");
export const detectRegion = callable<[], { ok: boolean; region?: Region; image?: string; error?: string }>("detect_region");

// native lookup
export const tokenizeLine = callable<[text: string], { ok: boolean; tokens?: Token[]; error?: string }>("tokenize_line");
export const lookupWord = callable<[queries: string[]], { ok: boolean; entries: DictEntry[] }>("lookup_word");
export const lookupSelection = callable<[text: string], { ok: boolean; entries: DictEntry[] }>("lookup_selection");
export const getLookupStatus = callable<[], LookupStatus>("get_lookup_status");
export const installLookupRuntime = callable<[], { started: boolean }>("install_lookup_runtime");
export const importDictionaries = callable<[downloadJitendex: boolean], { started: boolean }>("import_dictionaries");
export const createAnkiCard = callable<
  [expression: string, reading: string, glosses: string, sentence: string],
  { ok: boolean; note_id?: number; error?: string }
>("create_anki_card");
