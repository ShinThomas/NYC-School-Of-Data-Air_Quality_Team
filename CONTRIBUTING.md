# Contributing

## Branch and review workflow

1. Start from the latest `dev` and work on your own branch.
2. Commit and push to your branch. Do not push project work directly to `dev` or `main`.
3. Open a pull request with base `dev` and your branch as the head.
4. Request review from @ShinThomas. Address review feedback and wait for his approval before merging.
5. Thomas manages release pull requests from `dev` into `main`.
6. After a merge, sync your working branch with `dev` before beginning more work. Avoid force pushes to shared branches.

`main` holds reviewed releases; `dev` integrates reviewed team contributions. Protection rules must be configured in repository settings to enforce this policy; documentation alone does not enforce it.

## Team working branches

| Teammate | Working branch |
| --- | --- |
| Thomas Shin | `thomas-shin` |
| Sam Cowan | `sam-cowan` |
| Alexis Cruz | `small-building-fuel` |
| Miriam Dulin | `mapping` |
| Kyle Yang | `kyle-yang` |
| Daniel Lin | `airdatasort` |

Existing task branches are retained to preserve work and open PRs. These are coordination assignments, not GitHub access restrictions. Additional task branches can use `<name>/<task>` and should start from `dev`.

## Syncing an existing branch

Commit or stash local work first, then:

```bash
git fetch origin
git switch YOUR_BRANCH
git merge origin/dev
git push origin YOUR_BRANCH
```

## Pull request expectations

- Explain the change, related issue, and how you checked the result.
- Document data sources, units, dependencies, and reproducible run instructions.
- Keep credentials and local environment files out of Git; use `.env.example` with placeholders when needed.
- Exclude `.DS_Store`, caches, and unnecessary generated files.
- Keep PRs focused and resolve merge conflicts before requesting final review.
- Use merge commits for `dev` to `main` releases to preserve the relationship between the two long-lived branches.

The CODEOWNERS file requests Thomas's review for changes once a PR is ready for review. Required code-owner approval must also be enabled in branch protection or rulesets. Thomas cannot approve his own PRs; his release PRs need a designated second reviewer or an explicitly configured owner exception.
