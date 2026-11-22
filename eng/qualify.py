"""Run acceptance cases against both source and an independent zipapp consumer."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def execute(name, argv, out, env):
    result = subprocess.run(argv, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    (out / f"{name}.stdout").write_text(result.stdout)
    (out / f"{name}.stderr").write_text(result.stderr)
    (out / f"{name}.command.json").write_text(json.dumps({"argv": argv, "exitCode": result.returncode}) + "\n")
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"{name} failed")
    return result


def main():
    out = ROOT / "artifacts" / "qualification"
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.pop("ASSAY_TEST_ARCHIVE", None)
    env.pop("PYTHONPATH", None)
    tests = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
    first = execute("source-tests", tests, out, env)
    archive = Path(execute("package", [sys.executable, "eng/package.py"], out, env).stdout.splitlines()[0])
    identity = hashlib.sha256(archive.read_bytes()).hexdigest()
    execute("repeat-package", [sys.executable, "eng/package.py"], out, env)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != identity:
        raise RuntimeError("archive output changed between builds")
    with tempfile.TemporaryDirectory(prefix="assay-consumer-") as folder:
        copied = Path(folder) / archive.name
        shutil.copyfile(archive, copied)
        second = execute("archive-tests", tests, out, {**env, "ASSAY_TEST_ARCHIVE": str(copied)})
    counts = [int(re.search(r"Ran (\d+) tests?", result.stderr)[1]) for result in (first, second)]
    record = {"status": "Pass", "sourceTests": counts[0], "archiveTests": counts[1],
              "archive": archive.name, "archiveSha256": identity}
    (out / "summary.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
