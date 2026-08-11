# tests/test_forge_update_check.py — regression test for the Forge Neo
# "Check for Updates" false-negative bug.
#
# Real-world bug: _ForgeUpdateWorker decided whether an update was available
# by comparing the *text* of modules_forge/forge_version.py between the
# local checkout and the upstream ref. Forge Neo (Haoming02/sd-webui-forge-
# classic) doesn't reliably bump that file on every release -- e.g. the
# upstream "2.28.1" tag only touched README.md, leaving forge_version.py's
# `release = "2.28"` untouched. A checkout sitting at the prior commit had
# identical version-file text to the new upstream tip, so the string
# compare reported "Up to date" while real commits (including backend
# fixes) sat unpulled. Confirmed against the actual upstream repo history
# before fixing. The fix compares commit SHAs (local HEAD vs `@{u}`)
# instead, using the version file only for the human-readable message.

import os
import subprocess

import pytest

import settings_dialog as sd


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True, text=True, timeout=30,
    )


def _write_version_file(repo_dir, release="2.28"):
    d = os.path.join(repo_dir, "modules_forge")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "forge_version.py"), "w", encoding="utf-8") as f:
        f.write(f'version = "neo"\nrelease = "{release}"\n')


@pytest.fixture
def stale_checkout(tmp_path):
    """A local clone deliberately one commit behind its remote, where the
    upstream commit that moved the remote forward did NOT touch
    forge_version.py -- exactly the real-world "2.28.1" tag scenario."""
    remote = tmp_path / "remote"
    remote.mkdir()
    _git(remote, "init", "-q")
    _write_version_file(str(remote))
    (remote / "README.md").write_text("hello\n", encoding="utf-8")
    _git(remote, "add", "-A")
    _git(remote, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-qm", "initial 2.28")

    (remote / "README.md").write_text("hello world\n", encoding="utf-8")
    _git(remote, "-c", "user.email=t@t.com", "-c", "user.name=t", "commit", "-aqm", "update README (no version bump)")

    local = tmp_path / "local"
    _git(tmp_path, "clone", "-q", str(remote), str(local))
    _git(local, "reset", "-q", "--hard", "HEAD~1")
    _git(local, "branch", "-u", "origin/master")

    return str(local)


def test_detects_update_when_version_file_text_is_unchanged(qapp, stale_checkout):
    """The core regression: local is genuinely behind, but its
    forge_version.py text matches the remote tip's exactly. Must not report
    "Up to date"."""
    worker = sd._ForgeUpdateWorker(stale_checkout)
    results = []
    worker.result.connect(lambda ok, msg: results.append((ok, msg)))
    worker.run()

    assert len(results) == 1
    ok, msg = results[0]
    assert ok is True
    assert "Up to date" not in msg
    assert msg.startswith("Updated")

    # And it actually pulled -- local HEAD now matches remote tip.
    local_sha = _git(stale_checkout, "rev-parse", "HEAD").stdout.strip()
    remote_sha = _git(stale_checkout, "rev-parse", "origin/master").stdout.strip()
    assert local_sha == remote_sha


def test_reports_up_to_date_when_shas_match(qapp, stale_checkout):
    """Once genuinely current, a second check must say so."""
    first = sd._ForgeUpdateWorker(stale_checkout)
    first.run()  # brings it up to date

    worker = sd._ForgeUpdateWorker(stale_checkout)
    results = []
    worker.result.connect(lambda ok, msg: results.append((ok, msg)))
    worker.run()

    assert results == [(True, "Up to date — neo 2.28")]


def test_missing_dir_reports_error(qapp, tmp_path):
    worker = sd._ForgeUpdateWorker(str(tmp_path / "does_not_exist"))
    results = []
    worker.result.connect(lambda ok, msg: results.append((ok, msg)))
    worker.run()
    assert results == [(False, "Forge Neo directory not set — save it first.")]


def test_non_git_dir_reports_error(qapp, tmp_path):
    d = tmp_path / "not_a_repo"
    d.mkdir()
    worker = sd._ForgeUpdateWorker(str(d))
    results = []
    worker.result.connect(lambda ok, msg: results.append((ok, msg)))
    worker.run()
    assert results == [(False, "Not a git checkout — can't check for updates here.")]
