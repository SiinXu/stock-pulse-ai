# Supply-Chain Maintenance

This document defines the review, update, exception, and rollback contract for
repository dependency inputs and GitHub Actions. It implements the workflow
controls required by `SUPPLY-02`, `SUPPLY-03`, and the applicable parts of
`SUPPLY-05` in `docs/security-baseline.md`. Python dependency resolution is
tracked in #326 and will be added to this contract with its resolved inputs.

## GitHub Actions

Every external Action reference must use a reviewed, lowercase, 40-character
commit SHA. The same line must end with the exact upstream release identity in
full `major.minor.patch` form, for example:

```yaml
uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5.1.0
```

Do not use a branch, major tag, floating tag, shortened SHA, a major-only
release comment such as `# v5`, or an unverified commit. Resolve annotated tags
to the commit object rather than pinning the tag
object. `.github/dependabot.yml` checks for GitHub Actions updates weekly;
Dependabot pull requests must preserve the SHA pin and release comment.

For an Action update:

1. Read the upstream release notes and identify behavior, input, runner, and
   permission changes.
2. Verify that the release tag resolves to the proposed commit in the upstream
   repository. Record the exact release in the inline comment.
3. Update every use of that Action together. Do not change workflow triggers or
   job topology as part of a pin refresh.
4. Run the workflow guard, YAML parsing, and `actionlint`, then require the
   repository's blocking CI checks before merge.

## Token Permissions

Every workflow sets top-level `permissions: {}`. Every job declares its own
mapping, including read-only jobs. The guard records every scope and access
level in `APPROVED_JOB_PERMISSIONS`; any expansion or narrowing of read or write
access must update that executable contract in the same reviewed change.
Job-level write scopes are limited to the following operations:

| Workflow job | Approved write scope | Purpose |
| --- | --- | --- |
| `auto-tag.yml / tag` | `contents` | Create an opt-in version tag. |
| `create-release.yml / release` | `contents` | Create a GitHub Release. |
| `desktop-release.yml / publish-release` | `contents` | Publish desktop assets to an existing release. |
| `docker-publish.yml / build-and-push` | `packages` | Push the release image to GHCR. |
| `ghcr-dockerhub.yml / build-and-push` | `packages` | Push a manually requested image to GHCR. |
| `issue-claim.yml / claim` | `issues` | Assign and comment on an issue claim. |
| `pr-review.yml / labeler` | `pull-requests` | Add pull-request labels. |
| `pr-review.yml / comment` | `pull-requests` | Publish the automated review comment. |
| `stale.yml / stale` | `issues`, `pull-requests` | Mark and close inactive items. |

The table highlights privileged operations; `APPROVED_JOB_PERMISSIONS` also
contains every read-only job permission. Docker publish
jobs do not request `id-token: write` because they authenticate with registry
credentials and do not perform OIDC attestation.

The PR Review workflow remains a `pull_request` workflow. Fork runs receive no
repository secrets, and its secret- or write-dependent jobs retain explicit
same-repository conditions. Pinning and permission declarations must not weaken
that isolation.

## Time-Bounded Exceptions

Exceptions are permitted only when an external Action cannot immediately use an
immutable commit. Add one exact entry to
`scripts/workflow_supply_chain_exceptions.json` with these fields:

```json
{
  "workflow": ".github/workflows/example.yml",
  "action": "owner/action",
  "ref": "v1",
  "expires": "2030-01-31",
  "owner": "security-maintainers",
  "reason": "Link to the tracked blocker and remediation plan."
}
```

The owner and reason must be specific, the expiry must be within 30 days, and
the exception must match one workflow, Action, and ref exactly. Expired,
overlong, duplicate, and unused exceptions fail CI. Exceptions do not waive
release comments, workflow-level deny-by-default permissions, job-level
permission declarations, or the complete reviewed permission allowlist. Approval from a
maintainer responsible for security or CI is required in the pull request.

## Validation And Rollback

Run:

```bash
python scripts/check_workflow_supply_chain.py --self-test
python scripts/check_workflow_supply_chain.py
python -c "import glob,yaml;[yaml.safe_load(open(path)) for path in glob.glob('.github/workflows/*.yml')]"
actionlint .github/workflows/*.yml
```

The self-tests cover compliant manifests, a representative immutable pin
update, conventionally formatted and flow-mapped movable references, floating
release comments, missing permission declarations, top-level write access,
active/expired/overlong exceptions, and unapproved read or write scopes.

For a bad Action update, revert the affected workflow file to its last reviewed
SHA and release comment, then rerun the same checks. For a permission regression,
revert the affected workflow and the matching executable allowlist/documentation
entry together. These workflow-only rollbacks do not require application data or
configuration restoration.
