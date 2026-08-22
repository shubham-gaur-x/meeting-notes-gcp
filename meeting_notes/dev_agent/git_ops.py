"""Git worktree operations for the dev agent — one worktree per ticket.

**One adaptation from v5.** v5 assumed a long-lived `REPO_DIR` bind-mounted
into a Docker Compose service, so `ensure_repo_cloned` had a "already exists,
just fetch" branch. Cloud Run Jobs get a fresh, ephemeral filesystem on every
execution — that branch is dead code in this environment, not a path worth
keeping unreachable, so it is removed rather than ported unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

log = structlog.get_logger()


class GitError(RuntimeError):
    pass


def authed_remote_url(owner: str, repo: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{owner}/{repo}.git"


async def _run_git(args: list[str], cwd: str | None = None) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise GitError(stderr.decode(errors="replace").strip())
    return stdout.decode(errors="replace").strip()


async def ensure_repo_cloned(repo_dir: str, owner: str, repo: str, token: str) -> None:
    """Always a fresh clone. Cloud Run Jobs have no persistent filesystem
    between executions, so there is never an existing checkout to fetch into."""
    url = authed_remote_url(owner, repo, token)
    log.info("git_ops.clone", repo_dir=repo_dir, owner=owner, repo=repo)
    await _run_git(["clone", url, repo_dir])


async def default_branch(repo_dir: str, *, run: Any = None) -> str:
    """The repository's own default branch.

    Assuming "main" broke the very first live run against a repo whose default
    is `master` -- `fatal: couldn't find remote ref main`, before the agent had
    done anything at all. `origin/HEAD` is what the remote actually points at;
    a fresh clone can leave it unset, so fall back to probing the common names
    rather than guessing one of them.
    """
    run = run or _run_git
    try:
        ref = await run(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=repo_dir)
        name = (ref or "").strip().rsplit("/", 1)[-1]
        if name:
            return name
    except GitError:
        pass
    for candidate in ("main", "master", "develop"):
        try:
            await run(["rev-parse", "--verify", f"refs/remotes/origin/{candidate}"], cwd=repo_dir)
            return candidate
        except GitError:
            continue
    return "main"


async def create_worktree(
    repo_dir: str, work_dir: str, branch_name: str, *, run: Any = None
) -> str:
    """Branch a worktree off the repository's default branch. Returns that
    branch, so the caller can tell the agent which base to open the PR against."""
    run = run or _run_git
    base = await default_branch(repo_dir, run=run)
    await run(["fetch", "origin", base], cwd=repo_dir)
    # Remove a stale worktree/branch from a previous failed attempt (ignore errors).
    try:
        await run(["worktree", "remove", "--force", work_dir], cwd=repo_dir)
    except GitError:
        pass
    try:
        await run(["branch", "-D", branch_name], cwd=repo_dir)
    except GitError:
        pass

    await run(
        ["worktree", "add", "-b", branch_name, work_dir, f"origin/{base}"], cwd=repo_dir
    )
    log.info("git_ops.worktree_created", branch=branch_name, work_dir=work_dir, base=base)
    return base


async def remove_worktree(
    repo_dir: str, work_dir: str, branch_name: str, ignore_errors: bool = False
) -> None:
    try:
        await _run_git(["worktree", "remove", "--force", work_dir], cwd=repo_dir)
        await _run_git(["branch", "-D", branch_name], cwd=repo_dir)
        log.info("git_ops.worktree_removed", branch=branch_name)
    except GitError as exc:
        if ignore_errors:
            log.warning("git_ops.worktree_remove_failed", branch=branch_name, error=str(exc))
        else:
            raise

