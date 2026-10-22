"""Filesystem lifecycle and hooks management for bare Git repositories (M1-06)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger

logger = get_logger("ubuntubio.git.repo_manager")


class GitRepoManager:
    """Manages creation, deletion, and hooks for bare Git repositories."""

    def __init__(self, git_root: Path | None = None) -> None:
        self._git_root = git_root

    @property
    def git_root(self) -> Path:
        return self._git_root if self._git_root is not None else settings.GIT_ROOT

    def get_repo_path(self, owner: str, name: str) -> Path:
        """Calculate the absolute path to a bare repository."""
        # Sanitize paths to prevent path traversal
        clean_owner = Path(owner).name
        clean_name = Path(name).name
        if not clean_name.endswith(".git"):
            clean_name = f"{clean_name}.git"
        return self.git_root / clean_owner / clean_name

    def init_bare_repo(self, owner: str, name: str) -> Path:
        """Initialize a new bare Git repository on disk."""
        repo_path = self.get_repo_path(owner, name)
        if repo_path.exists():
            return repo_path

        logger.info(
            "Initializing new bare Git repository",
            extra={"repo_owner": owner, "repo_name": name, "repo_path": str(repo_path)},
        )
        repo_path.mkdir(parents=True, exist_ok=True)

        # Run git init --bare with default branch 'main'
        subprocess.run(
            ["git", "init", "--bare", "--initial-branch=main", str(repo_path)],
            check=True,
            capture_output=True,
            text=True,
        )

        # Enable smart HTTP push/pull
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "http.receivepack", "true"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "http.uploadpack", "true"],
            check=True,
        )

        # Install pre-receive hook placeholder
        self.install_hooks(repo_path)
        return repo_path

    def install_hooks(self, repo_path: Path) -> None:
        """Install pre-receive and post-receive hooks."""
        hooks_dir = repo_path / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        pre_receive = hooks_dir / "pre-receive"
        with open(pre_receive, "w", encoding="utf-8") as f:
            f.write(f"#!/bin/sh\nexec {sys.executable} -m ubuntubio.git.validator_hook\n")
        pre_receive.chmod(0o755)

        post_receive = hooks_dir / "post-receive"
        with open(post_receive, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\n# UbuntuBio post-receive indexer hook\nexit 0\n")
        post_receive.chmod(0o755)

    def delete_repo(self, owner: str, name: str) -> bool:
        """Delete bare repository from disk."""
        import shutil

        repo_path = self.get_repo_path(owner, name)
        if repo_path.exists():
            logger.info(
                "Deleting bare Git repository",
                extra={"repo_owner": owner, "repo_name": name, "repo_path": str(repo_path)},
            )
            shutil.rmtree(repo_path)
            return True
        return False
