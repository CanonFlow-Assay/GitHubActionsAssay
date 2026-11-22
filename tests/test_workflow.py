import hashlib
import json
from zipfile import ZipFile

from consumer import Consumer

SRC = "a" * 40
ENGINE = "b" * 40
HASH = "c" * 64
REPO = "example/owned"
PATH = ".github/workflows/ci.yml"


class WorkflowEvidence(Consumer):
    def setUp(self):
        super().setUp()
        workflow = b"name: Coherent evidence\n"
        (self.root / "workflow.yml").write_bytes(workflow)
        self.policy = {
            "schemaVersion": 1, "profile": "bound-run",
            "files": {"run": "run.json", "jobs": "jobs.json", "artifacts": "artifacts.json", "archive": "evidence.zip",
                      "workflow": "workflow.yml", "scopedLog": "scope.log", "runner": "runner.json"},
            "expects": {"repository": REPO, "runId": 10, "attempt": 1, "workflowPath": PATH,
                        "workflowSha256": hashlib.sha256(workflow).hexdigest(), "headSha": SRC, "job": "Gate",
                        "checkoutStep": "Engine", "packageStep": "Pack", "gates": ["Saga"],
                        "artifact": "proof", "sdkVersion": "11.0.100", "sdkMember": "sdk.json",
                        "engine": {"repository": "example/engine", "sha": ENGINE}, "packages": {"runner": HASH}},
        }
        self.run = {"repository": {"full_name": REPO}, "id": 10, "run_attempt": 1, "head_sha": SRC,
                    "path": PATH, "status": "completed", "conclusion": "success"}
        self.write("run.json", self.run)
        self.job = {"id": 20, "name": "Gate", "run_id": 10, "run_attempt": 1,
                    "steps": [{"name": "Saga", "conclusion": "success"}]}
        self.write("jobs.json", {"total_count": 1, "jobs": [self.job]})
        log = (
            "Gate\tEngine\t2026-11-22T02:00:00.001Z repository: example/engine\n"
            f"Gate\tEngine\t2026-11-22T02:00:00.002Z ref: {'f' * 40}\n"
            "Gate\tEngine\t2026-11-22T02:00:00.003Z [command]/usr/bin/git log -1 --format=%H\n"
            f"Gate\tEngine\t2026-11-22T02:00:00.004Z {ENGINE}\n"
            f"Gate\tPack\t2026-11-22T02:00:00.005Z ##assay-package-sha256 runner {HASH}\n"
        ).encode()
        (self.root / "scope.log").write_bytes(log)
        self.runner = {"runId": 10, "attempt": 1, "jobId": 20, "engine": self.policy["expects"]["engine"].copy(),
                       "packageHashes": {"runner": HASH}, "scopedLogSha256": hashlib.sha256(log).hexdigest()}
        self.write("runner.json", self.runner)
        self.zip("11.0.100")

    def zip(self, version):
        path = self.root / "evidence.zip"
        with ZipFile(path, "w") as stream:
            stream.writestr("sdk.json", json.dumps({"verdict": "pass",
                            "evidence": {"authoritative": True, "toolchain": {"sdkVersion": version}}}))
        artifact = {"id": 30, "name": "proof", "expired": False, "size_in_bytes": path.stat().st_size,
                    "digest": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
                    "workflow_run": {"id": 10, "head_sha": SRC}}
        self.write("artifacts.json", {"total_count": 1, "artifacts": [artifact]})

    def test_complete_runner_passes_and_scan_is_provisional(self):
        self.assertTrue(self.invoke(0)["authoritative"])
        self.assertEqual(self.invoke(2, "scan")["verdict"], "Inconclusive")

    def test_checked_out_engine_wins_over_the_requested_ref(self):
        self.policy["expects"]["engine"]["sha"] = "f" * 40
        self.failed_rule(self.invoke(1), "GH004")

    def test_selected_step_was_skipped_and_archive_missing(self):
        self.job["steps"][0]["conclusion"] = "skipped"
        self.write("jobs.json", {"total_count": 1, "jobs": [self.job]})
        (self.root / "evidence.zip").unlink()
        receipt = self.invoke(1)
        self.failed_rule(receipt, "GH003")
        self.assertFalse(receipt["authoritative"])

    def test_source_or_attempt_mismatch_rejects_replayed_data(self):
        self.run["run_attempt"] = 2
        self.write("run.json", self.run)
        self.failed_rule(self.invoke(1), "GH001")

    def test_run_failure_is_retained(self):
        self.run["conclusion"] = "failure"
        self.write("run.json", self.run)
        self.failed_rule(self.invoke(1), "GH002")

    def test_archive_byte_drift_is_detected(self):
        with (self.root / "evidence.zip").open("ab") as stream:
            stream.write(b"changed")
        self.failed_rule(self.invoke(1), "GH005")

    def test_sdk_and_package_drift_are_distinct(self):
        self.zip("11.0.100-rc.2")
        self.policy["expects"]["packages"]["runner"] = "d" * 64
        receipt = self.invoke(1)
        self.failed_rule(receipt, "GH006")
        self.failed_rule(receipt, "GH007")

    def test_workflow_digest_drift_fails(self):
        (self.root / "workflow.yml").write_text("name: changed\n")
        self.failed_rule(self.invoke(1), "GH008")

    def test_normalized_facts_must_match_scoped_log(self):
        self.runner["engine"]["sha"] = "d" * 40
        self.write("runner.json", self.runner)
        self.failed_rule(self.invoke(1), "GH004")

    def test_receipt_cannot_replace_bound_input(self):
        result = self.invoke(3, "verify", "--out", "workflow.yml")
        self.assertEqual(result["observed"]["verdict"], "Pass")
        self.assertEqual((self.root / "workflow.yml").read_bytes(), b"name: Coherent evidence\n")
