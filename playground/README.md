# GitHubActionsAssay playground

The wrapper selects the evidence plan for CSharpAssay.Playground GitHub Actions run `44739374322`, attempt `1`. The unit suite exercises the offline verifier with controlled inputs.

Run the source commands from the repository root with Python 3. Assemble
an input bundle when the named archive and other artifacts are available.
[Run evidence guide](../docs/native.md)

```sh
python3 playground/run.py
```

The v2 receipt preserves command arguments, exits, and raw logs for
readiness, catalogue explanations, source tests, the showcase verification,
and the provisional scan control. The scan control expects
`Inconclusive` with exit `2`. The wrapper propagates a failed or
incomplete showcase and refuses a contradictory receipt and process exit.

For the native receipt alone, run each command independently.

```sh
PYTHONPATH=src python3 -m github_actions_assay scan --policy examples/playground-44739374322.json
PYTHONPATH=src python3 -m github_actions_assay verify --policy examples/playground-44739374322.json
```

Both commands report `Inconclusive` with exit `2` against the bare checked-in plan because required files such as the run metadata, workflow, logs and archive are missing. Verification of an assembled bundle covers the named run and attempt.

Pass the assembled evidence policy to exercise the named run and attempt.

```sh
python3 playground/run.py --policy artifacts/run-44739374322/policy.json
```
