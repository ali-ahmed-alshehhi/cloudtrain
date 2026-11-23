"use client";
// The frame of the comparison and cost pages (owner: Adel): the portal's sidebar, a header and a project
// picker, in the same look as the projects page (app/dashboard.js, Hilal). The page's own box comes from
// `children(projectId)` once a project is chosen.

import { useEffect, useMemo, useState } from "react";

import { createGatewayClient } from "../../app/lib/gateway.mjs";
import Problem from "../../app/components/problem";
import { chooseProject, projectHref } from "../../lib/pages/project-choice.mjs";

export const PAGES = [
  { key: "projects", href: "/", label: "Projects" },
  { key: "compare", href: "/compare", label: "Compare runs" },
  { key: "usage", href: "/usage", label: "Usage & cost" },
];

// The portal's stylesheet (Hilal's) colours the first sidebar link as the current one; on these pages the
// current page is another link, so the colour follows aria-current here instead.
const navLink = (current) => ({ background: current ? "#29474e" : "transparent" });
// Wide tables (9 columns on the comparison) scroll inside their box instead of widening the page.
const scrollBox = { overflowX: "auto" };

export default function WorkspacePage({ gatewayUrl, devToken, active, eyebrow, title, intro, requestedProject, children }) {
  const api = useMemo(() => createGatewayClient({ gatewayUrl, getToken: () => devToken }), [gatewayUrl, devToken]);
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [problem, setProblem] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setProblem(null);
    api.listProjects(controller.signal).then((body) => {
      if (!Array.isArray(body.items)) throw new Error("The project list could not be read.");
      setProjects(body.items);
      setProjectId((current) => chooseProject(body.items, current || requestedProject));
    }).catch((error) => {
      if (error.name !== "AbortError") setProblem(error);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, requestedProject]);

  // Keep the chosen project in the address, so a reload or a shared link shows the same one.
  useEffect(() => {
    if (projectId) window.history.replaceState(null, "", projectHref(PAGES.find((p) => p.key === active)?.href, projectId));
  }, [active, projectId]);

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/"><img src="/brand/cloudtrain-logo-dark.png" alt="CloudTrain" width="168" height="69" /><span>ML workspace</span></a>
      <nav aria-label="Main navigation">{PAGES.map((page) =>
        <a key={page.key} href={page.key === "projects" ? page.href : projectHref(page.href, projectId)}
          aria-current={page.key === active ? "page" : undefined} style={navLink(page.key === active)}>{page.label}</a>)}</nav>
      <p className="sidebar-note">Organize your data, training and models in one workspace.</p>
    </aside>
    <main style={{ minWidth: 0 }}>
      <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{intro}</p></div></header>
      {!devToken && <p className="notice">This workspace requires a signed-in session. Sign-in integration is pending.</p>}
      <section className="panel">
        <label htmlFor="project-picker">Project</label>
        <Problem error={problem} />
        {loading ? <p role="status">Loading projects…</p> : projects.length === 0 && !problem ?
          <p className="muted">No projects yet. Create one on the <a href="/">Projects</a> page.</p> :
          <select id="project-picker" value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={!!problem}>
            {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name} ({p.project_id})</option>)}
          </select>}
      </section>
      {projectId && <section className="panel" style={scrollBox}>{children(projectId)}</section>}
    </main>
  </div>;
}
