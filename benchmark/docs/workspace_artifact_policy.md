# Frozen prospective incidental workspace artifact policy

Status: **FROZEN**  
Review date: 2026-08-09  
Policy ID: `tsb-incidental-workspace-artifacts-v1`

## Decision

The benchmark treats only an explicit, frozen allowlist of untracked runtime
caches as incidental workspace artifacts. Version 1 covers Python
`__pycache__` directories, `.pytest_cache` directories, and `.pyc` files.

The rule is prospective. It applies only to runs whose evidence directory was
prepared with `workspace_artifact_policy.json`. Earlier frozen runs, including
`validation-L1-01-devin-r01-a03`, retain their original workspace, hash,
`final.diff`, and evidence contract and must not be rewritten.

## Treatment

For a policy-enabled run:

1. `create_run` copies the policy into the evidence directory and writes an
   empty `incidental_artifacts.json` placeholder.
2. The run workspace's private `.git/info/exclude` receives the allowlisted
   cache patterns. This file is Git metadata, is not exposed as task content,
   and is excluded from the frozen workspace hash.
3. The finalizer scans the physically frozen workspace. Each matching
   **untracked** file is recorded with its relative POSIX path, classification,
   byte size, and SHA-256 digest.
4. Inventoried files remain on disk and remain auditable, but they are omitted
   from `final.diff`. The finalizer never deletes or edits them.
5. A tracked file is never exempt merely because its name matches the policy.
   All tracked-file changes remain in `final.diff`.
6. Every nonmatching untracked file remains in `final.diff`.

This makes the semantic workspace hash and final diff consistent without
silently discarding evidence. The policy patterns must be a subset of each
task's frozen fixture-hash exclusions. A mismatch fails run preparation or
finalization.

## Freeze review

The candidate was reviewed and promoted to `FROZEN` on 2026-08-09. Review
confirmed the narrow untracked-only allowlist, physical preservation and
digest inventory, tracked/nonmatching diff retention, fixture-hash exclusion
alignment for all four representative tasks, schema validation, finalizer and
evidence-validator coverage, and unchanged treatment of historical runs.

Freezing this subpolicy does not authorize a pilot or main run. `create_run`
requires both this policy to be `FROZEN` and the complete experiment freeze
manifest plus its amendment log to pass the fail-closed execution gate. The
future sealed evaluation bundle binds the exact policy bytes; until that full
manifest is sealed, pilot/main creation remains blocked.

Adding a new artifact class requires prospective review, tests, regenerated
configuration hashes, a replacement frozen policy, and an amendment after the
experiment freeze. Broad globs, source
files, databases, logs, generated application bundles, and arbitrary agent
outputs must not be classified as incidental by default.
