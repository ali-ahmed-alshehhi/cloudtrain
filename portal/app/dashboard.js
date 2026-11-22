"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createGatewayClient } from "./lib/gateway.mjs";
import Problem from "./components/problem";
import Datasets from "./components/datasets";
import ProjectAlerts from "./components/project-alerts";



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
  const [uploading, setUploading] = useState(false);
  const [confirmation, setConfirmation] = useState("");
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

  async function createProject(event) {
    event.preventDefault();
    if (savingRef.current || uploading) return;
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
      <a className="brand" href="/"><img src="/brand/cloudtrain-logo-dark.png" alt="CloudTrain" width="168" height="69" /><span>ML workspace</span></a>
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
            <button className="secondary" disabled={loading || saving || uploading} onClick={() => setRefresh((value) => value + 1)}>Refresh</button></div>
          <Problem error={problem} />
          {loading ? <p role="status">Loading projects…</p> : problem ? <p>Refresh to try loading your projects again.</p> : projects.length === 0 ?
            <div className="empty"><h3>A fresh start</h3><p>Create your first project using the form.</p></div> :
            <ul className="project-list">{projects.map((project) => <li key={project.project_id}>
              <button className={`project-card ${selectedId === project.project_id ? "selected" : ""}`} aria-pressed={selectedId === project.project_id}
                disabled={saving || uploading} onClick={() => setSelectedId(project.project_id)}>
                <strong>{project.name}</strong><span>{project.description || "No description"}</span><small>{project.project_id}</small>
              </button>
            </li>)}</ul>}
        </section>
        <section className="panel" aria-labelledby="create-title">
          <h2 id="create-title">Create a project</h2><p className="muted">Give your next experiment a home.</p>
          <form onSubmit={createProject}>
            <fieldset disabled={saving || loading || uploading}><label htmlFor="project-name">Project name <span aria-hidden="true">*</span></label>
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
      {uploading && <p role="status">Upload in progress. Project selection will be available when it finishes.</p>}
      <Datasets key={selectedId} api={api} project={selectedProject} onUploadingChange={setUploading} />
      <section className="panel">
        {selectedId ? <ProjectAlerts key={selectedId} api={api} projectId={selectedId} /> : <><h2>Job alerts</h2><p className="muted">Select a project to view its job events.</p></>}
      </section>
    </main>
  </div>;
}
