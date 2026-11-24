"""Build an evaluation task set from a repository's merged pull requests.

Each task is one merged PR replayed from its parent commit:

* the agent starts from the repository as it was *before* the merge
  (``base_sha`` — the first parent of the merge/squash commit),
* the prompt is the PR title and description (what a developer would have
  handed the agent),
* the reference solution is the diff that actually merged.

Grading compares the agent's diff against that reference, so the task set
reflects the work your team really does rather than a public benchmark.

Two task modes are produced:

* ``edit`` — the agent changes the code. Split into ``quick_edit`` (small,
  single-file) and ``feature`` (multi-file) categories by diff size.
* ``plan`` — the agent explores read-only and returns an implementation plan,
  which is graded against the files and approach of the merged change.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CACHE_DIR = Path(os.environ.get("CODING_EVAL_CACHE", Path.home() / ".cache" / "coding-eval"))

# Paths whose diffs say nothing about whether the agent understood the task.
DEFAULT_EXCLUDES = [
    "*.lock",
    "*lock.json",
    "*.lockb",
    "go.sum",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.gif",
    "*.pdf",
    "*.ipynb",
    "vendor/*",
    "third_party/*",
    "node_modules/*",
    "dist/*",
    "*_pb2.py",
    "*_pb2_grpc.py",
    "*.pb.go",
    "*.generated.*",
    "CHANGELOG*",
    "CHANGES*",
    "HISTORY*",
    "NEWS*",
]
# Changes that only touch CI/tooling config are not coding-agent work.
CI_ONLY_PREFIXES = (".github/", ".gitlab-ci", ".circleci/", ".pre-commit-config", ".buildkite/", "renovate.json")
_CHORE_TITLE = re.compile(
    r"^(?:bump |update (?:pre-?commit|dependencies|deps)\b|\[pre-commit\.ci\]|chore\(deps)", re.IGNORECASE
)
DOC_SUFFIXES = (".md", ".mdx", ".rst", ".txt", ".adoc")
BOT_AUTHORS = ("dependabot", "renovate", "github-actions", "pre-commit-ci", "release-please", "[bot]")

_SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
_MERGE_PR = re.compile(r"^Merge pull request #(\d+) from ")
_GITHUB = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$")


class TaskBuildError(RuntimeError):
    """A merged change found while scanning history, before filtering."""

    pass


def _git(repo_dir: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise TaskBuildError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def _cache_key(repo: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", repo.rstrip("/").split("/")[-1].removesuffix(".git")).strip("-")
    return f"{stem}-{hashlib.sha1(repo.encode()).hexdigest()[:8]}"


def repo_cache_dir(repo: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> Path:
    """Path of the bare mirror used for ``repo`` (a URL or a local path)."""
    path = Path(repo).expanduser()
    if path.exists():
        return path.resolve()
    return cache_dir / "repos" / f"{_cache_key(repo)}.git"


def prepare_repo(repo: str, cache_dir: Path = DEFAULT_CACHE_DIR, refresh: bool = True) -> Path:
    """Return a local git directory for ``repo``, cloning a bare mirror if needed.

    ``repo`` can be a local checkout (used in place, never modified) or any URL
    ``git clone`` accepts. Private GitHub repos work if your git credentials do.
    """
    path = repo_cache_dir(repo, cache_dir)
    if Path(repo).expanduser().exists():
        _git(path, "rev-parse", "--git-dir")
        return path
    if path.exists():
        if refresh:
            _git(path, "fetch", "--prune", "origin", "+refs/heads/*:refs/heads/*")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(["git", "clone", "--bare", repo, str(path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        shutil.rmtree(path, ignore_errors=True)
        raise TaskBuildError(f"git clone {repo} failed: {result.stderr.strip()}")
    return path


def default_branch(repo_dir: Path) -> str:
    """The branch HEAD points at in the mirror, falling back to main/master/develop."""
    ref = _git(repo_dir, "symbolic-ref", "--quiet", "HEAD", check=False).strip()
    if ref:
        return ref.removeprefix("refs/heads/")
    for candidate in ("main", "master", "develop"):
        if _git(repo_dir, "rev-parse", "--verify", "--quiet", candidate, check=False).strip():
            return candidate
    raise TaskBuildError("could not determine the default branch; pass branch= explicitly")


@dataclass
class _Candidate:
    sha: str
    base_sha: str
    pr_number: int | None
    subject: str
    body: str
    author: str
    date: str


def _scan_history(repo_dir: Path, branch: str, limit: int) -> list[_Candidate]:
    fmt = "%H%x00%P%x00%an%x00%cI%x00%s%x00%b%x1e"
    out = _git(repo_dir, "log", "--first-parent", f"--max-count={limit}", f"--format={fmt}", branch)
    candidates = []
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, parents, author, date, subject, body = (record.split("\x00") + [""] * 6)[:6]
        parent_list = parents.split()
        if not parent_list:
            continue  # root commit
        pr = None
        if m := _MERGE_PR.match(subject):
            pr = int(m.group(1))
        elif m := _SQUASH_PR.search(subject):
            pr = int(m.group(1))
        candidates.append(_Candidate(sha, parent_list[0], pr, subject, body.strip(), author, date))
    return candidates


def _is_excluded(path: str, excludes: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(name, pat) for pat in excludes)


def _numstat(repo_dir: Path, base: str, sha: str) -> list[tuple[str, int | None, int | None]]:
    rows = []
    for line in _git(repo_dir, "diff", "--numstat", "-M", base, sha).splitlines():
        added, removed, path = line.split("\t", 2)
        if " => " in path:  # rename: keep the destination path
            path = re.sub(r"\{[^}]* => ([^}]*)\}", r"\1", path).split(" => ")[-1]
        rows.append((path, None if added == "-" else int(added), None if removed == "-" else int(removed)))
    return rows


def _github_coords(repo: str) -> tuple[str, str] | None:
    m = _GITHUB.search(repo)
    return (m.group("owner"), m.group("repo")) if m else None


def _github_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    if shutil.which("gh"):
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def _fetch_pr(owner: str, repo: str, number: int, token: str | None) -> dict[str, Any] | None:
    return _fetch_json(f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}", token)


def _fetch_json(url: str, token: str | None) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "coreweave-coding-agent-eval",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)", re.IGNORECASE)


def _linked_issues(owner: str, repo: str, body: str, token: str | None, limit: int = 2) -> list[str]:
    """Bodies of issues the PR says it closes — often the real specification."""
    out = []
    for num in list(dict.fromkeys(_CLOSES.findall(body or "")))[:limit]:
        issue = _fetch_json(f"https://api.github.com/repos/{owner}/{repo}/issues/{num}", token)
        if issue and not issue.get("pull_request"):
            out.append(f"### Issue #{num}: {issue.get('title', '')}\n\n{issue.get('body') or ''}")
    return out


_FENCED_PATCH = re.compile(r"```(?:diff|patch)\b.*?```", re.DOTALL)
_TRAILERS = re.compile(r"^(?:Co-Authored-By|Signed-off-by|🤖 Generated with).*$", re.MULTILINE | re.IGNORECASE)


def _clean_description(text: str, limit: int = 4000) -> str:
    """Drop pasted patches and trailers so the prompt states the goal, not the answer."""
    text = _FENCED_PATCH.sub("[patch omitted]", text or "")
    text = _TRAILERS.sub("", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)  # PR template comments
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:limit] + ("\n[description truncated]" if len(text) > limit else "")


EDIT_PROMPT = """You are working in a git repository checked out at the commit just before a change was merged.
Make the change described below. Edit files in the repository directly; you do not need to commit.
When the change is complete, call the `finish` tool with a short summary of what you changed.

