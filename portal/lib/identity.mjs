// Labels for "whose data is this?" (owner: Adel).
//
// A component that loads data for one job/project must never show it under another one. We label
// every stored answer with the identity it was loaded for, and only show it while that identity is
// still the current one. Plain JavaScript, tested with `node --test`.

const ids = new WeakMap();
let next = 1;

/** A stable number for an object or function (an API client, a fetch function); "none" for nothing. */
export function objectIdentity(value) {
  if (!value || (typeof value !== "object" && typeof value !== "function")) return "none";
  if (!ids.has(value)) ids.set(value, next++);
  return `#${ids.get(value)}`;
}

/** One string from several parts; objects and functions count by identity, not by content. */
export function identityOf(...parts) {
  return parts
    .map((part) => (part && (typeof part === "object" || typeof part === "function") ? objectIdentity(part) : String(part ?? "")))
    .join("|");
}

/** Store a value together with the identity it belongs to. */
export function labelled(identity, value) {
  return { identity, value };
}

/** The stored value only if it belongs to the current identity; otherwise null (show "loading"). */
export function valueFor(stored, identity) {
  return stored && stored.identity === identity ? stored.value : null;
}
