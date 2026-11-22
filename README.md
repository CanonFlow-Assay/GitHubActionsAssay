# GitHubActionsAssay

Verify a recorded GitHub Actions run against an independent plan. The
bound-run profile checks the source and workflow identity, run attempt,
required job steps, actual secondary checkout, the SDK recorded by an
authoritative native receipt, observed package hashes and the bytes of the
required GitHub artifact.

The initial adapter supports the CSharpAssay Playground evidence format.
It parses checkout HEAD from the result of git log in the selected step.
It reads the native SDK from the pinned JSON member of the verified ZIP.
It checks package identities recorded by the named producer step.
The scope starts with a complete attempt-scoped jobs page and a single
required artifact. The verifier reads supplied data offline.

## Run

~~~sh
python3 eng/qualify.py
PYTHONPATH=src python3 -m github_actions_assay catalog
PYTHONPATH=src python3 -m github_actions_assay verify --policy path/to/execution/policy.json
~~~

See the [evidence contract](CONTRACT.md) and [Playground reproduction](docs/native.md).
The deterministic zipapp is built under artifacts/. Apache-2.0.
