// Job alert feed (owner: Adel, Student 10 split 2).
//
// Polls the gateway's alert feed, GET /api/v1/jobs/events (contracts/openapi/job-service.yaml,
// operation listRecentEvents), and keeps the list of events the portal shows as alerts.
//
// Plain JavaScript with no React, so it can be tested with `node --test`. The React components
// that show alerts and live status use it; they live next to it and are wired into Hilal's pages.
//
// What it handles:
// - the cursor: `after` = the last event_id seen; the answer's `last_event_id` is the next cursor
// - catching up: the feed is oldest first and a page holds at most `limit` events, so a full page
//   is followed at once by the next page until a short page arrives
// - duplicate events (the same event_id is never shown twice)
// - the project filter: one feed per project; a new project means a new feed (see stop())
// - loading, empty, 401, 403 and "service unavailable" states
// - waiting 5 seconds between polls, doubling up to 60 seconds while the gateway has trouble

export const POLL_MS = 5000; // the contract asks for 5-10 seconds
export const MAX_BACKOFF_MS = 60000;
export const PAGE_LIMIT = 200; // the contract's maximum
export const MAX_PAGES_PER_POLL = 20; // never loop forever while catching up
export const KEEP_EVENTS = 100; // events kept for the screen

// The states a screen can show.
export const PHASES = Object.freeze({
  LOADING: "loading", // first answer not in yet
  READY: "ready", // answered (events may be empty)
  UNAUTHORIZED: "unauthorized", // 401: not logged in; polling stops
  FORBIDDEN: "forbidden", // 403: not a member of this project; polling stops
  UNAVAILABLE: "unavailable", // 503 or no network; keeps trying with back-off
  ERROR: "error", // any other failure; keeps trying with back-off
});

/**
 * Create one alert feed.
 *
 * @param {object} options
 * @param {(query: {after: string|null, project_id: string|null, limit: number}) =>
 *         Promise<{status: number, body: any}>} options.fetchEvents
 *        Calls GET /api/v1/jobs/events through the gateway. Never throws for an HTTP error:
 *        returns its status and parsed body. May throw (or reject) when the network is down.
 * @param {string|null} [options.projectId] Only this project's events (null = all the user's projects).
 * @param {(state: object) => void} options.onChange Called with a fresh state after every change.
 * @param {(fn: Function, ms: number) => any} [options.setTimer]  Defaults to setTimeout (tests pass a fake).
 * @param {(handle: any) => void} [options.clearTimer]           Defaults to clearTimeout.
 */
export function createAlertFeed({
  fetchEvents,
  projectId = null,
  onChange,
  setTimer = setTimeout,
  clearTimer = clearTimeout,
}) {
  const seen = new Set();
  let cursor = null;
  let wait = POLL_MS;
  let timer = null;
  let stopped = false;
  let state = {
    phase: PHASES.LOADING,
    projectId,
    events: [], // oldest first, at most KEEP_EVENTS
    newEvents: [], // events that arrived in the latest poll after the first one (the "alerts")
    lastEventId: null,
    nextPollMs: null,
    error: null, // { code, message, request_id } from the shared error format, when there is one
  };

  function publish(changes) {
    state = { ...state, ...changes };
    onChange(state);
  }

  // One poll: read pages until a short page, then return the events not seen before.
  async function readNewEvents() {
    const fresh = [];
    for (let page = 0; page < MAX_PAGES_PER_POLL; page += 1) {
      const answer = await fetchEvents({ after: cursor, project_id: projectId, limit: PAGE_LIMIT });
      if (stopped) return { stoppedEarly: true };
      if (answer.status !== 200) return { failed: answer };

      const items = Array.isArray(answer.body?.items) ? answer.body.items : [];
      for (const event of items) {
        if (!event || seen.has(event.event_id)) continue; // duplicate
        if (projectId && event.project_id !== projectId) continue; // not this project
        seen.add(event.event_id);
        fresh.push(event);
      }
      // last_event_id is null when the feed is empty: keep the cursor we had.
      if (answer.body?.last_event_id) cursor = answer.body.last_event_id;
      if (items.length < PAGE_LIMIT) break;
    }
    return { fresh };
  }

  function failureState(answer) {
    const error = answer?.body?.error ?? null;
    if (answer?.status === 401) return { phase: PHASES.UNAUTHORIZED, error, retry: false };
    if (answer?.status === 403) return { phase: PHASES.FORBIDDEN, error, retry: false };
    if (!answer || answer.status === 503 || answer.status === 502 || answer.status === 504) {
      return { phase: PHASES.UNAVAILABLE, error, retry: true };
    }
    return { phase: PHASES.ERROR, error, retry: true };
  }

  async function poll() {
    timer = null;
    let result;
    try {
      result = await readNewEvents();
    } catch {
      result = { failed: null }; // network down: no answer at all
    }
    if (stopped || result.stoppedEarly) return;

    if (result.failed !== undefined) {
      const { phase, error, retry } = failureState(result.failed);
      if (!retry) {
        publish({ phase, error, newEvents: [], nextPollMs: null });
        return; // logging in again or joining the project needs the user; start a new feed then
      }
      wait = Math.min(wait * 2, MAX_BACKOFF_MS);
      publish({ phase, error, newEvents: [], nextPollMs: wait });
    } else {
      const firstAnswer = state.phase === PHASES.LOADING;
      wait = POLL_MS;
      publish({
        phase: PHASES.READY,
        error: null,
        events: [...state.events, ...result.fresh].slice(-KEEP_EVENTS),
        // The history loaded on the first answer is not shown as new alerts.
        newEvents: firstAnswer ? [] : result.fresh,
        lastEventId: cursor,
        nextPollMs: wait,
      });
    }
    timer = setTimer(poll, wait);
  }

  return {
    start() {
      onChange(state);
      poll();
    },
    /** Stop polling. Answers still on their way are ignored. */
    stop() {
      stopped = true;
      if (timer !== null) clearTimer(timer);
      timer = null;
    },
    getState: () => state,
  };
}

/**
 * The feed state to show for the current project and connection, or null ("loading") when the stored
 * state belongs to another project or another fetchEvents (for example the previous project, just
 * after switching, before the new feed has answered). `stored` is { projectId, fetchEvents, state }.
 */
export function stateForFeed(stored, projectId, fetchEvents) {
  if (!stored) return null;
  if (stored.projectId !== (projectId ?? null) || stored.fetchEvents !== fetchEvents) return null;
  return stored.state;
}

/** Builds the query string for GET /api/v1/jobs/events from the feed's query. */
export function eventsQueryString({ after, project_id, limit }) {
  const params = new URLSearchParams();
  if (after) params.set("after", after);
  if (project_id) params.set("project_id", project_id);
  if (limit) params.set("limit", String(limit));
  const text = params.toString();
  return text ? `?${text}` : "";
}
