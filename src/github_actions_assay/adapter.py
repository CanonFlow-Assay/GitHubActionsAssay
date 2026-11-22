"""Check a declared GitHub Actions run attempt against an independent plan."""

import re
import shutil
from zipfile import BadZipFile, ZipFile

from .logs import parse

EXTRA_FILES = ("logs.py",)
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
PUBLIC_NAME = re.compile(r"[-.A-Za-z0-9_]+/[-.A-Za-z0-9_]+\Z")


def doctor():
    return {"verifyOffline": True, "githubCollectorAvailable": shutil.which("gh") is not None}


def expect(value):
    required = {
        "repository", "workflowPath", "workflowSha256", "headSha", "runId", "attempt",
        "job", "gates", "engine", "sdkVersion", "sdkMember", "artifact", "packages",
        "checkoutStep", "packageStep",
    }
    if set(value) != required or not isinstance(value["repository"], str) or not PUBLIC_NAME.fullmatch(value["repository"]):
        raise ValueError("invalid workflow plan")
    if any(type(value[key]) is not int or value[key] < 1 for key in ("runId", "attempt")):
        raise ValueError("invalid GitHub run identity")
    if any(not isinstance(value[key], str) or not value[key] for key in ("artifact", "job", "sdkVersion", "sdkMember", "checkoutStep", "packageStep")):
        raise ValueError("invalid workflow expectation")
    from .engine import relative_file
    relative_file(value["workflowPath"])
    relative_file(value["sdkMember"])
    if not SHA.fullmatch(value["headSha"]) or not DIGEST.fullmatch(value["workflowSha256"]):
        raise ValueError("workflow and source identities must be pinned")
    engine = value["engine"]
    if not isinstance(engine, dict) or set(engine) != {"repository", "sha"}:
        raise ValueError("engine must have an expected repository and SHA")
    if not PUBLIC_NAME.fullmatch(engine["repository"]) or not SHA.fullmatch(engine["sha"]):
        raise ValueError("engine identity must be pinned")
    gates = value["gates"]
    if not isinstance(gates, list) or not 1 <= len(gates) <= 64 or any(not isinstance(gate, str) or not gate for gate in gates):
        raise ValueError("expected nonempty required gates")
    if len(set(gates)) != len(gates):
        raise ValueError("required gates must be unique")
    packages = value["packages"]
    if not isinstance(packages, dict) or not packages or any(not DIGEST.fullmatch(sha) for sha in packages.values()):
        raise ValueError("reviewed package hashes are required")


def same(value, required):
    return None if value is None else value == required


def job_steps(evidence, plan):
    payload = evidence.json("jobs")
    items = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(items, list) or payload.get("total_count") != len(items):
        evidence.check("GH003", None, detail="complete attempt-scoped jobs page required")
        return None
    jobs = [item for item in items if isinstance(item, dict) and item.get("name") == plan["job"]]
    if len(jobs) != 1:
        evidence.check("GH003", None, detail="unique named job unavailable")
        return None
    job = jobs[0]
    if job.get("run_id") != plan["runId"] or job.get("run_attempt") != plan["attempt"]:
        evidence.check("GH003", False, detail="job belongs to a different run or attempt")
        return None
    steps = job.get("steps")
    if not isinstance(steps, list):
        evidence.check("GH003", None)
        return job
    for gate in plan["gates"]:
        outcomes = [item.get("conclusion") for item in steps if isinstance(item, dict) and item.get("name") == gate]
        outcome = outcomes[0] if len(outcomes) == 1 else None
        evidence.check("GH003", same(outcome, "success"), gate, outcome)
    return job


