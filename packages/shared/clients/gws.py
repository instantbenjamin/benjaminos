"""Google Workspace client — Drive + Docs reads (and eventually writes).

Uses the eir-agents service account with domain-wide delegation to
impersonate b@white.ai. Credential file at ~/.config/gws/eir-agents-sa.json.

Scopes loaded lazily based on the operation requested.
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_SA_PATH = Path("~/.config/gws/benjaminos-sa.json").expanduser()
DEFAULT_IMPERSONATE = "b@white.ai"

SCOPE_DRIVE_READONLY = "https://www.googleapis.com/auth/drive.readonly"
SCOPE_DRIVE_FILE     = "https://www.googleapis.com/auth/drive.file"
SCOPE_DOCS_READONLY  = "https://www.googleapis.com/auth/documents.readonly"


class GWSClient:
    """Domain-wide-delegated Google Workspace client for b@white.ai."""

    def __init__(
        self,
        sa_path: str | Path | None = None,
        impersonate: str | None = None,
        scopes: list[str] | None = None,
    ):
        self.sa_path = Path(sa_path or os.environ.get("GWS_SA_PATH", DEFAULT_SA_PATH))
        self.impersonate = impersonate or os.environ.get("GWS_IMPERSONATE", DEFAULT_IMPERSONATE)
        self.scopes = scopes or [SCOPE_DRIVE_READONLY, SCOPE_DOCS_READONLY]
        if not self.sa_path.exists():
            raise RuntimeError(f"SA credentials not found at {self.sa_path}")
        self._drive = None
        self._creds = None

    def _build_creds(self):
        from google.oauth2 import service_account
        sa_creds = service_account.Credentials.from_service_account_file(
            str(self.sa_path), scopes=self.scopes,
        )
        return sa_creds.with_subject(self.impersonate)

    def _drive_service(self):
        if self._drive is None:
            from googleapiclient.discovery import build
            self._drive = build("drive", "v3", credentials=self._build_creds(),
                                cache_discovery=False)
        return self._drive

    def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Return Drive metadata for a file (name, mimeType, parents, mtime, etc.)."""
        return self._drive_service().files().get(
            fileId=file_id,
            fields="id,name,mimeType,parents,modifiedTime,createdTime,owners",
            supportsAllDrives=True,
        ).execute()

    def read_doc_as_text(self, file_id: str) -> str:
        """Export a Google Doc as plain text. Returns the body content as a string."""
        return self._export(file_id, "text/plain")

    def read_doc_as_markdown(self, file_id: str) -> str:
        """Export a Google Doc as markdown."""
        return self._export(file_id, "text/markdown")

    def _export(self, file_id: str, mime_type: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload
        request = self._drive_service().files().export_media(
            fileId=file_id, mimeType=mime_type,
        )
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue().decode("utf-8", errors="replace")

    def list_files_in_folder(
        self, folder_id: str, mime_type: str | None = None,
        modified_after: str | None = None, page_size: int = 200,
    ) -> list[dict[str, Any]]:
        """List files inside a folder. Optionally filter by mime_type and mtime."""
        q = [f"'{folder_id}' in parents", "trashed = false"]
        if mime_type:
            q.append(f"mimeType = '{mime_type}'")
        if modified_after:
            q.append(f"modifiedTime > '{modified_after}'")
        resp = self._drive_service().files().list(
            q=" and ".join(q),
            fields="files(id,name,mimeType,modifiedTime,parents)",
            pageSize=page_size,
            supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        return resp.get("files", [])
