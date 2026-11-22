"""Bounded evidence inputs, native checks, and four-state receipts."""

import argparse
import hashlib
from importlib.resources import files
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile

from . import adapter

RESOURCE = files(__package__)
EXIT = {"Pass": 0, "Fail": 1, "Inconclusive": 2, "ToolFailure": 3}
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
JSON_LIMIT = 4 * 1024 * 1024
FILE_LIMIT = 128 * 1024 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parse_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON property")
            result[key] = value
        return result

    def no_constant(_):
        raise ValueError("nonfinite JSON number")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=no_constant)


def regular(path, limit):
    if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_file():
        raise ValueError("expected a regular file without symbolic links")
    if path.stat().st_size > limit:
        raise ValueError("file size exceeds the scope limit")
    return path


def bounded_bytes(path, limit=JSON_LIMIT):
    with regular(path, limit).open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("file size exceeds the scope limit")
    return content


def file_hash(path):
    result = hashlib.sha256()
    count = 0
    with regular(path, FILE_LIMIT).open("rb") as stream:
        while block := stream.read(1024 * 1024):
            count += len(block)
            if count > FILE_LIMIT:
                raise ValueError("file size exceeds the scope limit")
            result.update(block)
    return result.hexdigest()


def relative_file(name):
    if not isinstance(name, str) or not name or len(name) > 512 or "\\" in name or "\0" in name:
        raise ValueError("expected a bounded relative filename")
    if any(piece in ("", ".", "..") for piece in name.split("/")):
        raise ValueError("expected a canonical relative filename")
    return PurePosixPath(name)


def load_policy(raw, profile):
    value = parse_json(raw)
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "profile", "files", "expects"}:
        raise ValueError("policy requires schemaVersion, profile, files, and expects")
    if type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1 or value["profile"] != profile:
        raise ValueError("unsupported policy schema or profile")
    paths = value["files"]
    if not isinstance(paths, dict) or not 1 <= len(paths) <= 64 or not isinstance(value["expects"], dict):
        raise ValueError("expected a bounded file map and expectations object")
    for role, filename in paths.items():
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", role):
            raise ValueError("invalid evidence role")
        relative_file(filename)
    if len(set(paths.values())) != len(paths):
        raise ValueError("each evidence role requires a distinct file")
    return value


class Evidence:
    def __init__(self, root, policy, checks):
        self.expects = policy["expects"]
        self.paths = {role: root / relative_file(name) for role, name in policy["files"].items()}
        self.observed = {}
        self.names = policy["files"]
        self.checks = []
        self.missing = []
        self.errors = []
        self.rules = checks

    def bind(self):
        for role, path in sorted(self.paths.items()):
            try:
                self.observed[role] = file_hash(path)
            except (OSError, ValueError):
                self.missing.append(f"{role}: declared file unavailable")

    def path(self, role):
        if role not in self.observed:
            self.missing.append(f"{role}: evidence unavailable")
            return None
        return self.paths[role]

    def raw(self, role, limit=JSON_LIMIT):
        path = self.path(role)
        if path is None:
            return None
        try:
            content = bounded_bytes(path, limit)
            if digest(content) != self.observed[role]:
                raise ValueError("input changed")
            return content
        except (OSError, ValueError):
            self.missing.append(f"{role}: file unavailable or changed during reading")
            return None

    def json(self, role):
        raw = self.raw(role)
        if raw is None:
            return None
        try:
            return parse_json(raw)
        except (ValueError, RecursionError):
            self.missing.append(f"{role}: malformed JSON")
            return None

    def check(self, rule, passed, subject=None, detail=None):
        if rule not in self.rules or (passed is not None and type(passed) is not bool):
            raise RuntimeError("invalid check outcome")
        status = "untested" if passed is None else "passed" if passed else "failed"
        self.checks.append({"rule": rule, "outcome": status, "subject": subject, "detail": detail})
        if passed is None:
            self.missing.append(rule + (f"/{subject}" if subject else "") + ": evidence incomplete")

    def reobserve(self):
        for role, before in self.observed.items():
            try:
                same = file_hash(self.paths[role]) == before
            except (OSError, ValueError):
                same = False
            if not same:
                self.missing.append(f"{role}: observed input changed or became unavailable")


def producer_hash():
    names = ("__init__.py", "__main__.py", "engine.py", "adapter.py", "catalogue.json", *adapter.EXTRA_FILES)
    mapped = {name: digest(RESOURCE.joinpath(name).read_bytes()) for name in names}
    return digest(canonical(mapped).encode())


