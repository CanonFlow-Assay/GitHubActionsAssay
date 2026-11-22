"""Parse actual checkout HEAD and package identities from scoped GitHub logs."""

import re


def parse(log, job, checkout_step, package_step):
    outputs = {checkout_step: [], package_step: []}
    for raw in log.splitlines():
        columns = raw.split("\t", 2)
        if len(columns) != 3 or columns[0] != job or columns[1] not in outputs:
            continue
        stamp, separator, message = columns[2].lstrip("\ufeff").partition(" ")
        if separator and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", stamp):
            outputs[columns[1]].append(message.strip())

    checkout = outputs[checkout_step]
    repos = set()
    heads = set()
    for index, line in enumerate(checkout):
        match = re.fullmatch(r"(?:Syncing repository:|repository:) ([-.A-Za-z0-9_]+/[-.A-Za-z0-9_]+)", line)
        if match:
            repos.add(match[1])
        if line.startswith("[command]") and line.endswith("git log -1 --format=%H") and index + 1 < len(checkout):
            if re.fullmatch(r"[a-f0-9]{40}", checkout[index + 1]):
                heads.add(checkout[index + 1])
    engine = {"repository": next(iter(repos)), "sha": next(iter(heads))} if len(repos) == len(heads) == 1 else None

    values = {match[1] for line in outputs[package_step]
              if (match := re.fullmatch(r'"packageSha256": "([a-f0-9]{64})",?', line))}
    packages = {"CsAssay.Tool": next(iter(values))} if len(values) == 1 else {}
    declared = {}
    for line in outputs[package_step]:
        matched = re.fullmatch(r"##assay-package-sha256 ([A-Za-z0-9_.-]+) ([a-f0-9]{64})", line)
        if matched:
            declared.setdefault(matched[1], set()).add(matched[2])
    for package, digests in declared.items():
        if package in packages:
            digests.add(packages[package])
        if len(digests) == 1:
            packages[package] = next(iter(digests))
        else:
            packages.pop(package, None)
    return engine, packages
