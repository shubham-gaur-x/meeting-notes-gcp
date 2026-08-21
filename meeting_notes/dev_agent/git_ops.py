"""Git worktree operations for the dev agent — one worktree per ticket.

**One adaptation from v5.** v5 assumed a long-lived `REPO_DIR` bind-mounted
into a Docker Compose service, so `ensure_repo_cloned` had a "already exists,
just fetch" branch. Cloud Run Jobs get a fresh, ephemeral filesystem on every
execution — that branch is dead code in this environment, not a path worth
keeping unreachable, so it is removed rather than ported unchanged.
"""

from __future__ import annotations

import asyncio

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


async def create_worktree(repo_dir: str, work_dir: str, branch_name: str) -> None:
    await _run_git(["fetch", "origin", "main"], cwd=repo_dir)
    # Remove a stale worktree/branch from a previous failed attempt (ignore errors).
    try:
        await _run_git(["worktree", "remove", "--force", work_dir], cwd=repo_dir)
    except GitError:
        pass
    try:
        await _run_git(["branch", "-D", branch_name], cwd=repo_dir)
    except GitError:
        pass

    await _run_git(
        ["worktree", "add", "-b", branch_name, work_dir, "origin/main"], cwd=repo_dir
    )
    log.info("git_ops.worktree_created", branch=branch_name, work_dir=work_dir)


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

