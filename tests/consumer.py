import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE, = (path.name for path in (ROOT / "src").iterdir() if (path / "engine.py").is_file())


class Consumer(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.policy = {}

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value) + "\n")

    def invoke(self, expected, command="verify", *arguments):
        self.write("policy.json", self.policy)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        archive = env.get("ASSAY_TEST_ARCHIVE")
        if archive:
            argv = [sys.executable, archive]
        else:
            argv = [sys.executable, "-m", PACKAGE]
            env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(
            [*argv, command, "--policy", "policy.json", *arguments],
            cwd=self.root, capture_output=True, text=True, env=env, timeout=20,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def failed_rule(self, receipt, rule):
        self.assertTrue(any(row["rule"] == rule and row["outcome"] == "failed"
                            for row in receipt["checks"]), receipt)
