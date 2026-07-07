// Clipboard copy inside Steam's CEF (the decky-clipboard technique).
// Steam's UI is an X client on gamescope's base XWayland server, and
// gamescope mirrors UTF-8 clipboard contents to all its XWayland servers
// (SteamOS >= 3.7.14) — so text copied here reaches a Firefox window
// running as a non-Steam app, where Yomitan's clipboard monitor sees it.
// execCommand is used deliberately: it works without focus/user-gesture
// constraints in gaming mode where navigator.clipboard can fail silently.

export function copyToClipboard(text: string): boolean {
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
