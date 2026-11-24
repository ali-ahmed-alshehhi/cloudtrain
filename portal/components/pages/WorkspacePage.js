"use client";
// The frame of the comparison and cost pages (owner: Adel): the portal's sidebar, a header and a project
// picker, in the same look as the projects page (app/dashboard.js, Hilal). The page's own box comes from
// `children(projectId)` once a project is chosen.

import { useEffect, useMemo, useState } from "react";

import { createGatewayClient } from "../../app/lib/gateway.mjs";
import Problem from "../../app/components/problem";
import { chooseProject, projectHref } from "../../lib/pages/project-choice.mjs";

import Navigation, { PAGES } from "../../app/components/navigation";

// Wide tables (9 columns on the comparison) scroll inside their box instead of widening the page.
const scrollBox = { overflowX: "auto" };

export default function WorkspacePage({ gatewayUrl, devToken, active, eyebrow, title, intro, requestedProject, children, projectLocked = false, pagePath }) {
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
      if (controller.signal.aborted) return;
      setProjects(body.items);
      setProjectId((current) => chooseProject(body.items, current || requestedProject));
    }).catch((error) => {
      if (error.name !== "AbortError") setProblem(error);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [api, requestedProject]);

  // Keep the chosen project in the address, so a reload or a shared link shows the same one.
  useEffect(() => {
    if (projectId) window.history.replaceState(null, "", projectHref(pagePath || PAGES.find((p) => p.key === active)?.href, projectId));
  }, [active, projectId, pagePath]);

  return <div className="shell">
    <Navigation active={active} projectId={projectId} />
    <main style={{ minWidth: 0 }}>
      <header className="page-header"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p>{intro}</p></div></header>
      {!devToken && <p className="notice">This workspace requires a signed-in session. Sign-in integration is pending.</p>}
      <section className="panel">
        <label htmlFor="project-picker">Project</label>
        <Problem error={problem} />
        {loading ? <p role="status">Loading projects…</p> : projects.length === 0 && !problem ?
          <p className="muted">No projects yet. Create one on the <a href="/">Projects</a> page.</p> :
          <select id="project-picker" value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={!!problem || projectLocked}>
            {projects.map((p) => <option key={p.project_id} value={p.project_id}>{p.name} ({p.project_id})</option>)}
          </select>}
      </section>
      {!loading && !problem && projectId && <section className="panel" style={scrollBox}>{children(projectId)}</section>}
    </main>
  </div>;
}
