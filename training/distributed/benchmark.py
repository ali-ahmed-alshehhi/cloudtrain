"""Benchmark runner: 1 GPU against multi-GPU DDP, and DataLoader workers against throughput.

    python -m distributed.benchmark scaling --gpus 1 2 --machine-type g4dn.12xlarge --out scaling.json
    python -m distributed.benchmark workers --values 0 2 4 8 --out workers.json
    python -m distributed.benchmark report scaling.json

`scaling` and `workers` also take the training flags of `distributed.train` (--model, --dataset,
--epochs, --batch-size, ...). Add `--sync-probe-steps 50` to a `scaling` run to measure gradient-sync
time as well. Every finished run is saved at once, so an interrupted benchmark keeps what it measured.
`report` prints the Markdown tables for docs/BENCHMARKS.md from a saved file.
"""

import argparse
import json
from pathlib import Path

from . import metrics, train


def render(saved: dict) -> str:
    """The Markdown tables for one saved benchmark."""
    results = saved["results"]
    if saved["experiment"] == "workers":
        return metrics.workers_table(results)
    price = metrics.hourly_price(saved["machine_type"]) if saved["machine_type"] else None
    tables = [metrics.scaling_table(metrics.scaling_rows(results, price))]
    probed = [result for result in results if result["sync_probe"]]
    if probed:
        tables.append(metrics.sync_table(probed))
    return "\n\n".join(tables)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    scaling = commands.add_parser("scaling", help="the same training on each GPU count")
    scaling.add_argument("--gpus", type=int, nargs="+", default=[1, 2])
    scaling.add_argument("--repeats", type=int, default=3, help="runs per GPU count, each with its own seed")
    scaling.add_argument("--machine-type", help="a machine type in contracts/pricing.yaml, for the cost")
    workers = commands.add_parser("workers", help="the same training with each number of DataLoader workers")
    workers.add_argument("--values", type=int, nargs="+", default=[0, 2, 4, 8])
    for command in (scaling, workers):
        command.add_argument("--out", required=True, help="JSON file for the results")
        train.add_arguments(command)
    commands.add_parser("report", help="print the tables of a saved benchmark").add_argument("file")
    args = parser.parse_args(argv)

    if args.command == "report":
        print(render(json.loads(Path(args.file).read_text())))
        return
    saved = {"experiment": args.command, "machine_type": None, "results": []}
    if args.command == "scaling":
        if args.machine_type:
            metrics.hourly_price(args.machine_type)  # an unknown machine type stops here, before any GPU time
        saved["machine_type"] = args.machine_type
        configs = [
            train.config_from(
                args, strategy="single" if gpus == 1 else "ddp", world_size=gpus, seed=args.seed + repeat
            )
            for gpus in args.gpus
            for repeat in range(args.repeats)
        ]
    else:
        configs = [train.config_from(args, num_workers=value) for value in args.values]
    for cfg in configs:
        print(f"{cfg.strategy} x{cfg.world_size}, {cfg.num_workers} workers, seed {cfg.seed} ...", flush=True)
        saved["results"].append(train.run(cfg))
        Path(args.out).write_text(json.dumps(saved, indent=1))
    print(render(saved))


if __name__ == "__main__":
    main()
