// One navigation across Hilal's pages and Adel's comparison/cost frame.
export const PAGES = [
  { key: "projects", href: "/", label: "Projects" },
  { key: "datasets", href: "/#datasets", label: "Datasets" },
  { key: "jobs", href: "/jobs", label: "Training jobs" },
  { key: "compare", href: "/compare", label: "Compare runs" },
  { key: "usage", href: "/usage", label: "Usage & cost" },
];
export default function Navigation({ active, projectId = "" }) {
  return <aside className="sidebar"><a className="brand" href="/"><img src="/brand/cloudtrain-logo-dark.png" alt="CloudTrain" width="168" height="69" /><span>ML workspace</span></a>
    <nav aria-label="Main navigation">{PAGES.map((page) => <a key={page.key} href={!["projects", "datasets"].includes(page.key) && projectId ? `${page.href}?project=${encodeURIComponent(projectId)}` : page.href} aria-current={page.key === active ? "page" : undefined}>{page.label}</a>)}</nav>
    <p className="sidebar-note">Organize your data, training and models in one workspace.</p></aside>;
}
