// Which project a page shows (owner: Adel). Shared by the comparison and cost pages.
//
// The address can name a project (`/usage?project=project-04`), so a link or a reload keeps it. A name that
// is not in the user's list is ignored (no request is ever made for it), and the first project is shown.

export const PROJECT_PARAM = "project";

/** The project to show: the requested one if the user has it, else the first, else "" (no projects). */
export function chooseProject(projects, requested) {
  const ids = (Array.isArray(projects) ? projects : []).map((p) => p?.project_id).filter(Boolean);
  if (requested && ids.includes(requested)) return requested;
  return ids[0] ?? "";
}

/** The address of a page for one project, e.g. projectHref("/usage", "project-04") -> "/usage?project=project-04". */
export function projectHref(path, projectId) {
  return projectId ? `${path}?${PROJECT_PARAM}=${encodeURIComponent(projectId)}` : path;
}
