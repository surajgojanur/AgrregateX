# Local AgrregateX checkouts

This folder describes the related local directories shown in the desktop file manager. They are separate working directories that share Git history where registered as worktrees. Changes in one directory do not automatically appear in another.

| Folder | Local path | Git state observed on 2026-11-01 | Purpose |
|---|---|---|---|
| `AgrregateX` | `/home/god/Documents/github/AgrregateX` | `fix/issue34-complete-monitor-health-audit` at `aed320e` | Main working checkout for Issue #34 and the active draft PR #38. |
| `agrregatex-benchfix` | `/home/god/Documents/github/agrregatex-benchfix` | `feat/p2-benchmark-harness` at `4298dc2` | Benchmark worktree. |
| `AgrregateX-demo` | `/home/god/Documents/github/AgrregateX-demo` | Detached `HEAD` at `95928b8` | Demo worktree; commits made here are detached until a branch is created. |

The main checkout also has other registered worktrees under `/tmp`; see `git worktree list` for the live list. Branch names and commit IDs above are a snapshot and will change as work progresses.

## Safe workflow

- Open the folder whose branch owns the files you intend to edit. Confirm with `git status --short --branch` before changing anything.
- A worktree shares the repository's object database and branch references, but has its own checked-out files and index. Do not edit the same branch from multiple worktrees at once.
- The demo checkout is detached in the snapshot above. Create or switch to a named branch before committing there.
- Keep generated results, credentials, local environment files and other unrelated untracked files out of commits.
- Use `git worktree list` from the main checkout to inspect registrations. Do not remove a worktree until its changes are safely recorded and it is no longer needed.

The canonical copy of this guide lives in the main checkout at `workspace-checkouts/README.md`.