## {title}

{description}"""

PLAN_PROMPT = """You are working in a git repository checked out at the commit just before a change was merged.
Do NOT modify any files. Explore the code, then produce an implementation plan for the change described below:
which files need to change, what changes in each, and any risks or tests to update.
When the plan is ready, call the `finish` tool with the full plan as the summary.

## {title}

{description}"""


def _category(lines_changed: int, files: int, quick_edit_max_lines: int) -> str:
    return "quick_edit" if files == 1 and lines_changed <= quick_edit_max_lines else "feature"


def build_tasks(  # noqa: C901, PLR0912, PLR0913, PLR0915
    repo: str,
    *,
    n_tasks: int = 30,
    branch: str | None = None,
    scan_limit: int = 500,
    min_lines: int = 3,
    max_lines: int = 400,
    max_files: int = 10,
    quick_edit_max_lines: int = 25,
    n_plan_tasks: int = 0,
    require_pr: bool = True,
    skip_docs_only: bool = True,
    excludes: list[str] | None = None,
    fetch_pr_metadata: bool = True,
    seed: int = 0,
    max_reference_chars: int = 60_000,
    cache_dir: Path = DEFAULT_CACHE_DIR,
) -> list[dict[str, Any]]:
    """Build up to ``n_tasks`` edit tasks (plus ``n_plan_tasks`` planning tasks).

    Tasks are drawn from the ``scan_limit`` most recent merged changes on the
    default branch, filtered by size, then sampled so quick edits and
    multi-file features are both represented. Selection is deterministic for a
    given ``seed``.

    Returns a list of JSON-serializable dicts, one per task, suitable for a
    ``weave.Dataset``.
    """
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    repo_dir = prepare_repo(repo, cache_dir)
    branch = branch or default_branch(repo_dir)
    coords = _github_coords(repo) or _github_coords(_git(repo_dir, "config", "--get", "remote.origin.url", check=False))
    token = _github_token() if (coords and fetch_pr_metadata) else None
    repo_name = coords[1] if coords else repo_dir.name.removesuffix(".git")

    eligible: list[dict[str, Any]] = []
    for c in _scan_history(repo_dir, branch, scan_limit):
        if require_pr and c.pr_number is None:
            continue
        if any(bot in c.author.lower() for bot in BOT_AUTHORS) or _CHORE_TITLE.search(c.subject):
            continue
        stats = [s for s in _numstat(repo_dir, c.base_sha, c.sha) if not _is_excluded(s[0], excludes)]
        if not stats or any(a is None for _, a, _ in stats):  # nothing left, or binary files
            continue
        files = [p for p, _, _ in stats]
        if skip_docs_only and all(p.lower().endswith(DOC_SUFFIXES) for p in files):
            continue
        if all(p.startswith(CI_ONLY_PREFIXES) for p in files):
            continue
        added = sum(a for _, a, _ in stats)  # type: ignore[misc]
        removed = sum(r for _, _, r in stats)  # type: ignore[misc]
        if not (min_lines <= added + removed <= max_lines) or len(files) > max_files:
            continue
        eligible.append(
            {
                "candidate": c,
                "files": files,
                "added": added,
                "removed": removed,
                "category": _category(added + removed, len(files), quick_edit_max_lines),
            }
        )

    if not eligible:
        raise TaskBuildError(
            f"no merged changes in the last {scan_limit} commits of {branch} passed the filters; "
            "widen max_lines/max_files, raise scan_limit, or set require_pr=False"
        )

    # Stratified, deterministic sample: aim for roughly one-third quick edits.
    rng = random.Random(seed)
    by_cat: dict[str, list[dict[str, Any]]] = {"quick_edit": [], "feature": []}
    for e in eligible:
        by_cat[e["category"]].append(e)
    for bucket in by_cat.values():
        rng.shuffle(bucket)
    want_quick = min(len(by_cat["quick_edit"]), max(1, n_tasks // 3))
    picked = by_cat["quick_edit"][:want_quick] + by_cat["feature"][: n_tasks - want_quick]
    if len(picked) < n_tasks:  # top up from whichever bucket has spares
        leftovers = by_cat["quick_edit"][want_quick:] + by_cat["feature"][n_tasks - want_quick :]
        picked += leftovers[: n_tasks - len(picked)]
    picked.sort(key=lambda e: e["candidate"].date)

    tasks: list[dict[str, Any]] = []
    for e in picked:
        c: _Candidate = e["candidate"]
        title, description = c.subject, c.body
        if coords and fetch_pr_metadata and c.pr_number is not None:
            pr = _fetch_pr(coords[0], coords[1], c.pr_number, token)
            if pr:
                if pr.get("user", {}).get("type") == "Bot" or _CHORE_TITLE.search(pr.get("title") or ""):
                    continue
                title, description = pr.get("title") or title, pr.get("body") or description
                issues = _linked_issues(coords[0], coords[1], description, token)
                if issues:
                    description = description + "\n\n" + "\n\n".join(issues)
        title = _SQUASH_PR.sub("", _MERGE_PR.sub("", title)).strip() or title
        description = _clean_description(description) or "(no description provided)"
        reference = _git(repo_dir, "diff", "-M", c.base_sha, c.sha, "--", *e["files"])
        tasks.append(
            {
                "task_id": f"{repo_name}#{c.pr_number or c.sha[:10]}",
                "mode": "edit",
                "category": e["category"],
                "repo": repo,
                "base_sha": c.base_sha,
                "merged_sha": c.sha,
                "pr_number": c.pr_number,
                "title": title,
                "prompt": EDIT_PROMPT.format(title=title, description=description),
                "reference_diff": reference[:max_reference_chars],
                "reference_files": e["files"],
                "lines_added": e["added"],
                "lines_removed": e["removed"],
                "merged_at": c.date,
            }
        )

    # Planning tasks reuse the largest feature changes: they need the most design.
    if n_plan_tasks:
        features = sorted(
            (t for t in tasks if t["category"] == "feature"),
            key=lambda t: (len(t["reference_files"]), t["lines_added"] + t["lines_removed"]),
            reverse=True,
        )
        for t in features[:n_plan_tasks]:
            description = t["prompt"].split("\n\n", 2)[-1]
            tasks.append(
                {
                    **t,
                    "task_id": f"{t['task_id']}:plan",
                    "mode": "plan",
                    "category": "planning",
                    "prompt": PLAN_PROMPT.format(title=t["title"], description=description),
                }
            )
    return tasks


def save_tasks(tasks: list[dict[str, Any]], path: str | Path) -> Path:
    """Write tasks to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(tasks, indent=2))
    return path


def load_tasks(path: str | Path) -> list[dict[str, Any]]:
    """Read tasks written by ``save_tasks``."""
    return json.loads(Path(path).read_text())
