"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createGatewayClient } from "./lib/gateway.mjs";
import Problem from "./components/problem";
import Datasets from "./components/datasets";

const FIRST_WAIT_MS = 5000;
const LONGEST_WAIT_MS = 60000;


export default function Dashboard({ gatewayUrl, devToken }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const [health, setHealth] = useState("Checking connection");
  const [projects, setProjects] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [problem, setProblem] = useState(null);
  const [createProblem, setCreateProblem] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [alerts, setAlerts] = useState([]);
  const [alertProblem, setAlertProblem] = useState(null);
  // Keep the same key when retrying an unchanged form after a lost response.
  const submission = useRef(null);
  const savingRef = useRef(false);
  const selectedProject = projects.find((project) => project.project_id === selectedId);

  useEffect(() => {
    const controller = new AbortController();
    api.request("/health", { signal: controller.signal })
      .then(() => setHealth("Connected"))
      .catch((error) => { if (error.name !== "AbortError") setHealth("Unavailable"); });
    return () => controller.abort();
  }, [api, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setProblem(null);
    api.listProjects(controller.signal).then((body) => {
      if (!Array.isArray(body.items)) throw new Error("The project list could not be read.");
      setProjects(body.items);
      setSelectedId((current) => body.items.some((p) => p.project_id === current) ? current : "");
    }).catch((error) => {
      if (error.name !== "AbortError") setProblem(error);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, refresh]);

  // Existing alert feed retained for Adel to extend; reset its cursor per project.
  useEffect(() => {
    setAlerts([]);
    setAlertProblem(null);
    if (!selectedId) return;
    const controller = new AbortController();
    let lastEventId = null;
    let wait = FIRST_WAIT_MS;
    let timer;
    const seen = new Set();
    async function poll() {
      const query = new URLSearchParams({ project_id: selectedId });
      if (lastEventId) query.set("after", lastEventId);
      try {
        const body = await api.request(`/api/v1/jobs/events?${query}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        const fresh = body.items.filter((event) => !seen.has(event.event_id));
        fresh.forEach((event) => seen.add(event.event_id));
        setAlerts((old) => [...old, ...fresh].slice(-20));
        if (body.last_event_id) lastEventId = body.last_event_id;
        setAlertProblem(null);
        wait = FIRST_WAIT_MS;
      } catch (error) {
        if (controller.signal.aborted) return;
        setAlertProblem(error);
        wait = Math.min(wait * 2, LONGEST_WAIT_MS);
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, wait);
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [api, selectedId]);

  async function createProject(event) {
    event.preventDefault();
    if (savingRef.current) return;
    const project = { name: name.trim(), description: description.trim() || null };
    if (!project.name) {
      setCreateProblem(new Error("Enter a project name."));
      return;
    }
    const fingerprint = JSON.stringify(project);
    if (submission.current?.fingerprint !== fingerprint) {
      submission.current = { fingerprint, key: crypto.randomUUID() };
    }
    savingRef.current = true;
    setSaving(true);
    setCreateProblem(null);
    setConfirmation("");
    try {
      const created = await api.createProject(project, submission.current.key);
      setProjects((old) => [...old.filter((p) => p.project_id !== created.project_id), created]);
      setSelectedId(created.project_id);
      setName("");
      setDescription("");
      submission.current = null;
      setConfirmation(`Created ${created.name}. Your project is selected.`);
    } catch (error) {
      setCreateProblem(error);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/">CloudTrain<span>ML workspace</span></a>
      <nav aria-label="Main navigation"><a href="#projects" aria-current="page">Projects</a><a href="#datasets">Datasets</a></nav>
      <p className="sidebar-note">Organize your data, training and models in one workspace.</p>
    </aside>
    <main id="projects">
      <header className="page-header"><div><p className="eyebrow">YOUR WORKSPACE</p><h1>Projects</h1>
        <p>Create a project to keep your datasets and training runs together.</p></div>
        <span className={`connection ${health === "Connected" ? "connected" : ""}`} role="status">{health}</span>
      </header>
      {devToken && <p className="notice">Local development session. Real sign-in will be integrated with the team’s identity provider.</p>}
      {!devToken && <p className="notice">This workspace requires a signed-in session. Sign-in integration is pending.</p>}
      <div className="workspace-grid">
        <section className="panel" aria-labelledby="project-list-title">
          <div className="section-heading"><h2 id="project-list-title">Your projects</h2>
            <button className="secondary" disabled={loading || saving} onClick={() => setRefresh((value) => value + 1)}>Refresh</button></div>
          <Problem error={problem} />
          {loading ? <p role="status">Loading projects…</p> : problem ? <p>Refresh to try loading your projects again.</p> : projects.length === 0 ?
            <div className="empty"><h3>A fresh start</h3><p>Create your first project using the form.</p></div> :
            <ul className="project-list">{projects.map((project) => <li key={project.project_id}>
              <button className={`project-card ${selectedId === project.project_id ? "selected" : ""}`} aria-pressed={selectedId === project.project_id}
                onClick={() => setSelectedId(project.project_id)}>
                <strong>{project.name}</strong><span>{project.description || "No description"}</span><small>{project.project_id}</small>
              </button>
            </li>)}</ul>}
        </section>
        <section className="panel" aria-labelledby="create-title">
          <h2 id="create-title">Create a project</h2><p className="muted">Give your next experiment a home.</p>
          <form onSubmit={createProject}>
            <fieldset disabled={saving || loading}><label htmlFor="project-name">Project name <span aria-hidden="true">*</span></label>
              <input id="project-name" required maxLength={100} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Image classification" />
              <label htmlFor="project-description">Description <span className="muted">(optional)</span></label>
              <textarea id="project-description" maxLength={1000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="What will you train or explore?" />
              <button type="submit">{saving ? "Creating…" : "Create project"}</button>
            </fieldset>
            <Problem error={createProblem} /><p className="success" role="status">{confirmation}</p>
          </form>
        </section>
      </div>
      {selectedProject && <section className="panel selection" aria-labelledby="selected-title">
        <p className="eyebrow">SELECTED PROJECT</p><h2 id="selected-title">{selectedProject.name}</h2>
        <p>{selectedProject.description || "No description provided."}</p><small>{selectedProject.project_id}</small>
      </section>}
      <Datasets key={selectedId} api={api} project={selectedProject} />
      <section className="panel" aria-labelledby="alerts-title"><h2 id="alerts-title">Job alerts</h2>
        <Problem error={alertProblem} />
        {!selectedId ? <p className="muted">Select a project to view its job events.</p> : alerts.length === 0 ? <p className="muted">No job events yet for this project.</p> :
          <ul className="events">{alerts.map((event) => <li key={event.event_id}><strong>{event.job_id}</strong> · {event.event_type}<small>{event.occurred_at}{event.data?.reason ? ` · ${event.data.reason}` : ""}</small></li>)}</ul>}
      </section>
    </main>
  </div>;
}