def audit(policy_path, catalogue, mode):
    raw = bounded_bytes(policy_path)
    policy = load_policy(raw, catalogue["profile"])
    evidence = Evidence(policy_path.parent, policy, {rule["id"] for rule in catalogue["rules"]})
    identity = producer_hash()
    evidence.bind()
    adapter.verify(evidence, mode == "scan")
    if mode == "scan":
        evidence.missing.append("scan is provisional")
    if not evidence.checks:
        evidence.missing.append("no check executed")
    evidence.reobserve()
    try:
        if bounded_bytes(policy_path) != raw or producer_hash() != identity:
            evidence.missing.append("policy or producer changed during verification")
    except (OSError, ValueError):
        evidence.missing.append("policy or producer became unavailable")

    if evidence.errors:
        verdict = "ToolFailure"
    elif any(row["outcome"] == "failed" for row in evidence.checks):
        verdict = "Fail"
    else:
        verdict = "Inconclusive" if evidence.missing else "Pass"
    result = {
        "schemaVersion": "portfolio-assay-receipt/1",
        "assay": catalogue["assay"], "profile": catalogue["profile"], "mode": mode,
        "producerSha256": identity, "policySha256": digest(raw),
        "verdict": verdict, "authoritative": not (evidence.errors or evidence.missing),
        "inputs": [{"role": role, "path": evidence.names[role], "sha256": value}
                   for role, value in sorted(evidence.observed.items())],
        "checks": evidence.checks, "missingEvidence": sorted(set(evidence.missing)),
        "toolFailures": sorted(set(evidence.errors)),
    }
    return result, [policy_path, *evidence.paths.values()]


def publish(result, output, inputs):
    if any(item.is_symlink() for item in (output, *output.parents)):
        raise ValueError("output may not traverse symbolic links")
    if output.exists() and (not output.is_file() or output.stat().st_nlink != 1):
        raise ValueError("output must be a single-link regular file")
    if any(output == path or (output.exists() and path.exists() and output.samefile(path)) for path in inputs):
        raise ValueError("receipt output overlaps an input")
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as stream:
        staged = Path(stream.name)
        try:
            stream.write(canonical(result).encode())
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            staged.replace(output)
        finally:
            staged.unlink(missing_ok=True)


def failure(message):
    return {"schemaVersion": "portfolio-assay-receipt/1", "verdict": "ToolFailure",
            "authoritative": False, "error": message}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print(canonical(failure("invalid command line")), end="")
        raise SystemExit(3)


def main():
    try:
        catalogue = parse_json(RESOURCE.joinpath("catalogue.json").read_bytes())
        parser = Parser(description=catalogue["assay"] + " bounded evidence verification")
        commands = parser.add_subparsers(dest="mode", required=True)
        commands.add_parser("doctor")
        commands.add_parser("catalog")
        commands.add_parser("explain").add_argument("rule")
        for mode in ("scan", "verify", "assess"):
            command = commands.add_parser(mode)
            command.add_argument("--policy", type=Path, required=True)
            command.add_argument("--out", type=Path)
        args = parser.parse_args()
        if args.mode == "doctor":
            print(canonical({"scope": "readiness", **adapter.doctor()}), end="")
            return 0
        if args.mode == "catalog":
            print(canonical(catalogue), end="")
            return 0
        if args.mode == "explain":
            row = next((rule for rule in catalogue["rules"] if rule["id"] == args.rule), None)
            print(canonical(row or failure("unknown rule")), end="")
            return 0 if row else 3
        path = Path(os.path.abspath(args.policy))
        receipt, inputs = audit(path, catalogue, args.mode)
        value = receipt
        if args.mode == "assess":
            value = {"schemaVersion": "portfolio-assay-assessment/1",
                     "verdict": receipt["verdict"], "receipt": receipt}
        if args.out:
            try:
                inputs.append(Path(os.path.abspath(sys.argv[0])))
                if isinstance(RESOURCE, Path):
                    inputs.extend(file for file in RESOURCE.iterdir() if file.is_file())
                publish(value, Path(os.path.abspath(args.out)), inputs)
            except (OSError, ValueError):
                value = {**failure("unavailable output"), "observed": value}
        print(canonical(value), end="")
        return EXIT[value["verdict"]]
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, RecursionError):
        print(canonical(failure("invalid policy or verifier execution")), end="")
        return 3
