# Evidence contract

A policy has schemaVersion 1, the named profile, a files map from evidence
role to project-relative filename, and the profile's expects object. The
policy directory is the scope root. JSON uses UTF-8 and unique properties.
The verifier binds the policy, named files and producer bytes with SHA-256.
The 4 MiB structured input limit and 128 MiB bound-file limit keep the initial
lane finite. Paths use regular files without symlink components.

- doctor reports readiness.
- catalog and explain expose the finite implemented checks.
- scan produces provisional observations.
- verify runs the profile's checks over the declared inputs.
- assess retains the verification receipt in an additive envelope.

Pass exits 0. A known violation exits 1 as Fail. Missing or unavailable
required evidence exits 2 as Inconclusive. Invalid policy, invocation or
publication exits 3 as ToolFailure. Fail keeps independent evidence gaps.
A clean scan is Inconclusive. The authoritative flag describes completeness
within the selected evidence scope.

Verification is offline and consumes evidence as data. Collection is a
separate step. Hashes bind observed bytes and do not authenticate the
collection origin. Inputs are re-observed after verification. The output
writer stages an atomic replacement in an existing directory and refuses
overlap with inputs, symlink paths and multiply linked output targets.