def observed_runner(evidence, plan, job):
    material = evidence.json("runner")
    matched = isinstance(material, dict) and isinstance(job, dict) and (
        material.get("runId"), material.get("attempt"), material.get("jobId")
    ) == (plan["runId"], plan["attempt"], job.get("id"))
    if not matched:
        evidence.check("GH004", False if isinstance(material, dict) and job else None,
                       detail="runner evidence must identify the selected attempt and job")
        evidence.check("GH007", None)
        return
    raw = evidence.raw("scopedLog")
    if raw is None:
        evidence.check("GH004", None)
        evidence.check("GH007", None)
        return
    if material.get("scopedLogSha256") != evidence.observed["scopedLog"]:
        evidence.check("GH004", False, detail="observation digest differs from the scoped job log")
        evidence.check("GH007", None)
        return
    try:
        checkout, observed = parse(raw.decode("utf-8"), plan["job"], plan["checkoutStep"], plan["packageStep"])
    except UnicodeError:
        evidence.check("GH004", None, detail="job log encoding unavailable")
        evidence.check("GH007", None)
        return
    if material.get("engine") != checkout or material.get("packageHashes") != observed:
        evidence.check("GH004", False, detail="reported facts differ from the scoped job log")
        evidence.check("GH007", None)
        return
    evidence.check("GH004", same(checkout, plan["engine"]), detail=checkout)
    for name, expected in sorted(plan["packages"].items()):
        digest = observed.get(name) if isinstance(observed, dict) else None
        evidence.check("GH007", same(digest, expected), name, digest)


def archive(evidence, plan, scan):
    from .engine import JSON_LIMIT, digest, parse_json
    payload = evidence.json("artifacts")
    items = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(items, list) or payload.get("total_count") != len(items):
        evidence.check("GH005", None, detail="complete run artifacts page required")
        evidence.check("GH006", None)
        return
    artifacts = [item for item in items if isinstance(item, dict) and item.get("name") == plan["artifact"]]
    if len(artifacts) != 1:
        evidence.check("GH005", None, detail="required live artifact is absent or ambiguous")
        evidence.check("GH006", None)
        return
    item = artifacts[0]
    proof = item.get("workflow_run")
    if not isinstance(proof, dict) or (proof.get("id"), proof.get("head_sha")) != (plan["runId"], plan["headSha"]):
        evidence.check("GH005", False, detail="archive metadata references another run or source")
        evidence.check("GH006", None)
        return
    path = evidence.path("archive")
    expected = item.get("digest")
    if path is None or item.get("expired") is not False or not isinstance(expected, str) or scan:
        evidence.check("GH005", None)
        evidence.check("GH006", None)
        return
    matches = expected == "sha256:" + evidence.observed["archive"] and item.get("size_in_bytes") == path.stat().st_size
    evidence.check("GH005", matches, detail={"artifactId": item.get("id"), "digest": expected})
    if not matches:
        evidence.check("GH006", None)
        return
    try:
        with ZipFile(path) as archive_file:
            names = [info for info in archive_file.infolist() if info.filename == plan["sdkMember"]]
            if len(names) != 1 or names[0].file_size > JSON_LIMIT:
                evidence.check("GH006", None, detail="SDK receipt member absent, ambiguous, or oversized")
                return
            with archive_file.open(names[0]) as stream:
                raw = stream.read(JSON_LIMIT + 1)
            if len(raw) > JSON_LIMIT:
                raise ValueError("SDK receipt too large")
            sdk_receipt = parse_json(raw)
            native = sdk_receipt["evidence"]
            version = native["toolchain"]["sdkVersion"]
            passed = native["authoritative"] is True and sdk_receipt["verdict"] == "pass"
    except (BadZipFile, KeyError, OSError, TypeError, ValueError, RecursionError, RuntimeError):
        evidence.check("GH006", None, detail="completed native SDK receipt unavailable")
        return
    evidence.check("GH006", passed and version == plan["sdkVersion"],
                   detail={"sdkVersion": version, "memberSha256": digest(raw)})


def verify(evidence, scan):
    plan = evidence.expects
    expect(plan)
    run = evidence.json("run")
    if isinstance(run, dict):
        repo = (run.get("repository") or {}).get("full_name")
        identity = (repo, run.get("id"), run.get("run_attempt"), run.get("head_sha"), run.get("path"))
        expected = (plan["repository"], plan["runId"], plan["attempt"], plan["headSha"], plan["workflowPath"])
        evidence.check("GH001", identity == expected)
        completed = run.get("status") == "completed"
        evidence.check("GH002", same(run.get("conclusion"), "success") if completed else None)
    else:
        evidence.check("GH001", None)
        evidence.check("GH002", None)
    workflow = evidence.raw("workflow")
    if workflow is None:
        evidence.check("GH008", None)
    else:
        from .engine import digest
        evidence.check("GH008", digest(workflow) == plan["workflowSha256"])
    job = job_steps(evidence, plan)
    observed_runner(evidence, plan, job)
    archive(evidence, plan, scan)
