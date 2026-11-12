"""Load routes.yaml and decide where a public path goes."""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROUTES_FILE = Path(__file__).parent / "routes.yaml"


@dataclass(frozen=True)
class Route:
    name: str
    prefixes: tuple[str, ...]
    target: str  # the service address, e.g. http://job-service:8003
    rewrite_from: str
    rewrite_to: str
    methods: frozenset[str] | None  # None means every method is allowed
    post_suffix: str | None  # POST allowed only on paths ending with this
    errors_from: str | None

    def matches(self, path: str) -> bool:
        return any(path == prefix or path.startswith(prefix + "/") for prefix in self.prefixes)

    def allows(self, method: str, path: str) -> bool:
        if self.methods is None or method in self.methods:
            return True
        return method == "POST" and self.post_suffix is not None and path.endswith(self.post_suffix)

    def upstream_url(self, path: str, query: str) -> str:
        """The full address to forward to, e.g. /api/v1/jobs/job-1 -> http://job-service:8003/jobs/job-1."""
        new_path = self.rewrite_to + path[len(self.rewrite_from) :]
        url = self.target.rstrip("/") + new_path
        return f"{url}?{query}" if query else url


def load_routes(path: Path = ROUTES_FILE) -> list[Route]:
    """Read the route table. Stops at start-up if a service address variable is missing."""
    raw = yaml.safe_load(path.read_text())["routes"]
    routes = []
    for item in raw:
        target_variable = item["target"]
        target = os.environ.get(target_variable)
        if not target:
            raise ValueError(f"Route '{item['name']}' needs the environment variable {target_variable}")
        methods = item["methods"]
        routes.append(
            Route(
                name=item["name"],
                prefixes=tuple(item["match"]),
                target=target,
                rewrite_from=item["rewrite"]["from"],
                rewrite_to=item["rewrite"]["to"],
                methods=None if methods == "all" else frozenset(m.upper() for m in methods),
                post_suffix=item.get("post_allowed_when_path_ends_with"),
                errors_from=item.get("errors_from"),
            )
        )
    return routes


def find_route(routes: list[Route], path: str) -> Route | None:
    for route in routes:
        if route.matches(path):
            return route
    return None


def is_forbidden_path(path: str) -> bool:
    """Internal addresses are never public, and '..' tricks are refused."""
    segments = path.lower().split("/")
    return "internal" in segments or ".." in segments or "." in segments
