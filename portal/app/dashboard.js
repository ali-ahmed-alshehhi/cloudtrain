"use client";
// Runs in the browser. Shows the gateway's health, the user's projects and the job alert feed.

import { useEffect, useState } from "react";

const FIRST_WAIT_MS = 5000; // the alert feed is asked every 5 seconds...
const LONGEST_WAIT_MS = 60000; // ...and waits longer (up to 60 s) while the gateway does not answer

export default function Dashboard({ gatewayUrl, devToken }) {
  const [health, setHealth] = useState("checking...");
  const [projects, setProjects] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [problem, setProblem] = useState("");

  const headers = devToken ? { Authorization: `Bearer ${devToken}` } : {};

  useEffect(() => {
    fetch(`${gatewayUrl}/health`)
      .then((answer) => answer.json())
      .then((body) => setHealth(body.status))
      .catch(() => setHealth("not reachable"));

    fetch(`${gatewayUrl}/api/v1/projects`, { headers })
      .then((answer) => answer.json())
      .then((body) => (body.items ? setProjects(body.items) : setProblem(body.error?.message)))
      .catch(() => setProblem("Could not load projects"));
  }, [gatewayUrl]);

  // The alert feed: ask for events newer than the last one we saw; back off when there is trouble.
  useEffect(() => {
    let lastEventId = null;
    let wait = FIRST_WAIT_MS;
    let timer;
    let stopped = false;

    async function poll() {
      const after = lastEventId ? `?after=${lastEventId}` : "";
      try {
        const answer = await fetch(`${gatewayUrl}/api/v1/jobs/events${after}`, { headers });
        if (!answer.ok) throw new Error(`status ${answer.status}`);
        const body = await answer.json();
        if (body.items.length > 0) setAlerts((old) => [...old, ...body.items].slice(-20));
        lastEventId = body.last_event_id;
        wait = FIRST_WAIT_MS;
      } catch {
        wait = Math.min(wait * 2, LONGEST_WAIT_MS);
      }
      if (!stopped) timer = setTimeout(poll, wait);
    }

    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [gatewayUrl]);

  return (
    <main>
      <h1>CloudTrain</h1>
      <p style={{ color: "#a15c00" }}>Stand-in portal — Hilal + Adel replace this page.</p>

      <h2>Gateway</h2>
      <p>
        <code>{gatewayUrl}/health</code>: <strong>{health}</strong>
      </p>

      <h2>Projects</h2>
      {problem && <p style={{ color: "crimson" }}>{problem}</p>}
      {projects.length === 0 && !problem && <p>No projects yet.</p>}
      <ul>
        {projects.map((project) => (
          <li key={project.project_id}>
            <strong>{project.project_id}</strong> — {project.name}
          </li>
        ))}
      </ul>

      <h2>Job alerts</h2>
      {alerts.length === 0 && <p>No job events yet.</p>}
      <ul>
        {alerts.map((event) => (
          <li key={event.event_id}>
            {event.occurred_at} · <strong>{event.job_id}</strong> · {event.event_type}
            {event.data?.reason ? ` (${event.data.reason})` : ""}
          </li>
        ))}
      </ul>
    </main>
  );
}
