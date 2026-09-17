// A finished scan asks the Lookup section to focus the first word of its
// sentence. Kept outside React because the section may only mount once the
// QAM has opened, after the scan's "done" event already fired.

let pendingText: string | null = null;
const subscribers = new Set<() => void>();

export const requestFirstWordFocus = (text: string) => {
  pendingText = text;
  subscribers.forEach((notify) => notify());
};

// Claims the request if it's for this sentence; stale words leave it pending.
export const takeFirstWordFocus = (text: string | null): boolean => {
  if (text === null || pendingText !== text) return false;
  pendingText = null;
  return true;
};

export const onFirstWordFocusRequest = (notify: () => void) => {
  subscribers.add(notify);
  return () => {
    subscribers.delete(notify);
  };
};
