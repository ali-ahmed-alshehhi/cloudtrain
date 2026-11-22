import test from "node:test";
import assert from "node:assert/strict";

import { chooseProject, projectHref } from "../lib/pages/project-choice.mjs";

const projects = [{ project_id: "project-01" }, { project_id: "project-04" }];

test("the project named in the address is shown when the user has it", () => {
  assert.equal(chooseProject(projects, "project-04"), "project-04");
});

test("an unknown or missing project falls back to the first one, never to the unknown id", () => {
  assert.equal(chooseProject(projects, "project-99"), "project-01");
  assert.equal(chooseProject(projects, ""), "project-01");
  assert.equal(chooseProject(projects, "../admin"), "project-01");
});

test("no projects (or an unreadable list) means no project", () => {
  assert.equal(chooseProject([], "project-01"), "");
  assert.equal(chooseProject(undefined, "project-01"), "");
});

test("a page address keeps the project, encoded", () => {
  assert.equal(projectHref("/usage", "project-04"), "/usage?project=project-04");
  assert.equal(projectHref("/compare", "a b&c"), "/compare?project=a%20b%26c");
  assert.equal(projectHref("/usage", ""), "/usage");
});
