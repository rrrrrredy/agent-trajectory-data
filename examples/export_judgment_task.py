"""Export one public development task's inputs, without reviewer material."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", choices=("study-claims", "editorial-selection"))
    parser.add_argument("--output", type=Path, required=True, help="New directory")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    source = repo / "tasks" / "evidence-judgment" / args.task / "input"
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Output already exists: {output}")
    # Only solver inputs; no recursive copy of the task or repository root.
    files = sorted(p for p in source.iterdir() if p.is_file())
    output.mkdir(parents=True)
    for path in files:
        shutil.copyfile(path, output / path.name)
    shutil.copyfile(repo / "LICENSE", output / "LICENSE")
    manifest = {
        "task": args.task,
        "split": "development",
        "training_eligible": False,
        "reference_answer_included": False,
        "model_runs": 0,
        "permission_isolation": False,
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(output.iterdir()) if p.is_file()
        },
    }
    (output / "input-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(output), **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
