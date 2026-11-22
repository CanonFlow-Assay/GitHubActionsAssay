# CSharpAssay Playground run evidence

The two plans in examples bind the published Playground commit da724b6.
Run 44739374322 used the intended engine commit, .NET SDK 11.0.100,
the planned CsAssay.Tool hash and the required saga and Playground gates.
The downloaded ZIP was checked against GitHub's reported artifact digest.
Run 44516824487 failed package preparation and skipped the required gates.
Its retained job metadata establishes the failure. Missing checkout and
archive evidence limit that separate receipt.

- [Pinned Playground run](https://github.com/CanonFlow-Assay/CSharpAssay.Playground/actions/runs/44739374322)
- [Earlier Playground run](https://github.com/CanonFlow-Assay/CSharpAssay.Playground/actions/runs/44516824487)
- [GitHub jobs API](https://docs.github.com/en/rest/actions/workflow-jobs)
- [GitHub artifacts API](https://docs.github.com/en/rest/actions/artifacts)

## Reproduce while the artifact is available

Collect the planned run, attempt jobs, run artifact list, scoped job log,
archive, and exact workflow bytes in a disposable directory. Use the
plan's source revision when obtaining the workflow.

~~~sh
repo=CanonFlow-Assay/CSharpAssay.Playground
run=44739374322
raw=$(mktemp -d)
gh api "repos/$repo/actions/runs/$run" > "$raw/$run-run.json"
gh api "repos/$repo/actions/runs/$run/attempts/1/jobs" > "$raw/$run-jobs.json"
gh api "repos/$repo/actions/runs/$run/artifacts" > "$raw/$run-artifacts.json"
gh run view "$run" --attempt 1 --repo "$repo" --log |
  rg 'Checkout matching CSharpAssay source|Build local .NET 11 packages' > "$raw/$run-selected.log"
gh api "repos/$repo/actions/artifacts/14631422348/zip" > "$raw/$run-archive.zip"
gh api -H 'Accept: application/vnd.github.raw+json' \
  "repos/$repo/contents/.github/workflows/playground.yml?ref=da724b67cc4e27f2698ac10f247a8f08065c9ec1" \
  > "$raw/playground.yml"
python3 eng/assemble.py --plan "examples/playground-$run.json" \
  --input "$raw" --out "artifacts/run-$run"
PYTHONPATH=src python3 -m github_actions_assay verify \
  --policy "artifacts/run-$run/policy.json" --out "artifacts/run-$run/receipt.json"
~~~

Keep raw logs out of the repository. The quoted GitHub CLI log format is
part of the initial collection contract. Future compatible producer steps
can emit exact package name and SHA-256 pairs using a line beginning with
##assay-package-sha256. Expired artifacts or unresolved job markers remain
missing evidence. The profile checks supplied GitHub metadata and log bytes.
It has no independent signature or attestation for those inputs.
