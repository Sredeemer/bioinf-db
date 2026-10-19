"""Git Smart-HTTP handler wrapping git http-backend (M1-08)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from fastapi import Request, Response

from ubuntubio.config import settings
from ubuntubio.core.logging import get_logger

logger = get_logger("ubuntubio.git.smart_http")


class GitSmartHttpHandler:
    """Invokes git http-backend with standard CGI environment mapping."""

    def __init__(self, git_root: Path | None = None) -> None:
        self._git_root = git_root

    @property
    def git_root(self) -> Path:
        return self._git_root if self._git_root is not None else settings.GIT_ROOT

    async def handle_request(
        self,
        request: Request,
        repo_subpath: str,
        user_id: str | None = None,
    ) -> Response:
        """Execute git http-backend and stream results back to the client."""
        # Read incoming request body if POST
        body = await request.body() if request.method == "POST" else b""

        env = os.environ.copy()
        env["GIT_PROJECT_ROOT"] = str(self.git_root)
        env["GIT_HTTP_EXPORT_ALL"] = "1"
        env["PATH_INFO"] = f"/{repo_subpath.lstrip('/')}"
        env["REQUEST_METHOD"] = request.method
        env["QUERY_STRING"] = request.url.query
        env["CONTENT_TYPE"] = request.headers.get("content-type", "")
        env["REMOTE_USER"] = user_id or "anonymous"

        logger.debug(
            "Invoking git http-backend",
            extra={"repo_subpath": repo_subpath, "method": request.method, "user_id": user_id},
        )

        proc = subprocess.Popen(
            ["git", "http-backend"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        stdout, stderr = proc.communicate(input=body)
        if proc.returncode != 0:
            logger.error(
                "git http-backend failed",
                extra={
                    "repo_subpath": repo_subpath,
                    "returncode": proc.returncode,
                    "stderr": stderr.decode("latin1", errors="ignore"),
                },
            )
            return Response(
                content=stderr or b"Git backend error",
                status_code=500,
                media_type="text/plain",
            )

        # Parse CGI response headers from stdout (separated from body by \r\n\r\n or \n\n)
        header_end = stdout.find(b"\r\n\r\n")
        delimiter_len = 4
        if header_end == -1:
            header_end = stdout.find(b"\n\n")
            delimiter_len = 2

        if header_end == -1:
            return Response(content=stdout, status_code=200)

        raw_headers = stdout[:header_end].decode("latin1").splitlines()
        response_body = stdout[header_end + delimiter_len :]

        headers_dict: dict[str, str] = {}
        status_code = 200

        import contextlib

        for header_line in raw_headers:
            if ":" in header_line:
                name, val = header_line.split(":", 1)
                clean_name = name.strip()
                clean_val = val.strip()
                if clean_name.lower() == "status":
                    with contextlib.suppress(ValueError, IndexError):
                        status_code = int(clean_val.split()[0])
                else:
                    headers_dict[clean_name] = clean_val

        return Response(
            content=response_body,
            status_code=status_code,
            headers=headers_dict,
        )
