"""Assemble the local CSharp Playground evidence captured from the GitHub API."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from github_actions_assay.adapter import expect
from github_actions_assay.engine import bounded_bytes, load_policy
from github_actions_assay.logs import parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    policy = load_policy(bounded_bytes(args.plan.absolute()), "bound-run")
    plan = policy["expects"]
    expect(plan)
    run = plan["runId"]
    args.out.mkdir(parents=True, exist_ok=False)
    for role in ("run", "jobs", "artifacts"):
        shutil.copyfile(args.input / f"{run}-{role}.json", args.out / policy["files"][role])
    workflow = (args.input / "playground.yml").read_bytes()
    (args.out / policy["files"]["workflow"]).write_bytes(workflow)
    scoped_log = (args.input / f"{run}-selected.log").read_bytes()
    (args.out / policy["files"]["scopedLog"]).write_bytes(scoped_log)
    jobs = json.loads((args.out / policy["files"]["jobs"]).read_text())["jobs"]
    selected = [job for job in jobs if job["name"] == plan["job"]]
    if len(selected) != 1:
        raise ValueError("unique planned job is required when assembling evidence")
    checkout, packages = parse(scoped_log.decode("utf-8"), plan["job"], plan["checkoutStep"], plan["packageStep"])
    runner = {"runId": run, "attempt": plan["attempt"], "jobId": selected[0]["id"], "engine": checkout,
              "packageHashes": packages, "scopedLogSha256": hashlib.sha256(scoped_log).hexdigest()}
    (args.out / policy["files"]["runner"]).write_text(json.dumps(runner, indent=2) + "\n")
    if (args.input / f"{run}-archive.zip").is_file():
        shutil.copyfile(args.input / f"{run}-archive.zip", args.out / policy["files"]["archive"])
    shutil.copyfile(args.plan, args.out / "policy.json")


if __name__ == "__main__":
    main()
