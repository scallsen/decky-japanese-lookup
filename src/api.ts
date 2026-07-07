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
  note_id?: number;
  picture?: boolean;
  sentence?: boolean;
}

export interface PluginStatus {
  monitor: { running: boolean; initialized: boolean; device_path: string | null };
  runtime: { installed: boolean; installing: boolean; step: string; error: string | null };
  models: { installed: boolean; downloading: boolean; progress: number; error: string | null; approx_size_mb: number };
  capture: { pipewire_source?: boolean; pngenc?: boolean; dims?: [number, number] | null; error?: string };
  delivery: { port: number; clients: number };
  anki_available: boolean;
  busy: boolean;
}

export interface Region { x: number; y: number; w: number; h: number }

export const captureAndMine = callable<[], { ok: boolean; error?: string }>("capture_and_mine");
export const getButtonState = callable<[], { success: boolean; buttons: string[] }>("get_button_state");
export const getStatus = callable<[], PluginStatus>("get_status");
export const getAllSettings = callable<[], Record<string, any>>("get_all_settings");
export const setSetting = callable<[key: string, value: any], { ok: boolean }>("set_setting");
export const installRuntime = callable<[], { started: boolean }>("install_runtime");
export const downloadModels = callable<[], { started: boolean }>("download_models");
export const testLine = callable<[], { ok: boolean; clients: number }>("test_line");
export const enrichLatestNote = callable<[], { ok: boolean; error?: string; note_id?: number }>("enrich_latest_note");
