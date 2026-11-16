// Colours for the status tones in lib/alerts/describe.mjs. Text never relies on colour alone:
// every badge and alert also says the status in words.
export const TONE_STYLES = {
  waiting: { background: "#eef2f7", color: "#334155", border: "#cbd5e1" },
  active: { background: "#e0efff", color: "#0b4a8b", border: "#93c5fd" },
  good: { background: "#e3f6e8", color: "#14532d", border: "#86efac" },
  bad: { background: "#fde8e8", color: "#7f1d1d", border: "#fca5a5" },
  muted: { background: "#f3f4f6", color: "#4b5563", border: "#d1d5db" },
  unknown: { background: "#fff7e6", color: "#7c4a03", border: "#fcd34d" },
};

export const MESSAGE_STYLES = {
  info: { color: "#475569" },
  warning: { color: "#7c4a03" },
  error: { color: "#991b1b" },
};
