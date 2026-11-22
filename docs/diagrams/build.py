"""Draws the two report diagrams as SVG: architecture.svg and deployment.svg.

Run from the repository root:  python docs/diagrams/build.py
Edit the boxes and lines below, run again, and commit the SVG files with this script.
Colours and font follow docs/brand/README.md. The font is embedded so the files look the same everywhere.
"""

import base64
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).parent
FONT = HERE.parent / "brand" / "fonts" / "nunito-latin.woff2"

# brand colours (docs/brand/README.md)
WHITE = "#FFFFFF"
CLOUD = "#F7FBFE"
BABY = "#BFE3FA"
TINT = "#E6F3FC"
STEEL = "#5B8DB8"
SLATE = "#334155"
MUTED = "#64748B"
AMBER = "#E9A93B"


class Svg:
    def __init__(self, width: int, height: int, title: str):
        self.w, self.h, self.title = width, height, title
        self.parts: list[str] = []

    def add(self, text: str) -> None:
        self.parts.append(text)

    # ---------- text ----------
    def text(self, x, y, s, size=12, weight=600, color=SLATE, anchor="start", halo=False):
        extra = (
            f' paint-order="stroke" stroke="{CLOUD}" stroke-width="5" stroke-linejoin="round"' if halo else ""
        )
        self.add(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}" '
            f'text-anchor="{anchor}"{extra}>{escape(s)}</text>'
        )

    def label(self, x, y, s, anchor="start"):
        """A small label beside a line."""
        self.text(x, y, s, size=11.5, weight=700, color=MUTED, anchor=anchor, halo=True)

    def rect(self, x, y, w, h, fill, stroke, rx=10, width=1.6, dashed=False):
        dash = ' stroke-dasharray="6 4"' if dashed else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{width}"{dash}/>'
        )

    # ---------- boxes ----------
    def box(self, x, y, w, h, title, lines=(), kind="service", planned=False):
        fill, stroke = {
            "service": (WHITE, SLATE),
            "published": (BABY, STEEL),
            "queue": (WHITE, STEEL),
            "external": (TINT, STEEL),
        }[kind]
        dash = ' stroke-dasharray="6 4"' if planned else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="1.6"{dash}/>'
        )
        if kind == "queue":  # message slots at the right end
            for i in range(3):
                sx = x + w - 14 - i * 9
                self.add(f'<rect x="{sx}" y="{y + 10}" width="5" height="{h - 20}" rx="2" fill="{BABY}"/>')
        self._lines(x + 14, y, h, title, lines)

    def store(self, x, y, w, h, title, lines=(), planned=False):
        """A cylinder: a database or a bucket."""
        ry = 9
        dash = ' stroke-dasharray="6 4"' if planned else ""
        body = (
            f"M{x},{y + ry} v{h - 2 * ry} a{w / 2},{ry} 0 0 0 {w},0 v{-(h - 2 * ry)} "
            f"a{w / 2},{ry} 0 0 0 {-w},0 z"
        )
        self.add(f'<path d="{body}" fill="{TINT}" stroke="{SLATE}" stroke-width="1.6"{dash}/>')
        self.add(
            f'<path d="M{x},{y + ry} a{w / 2},{ry} 0 0 0 {w},0" fill="none" stroke="{SLATE}" '
            f'stroke-width="1.6"{dash}/>'
        )
        self._lines(x + 14, y + 2 * ry - 4, h - 2 * ry + 4, title, lines)

    def _lines(self, x, y, h, title, lines):
        total = 18 + 16 * len(lines)
        top = y + (h - total) / 2 + 14
        self.text(x, top, title, size=15, weight=800)
        for i, line in enumerate(lines):
            self.text(x, top + 18 + i * 16, line, size=12, weight=600, color=MUTED)

    def zone(self, x, y, w, h, title, color=STEEL, fill="none", dashed=True):
        dash = ' stroke-dasharray="8 5"' if dashed else ""
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" stroke="{color}" '
            f'stroke-width="1.6"{dash}/>'
        )
        self.text(x + 14, y + 22, title, size=12.5, weight=800, color=color if color != AMBER else SLATE)

    def step(self, x, y, n):
        """A numbered marker, matched to the notes under the diagram."""
        self.add(f'<circle cx="{x}" cy="{y}" r="12" fill="{STEEL}" stroke="{CLOUD}" stroke-width="2.5"/>')
        self.text(x, y + 4.5, str(n), size=12.5, weight=900, color=WHITE, anchor="middle")

    # ---------- lines ----------
    def line(self, *points, dashed=False, arrow=True, start_arrow=False):
        """An orthogonal line through the points, with an arrowhead at the end."""
        d = "M" + " L".join(f"{px},{py}" for px, py in points)
        dash = ' stroke-dasharray="6 5"' if dashed else ""
        color = STEEL if dashed else SLATE
        marker = (' marker-end="url(#a-steel)"' if dashed else ' marker-end="url(#a)"') if arrow else ""
        if start_arrow:
            marker += ' marker-start="url(#a-start)"'
        self.add(
            f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round"{dash}{marker}/>'
        )

    def dot(self, x, y):
        self.add(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{SLATE}"/>')

    # ---------- page parts ----------
    def notes(self, x, y, items, columns=3, col_width=440):
        rows = -(-len(items) // columns)
        for i, item in enumerate(items):
            cx = x + (i // rows) * col_width
            cy = y + (i % rows) * 40
            self.step(cx + 12, cy + 4, i + 1)
            for j, part in enumerate(wrap(item, 52)):
                self.text(cx + 32, cy + 8 + j * 15, part, size=12, weight=600)

    def save(self, path: Path) -> None:
        font = base64.b64encode(FONT.read_bytes()).decode()
        head = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
            f'width="{self.w}" height="{self.h}" role="img" aria-label="{escape(self.title)}">\n'
            f"<title>{escape(self.title)}</title>\n"
            "<style>@font-face{font-family:Nunito;font-weight:200 1000;"
            f"src:url(data:font/woff2;base64,{font}) format('woff2')}}"
            "text{font-family:Nunito,'Segoe UI',Helvetica,Arial,sans-serif}</style>\n"
            "<defs>"
            f'<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            f'orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="{SLATE}"/></marker>'
            f'<marker id="a-steel" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" '
            f'orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="{STEEL}"/></marker>'
            f'<marker id="a-start" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" '
            f'orient="auto"><path d="M10,1 L1,5 L10,9 z" fill="{SLATE}"/></marker>'
            "</defs>\n"
            f'<rect width="{self.w}" height="{self.h}" fill="{CLOUD}"/>\n'
        )
        path.write_text(head + "\n".join(self.parts) + "\n</svg>\n", encoding="utf-8")


def wrap(text: str, width: int) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    return lines + [current]


def legend(s: Svg, x: int, y: int, items: list[tuple[str, str]]) -> None:
    """items: (kind, text). kinds: published, service, queue, store, planned, call, async, step."""
    for kind, text in items:
        if kind in ("published", "service", "queue"):
            fill = {"published": BABY, "service": WHITE, "queue": WHITE}[kind]
            stroke = STEEL if kind != "service" else SLATE
            s.rect(x, y - 11, 26, 16, fill, stroke, rx=4, width=1.4)
        elif kind == "planned":
            s.rect(x, y - 11, 26, 16, WHITE, SLATE, rx=4, width=1.4, dashed=True)
        elif kind == "store":
            s.store(x, y - 14, 26, 22, "")
        elif kind == "call":
            s.line((x, y - 3), (x + 26, y - 3))
        elif kind == "async":
            s.line((x, y - 3), (x + 26, y - 3), dashed=True)
        elif kind == "step":
            s.step(x + 13, y - 3, 1)
        s.text(x + 34, y + 1, text, size=12, weight=700, color=SLATE)
        x += 34 + int(len(text) * 6.6) + 26


# =====================================================================================
# 1. Architecture: the services and how a request moves through them
# =====================================================================================


def architecture() -> Svg:
    s = Svg(1500, 1150, "CloudTrain architecture")
    s.text(40, 48, "CloudTrain architecture", size=24, weight=900)
    s.text(40, 72, "The same services run on a laptop (docker compose) and on AWS.", size=13, color=MUTED)

    # published ports: the only way in
    s.box(40, 470, 150, 64, "Browser", ["the user"], kind="external")
    s.zone(232, 300, 240, 420, "Published ports", color=AMBER)
    s.box(260, 345, 184, 84, "Web portal", [":3000 · Hilal + Adel"], kind="published")
    s.box(260, 545, 184, 100, "API gateway", [":5810 · Ali", "login, request ID, routes"], kind="published")
    s.line((190, 490), (212, 490), (212, 387), (260, 387))
    s.line((190, 514), (222, 514), (222, 595), (260, 595))
    s.line((352, 429), (352, 545))
    s.label(362, 482, "API calls")
    s.label(362, 497, "via gateway only")

    # the services behind the gateway, on one route bus
    col, w = 620, 220
    rows = {  # name: (y, height)
        "projects": (110, 76),
        "datasets": (215, 76),
        "jobs": (330, 120),
        "mlflow": (480, 76),
        "registry": (595, 76),
        "inference": (710, 76),
    }
    s.box(col, *_yh(rows["projects"], w), "Projects", [":8001 · Ali", "members, who am I"])
    s.box(col, *_yh(rows["datasets"], w), "Datasets", [":8002 · Faisal", "versions, checksums"])
    s.box(
        col,
        *_yh(rows["jobs"], w),
        "Training jobs",
        [":8003 · Mariam", "202 Accepted, job history,", "GPU-hours and cost"],
    )
    s.box(col, *_yh(rows["mlflow"], w), "MLflow", [":5000 · Abdullah · read only"])
    s.box(col, *_yh(rows["registry"], w), "Model registry", [":8006 · Majed", "versions, promote, rollback"])
    s.box(col, *_yh(rows["inference"], w), "Inference", [":8007 · Majed", "loads the live version"])

    bus = 540
    s.line((444, 595), (bus, 595), arrow=False)
    s.dot(bus, 595)
    centres = {name: y + h / 2 for name, (y, h) in rows.items()}
    s.line((bus, centres["projects"]), (bus, centres["inference"]), arrow=False)
    routes = {
        "projects": "/projects",
        "datasets": "/datasets",
        "jobs": "/jobs",
        "mlflow": "/experiments",
        "registry": "/models",
        "inference": "/predict",
    }
    for name, path in routes.items():
        s.line((bus, centres[name]), (col, centres[name]))
        s.label(bus + 8, centres[name] - 7, path)
    s.label(bus - 6, 92, "/api/v1/…", anchor="start")

    # calls between services (never through the gateway)
    mid = col + 110
    s.line((mid, 330), (mid, 291))
    s.label(mid + 8, 316, "version exists?")
    s.line((mid, 595), (mid, 556))
    s.label(mid + 8, 581, "read run, register")
    s.line((mid, 710), (mid, 671))
    s.label(mid + 8, 696, "live version")

    # training runs in the background: queue → scheduler → worker
    q, qw, e = 920, 236, 1236
    s.box(q, 110, qw, 64, "SQS job-events", ["every status change"], kind="queue")
    s.box(q, 215, qw, 60, "SQS training-jobs-dlq", ["failure reports"], kind="queue")
    s.box(q, 357, qw, 76, "SQS training-jobs", ["one reader only"], kind="queue")
    s.box(e, 110, 214, 64, "Monitoring", ["dashboards · Hilal + Adel"])
    s.box(e, 357, 214, 76, "Scheduler", [":8004 · Maitha", "picks the machine"])
    s.box(e, 490, 214, 96, "Training worker", [":8010 · Abdullah", "DDP: Ahmed + Abdulla"])

    jobs_right = col + w
    s.line((jobs_right, 345), (880, 345), (880, 142), (q, 142))  # events out
    s.label(874, 312, "events", anchor="end")
    s.line((q, 245), (900, 245), (900, 370), (jobs_right, 370), dashed=True)  # DLQ back to jobs
    s.line((jobs_right, 395), (q, 395))  # send job
    s.label(jobs_right + 30, 388, "send job")
    s.line((q + 110, 357), (q + 110, 275), dashed=True)
    s.label(q + 118, 322, "after retry limit")
    s.line((q + qw, 395), (e, 395))
    s.line((q + qw, 142), (e, 142))
    s.line((e + 105, 433), (e + 105, 490))
    s.label(e + 113, 466, "/internal/run")
    # status and heartbeats back to Training jobs
    s.line((e, 520), (870, 520), (870, 425), (jobs_right, 425))
    s.line((e, 420), (1190, 420), (1190, 520), arrow=False)
    s.dot(1190, 520)
    s.label(950, 513, "status, heartbeat")
    # metrics and the model go to MLflow
    s.line((e, 566), (855, 566), (855, 518), (jobs_right, 518))
    s.label(950, 559, "metrics, model")

    # data stores
    s.store(col, 870, 536, 84, "PostgreSQL", ["one schema per service · RDS on AWS"])
    s.store(e, 870, 214, 84, "S3", ["datasets, artifacts"])
    s.line((mid, 786), (mid, 870))
    s.label(mid + 8, 832, "each service: its own schema")
    s.line((e + 105, 586), (e + 105, 870))
    s.label(e + 113, 735, "data in, model out")

    # walk-through steps
    for n, (x, y) in enumerate(
        [
            (260, 545),
            (col, 110),
            (col, 215),
            (col, 330),
            (e, 357),
            (e, 490),
            (q, 110),
            (col, 595),
            (col, 710),
        ],
        start=1,
    ):
        s.step(x, y, n)

    legend(
        s,
        40,
        990,
        [
            ("published", "published port"),
            ("service", "service"),
            ("queue", "SQS queue"),
            ("store", "data store"),
            ("call", "call or message"),
            ("async", "failure path"),
            ("step", "step in the walk-through"),
        ],
    )
    s.notes(
        40,
        1030,
        [
            "Log in at the gateway: Cognito on AWS, a test token on a laptop.",
            "Create a project. Every service checks membership with Projects.",
            "Upload a dataset. Each version is kept in S3 with a checksum.",
            "Submit a job. The dataset version is checked and the answer is 202 at once.",
            "The scheduler is the only reader of the queue and picks a machine.",
            "The worker trains (one GPU or DDP), sends heartbeats and logs to MLflow.",
            "Every status change is an event. The portal shows it as an alert.",
            "Register the best model from its MLflow run, then promote it.",
            "Inference loads the live version and answers predictions.",
        ],
    )
    return s


def _yh(row, w):
    y, h = row
    return y, w, h


# =====================================================================================
# 2. Deployment: which AWS piece runs what
# =====================================================================================

# What Terraform on main does not create yet. Empty since 22 Nov: ECS (#135), RDS (#95), Cognito (#127),
# GPU workers (#123, #133), Secrets Manager (#110) and CloudWatch (#134) are all merged.
PLANNED: set[str] = set()


def deployment() -> Svg:
    s = Svg(1500, 1260, "CloudTrain deployment on AWS")
    s.text(40, 48, "CloudTrain on AWS", size=24, weight=900)
    s.text(
        40,
        72,
        "Every resource is created by Terraform (applied to the AWS Emulator in CI, decision 0011).",
        size=13,
        color=MUTED,
    )

    def p(name):
        return name in PLANNED

    s.box(40, 217, 140, 60, "Browser", ["the user"], kind="external")
    s.zone(212, 96, 1262, 846, "AWS account · us-east-1", color=SLATE, dashed=False)
    s.zone(
        246,
        134,
        828,
        784,
        "VPC 10.0.0.0/16 · 2 availability zones (us-east-1a, us-east-1b)",
        color=STEEL,
        dashed=False,
    )
    s.zone(270, 168, 780, 196, "Public subnets 10.0.0.0/24, 10.0.1.0/24", color=AMBER, dashed=False)
    s.zone(270, 392, 780, 506, "Private subnets 10.0.10.0/24, 10.0.11.0/24", color=STEEL, dashed=False)

    # public subnets
    s.box(290, 215, 120, 64, "Internet", ["gateway"], kind="external")
    s.box(
        450,
        205,
        170,
        84,
        "Load balancer",
        ["listeners 5810, 3000", "HTTPS 443: real account"],
        planned=p("alb"),
    )
    s.box(680, 190, 170, 58, "To gateway", [":5810, private subnet"], kind="published", planned=p("gateway"))
    s.box(680, 272, 170, 58, "To portal", [":3000, private subnet"], kind="published", planned=p("portal"))
    s.box(895, 215, 135, 64, "NAT gateway", ["outbound only"], kind="external")
    s.line((180, 247), (290, 247))
    s.label(230, 239, "HTTP(S)")
    s.line((410, 247), (450, 247))
    s.line((620, 230), (650, 230), (650, 219), (680, 219))
    s.line((620, 265), (660, 265), (660, 301), (680, 301))

    # private subnets
    s.rect(290, 448, 420, 262, WHITE, SLATE, dashed=p("services"))
    s.text(304, 474, "ECS Fargate services", size=15, weight=800)
    s.text(304, 492, "stateless, one image each, one security group", size=12, color=MUTED)
    names = ["Projects", "Datasets", "Training jobs", "Scheduler", "Model registry", "Inference", "MLflow"]
    for i, name in enumerate(names):
        x = 304 + (i % 2) * 200
        y = 510 + (i // 2) * 46
        s.rect(x, y, 188, 36, TINT, STEEL, rx=8, width=1.2)
        s.text(x + 12, y + 23, name, size=13, weight=800)
    s.box(
        760,
        448,
        270,
        112,
        "EC2 CPU / GPU workers",
        ["pools: 1 GPU and 4 GPUs", "internal load balancer per pool"],
        planned=p("workers"),
    )
    s.store(
        760,
        616,
        270,
        94,
        "RDS PostgreSQL",
        ["one schema per service", "password kept by Secrets Manager"],
        planned=p("rds"),
    )

    # traffic inside the VPC
    s.line((850, 219), (870, 219), (870, 420), (560, 420), (560, 448))
    s.label(578, 413, "API calls to services")
    s.line((710, 520), (760, 520))
    s.label(712, 512, "run")
    s.line((710, 680), (760, 680))
    s.label(714, 672, "5432")
    s.line((895, 560), (895, 616))
    s.label(903, 593, "5432")

    # security groups (already in Terraform)
    s.rect(290, 742, 740, 132, TINT, STEEL, width=1.2)
    s.text(304, 768, "Security groups (in Terraform)", size=14, weight=800)
    rules = [
        ("alb", "443, 5810, 3000 from the internet"),
        ("services", "from the load balancer and from each other"),
        ("workers", "only from services (scheduler, job control)"),
        ("database", "PostgreSQL 5432 only from services and workers"),
    ]
    for i, (name, rule) in enumerate(rules):
        s.text(304, 792 + i * 21, name, size=12.5, weight=800, color=STEEL)
        s.text(384, 792 + i * 21, rule, size=12.5, weight=600)

    # outbound: private subnets reach AWS services through the NAT gateway
    s.line((965, 448), (965, 279))
    s.line((710, 470), (740, 470), (740, 436), (965, 436), arrow=False)
    s.dot(965, 436)
    s.label(974, 410, "outbound")

    # regional AWS services, outside the VPC
    r = 1112
    s.store(r, 130, 330, 90, "S3", ["datasets, artifacts", "versioned, encrypted, private"])
    s.box(r, 240, 330, 74, "SQS", ["training-jobs + DLQ, job-events"], kind="queue")
    s.box(r, 334, 330, 74, "ECR", ["one image repository per service"])
    s.box(r, 428, 330, 74, "Cognito user pool", ["login tokens for the gateway"], planned=p("cognito"))
    s.box(r, 522, 330, 74, "Secrets Manager", ["passwords and keys"], planned=p("secrets"))
    s.box(r, 616, 330, 74, "CloudWatch", ["logs and metrics"], planned=p("cloudwatch"))
    s.box(r, 716, 330, 84, "Terraform state", ["S3 backend with a lock", "never committed"])

    bus = 1090
    s.line((1030, 247), (bus, 247), arrow=False)
    s.dot(bus, 247)
    s.line((bus, 175), (bus, 653), arrow=False)
    for cy in (175, 277, 371, 465, 559, 653):
        s.line((bus, cy), (r, cy))

    # CI and Terraform from outside
    s.box(40, 958, 230, 74, "GitHub Actions", ["tests every pull request", "builds, scans, pushes images"])
    s.line((270, 995), (1456, 995), (1456, 371), (r + 330, 371))
    s.line((1277, 995), (1277, 800))
    s.dot(1277, 995)
    s.label(300, 987, "terraform apply on the emulator · deploy role (#129)")

    for n, (x, y) in enumerate(
        [(450, 205), (680, 190), (290, 448), (760, 448), (760, 616), (895, 215), (40, 958)], start=1
    ):
        s.step(x, y, n)

    legend(
        s,
        40,
        1070,
        [
            ("published", "gateway and portal"),
            ("service", "in Terraform on main (22 Nov)"),
            ("store", "data store"),
            ("queue", "SQS queues"),
            ("step", "note below"),
        ],
    )
    s.notes(
        40,
        1110,
        [
            "The load balancer is the only way in: 5810 and 3000 (443 with a real account).",
            "The gateway and the portal sit behind it. Every API call goes through the gateway.",
            "The other services run privately on ECS Fargate and call each other directly.",
            "Training runs on EC2 GPU workers; the Scheduler sends each job to its pool.",
            "Only services and workers can reach PostgreSQL.",
            "Private subnets reach S3, SQS and other AWS services through the NAT gateway.",
            "CI tests every change. Terraform creates everything; its state is locked in S3.",
        ],
    )
    return s


if __name__ == "__main__":
    architecture().save(HERE / "architecture.svg")
    deployment().save(HERE / "deployment.svg")
    print("wrote", HERE / "architecture.svg", "and", HERE / "deployment.svg")
