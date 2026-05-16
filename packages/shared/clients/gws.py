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
WIKI_FOLDER_ID = "1ea64rDgJZClTOv4E_0NGAdF8a1CVH_34"  # BenjaminOS/6-Wiki



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
        self.scopes = scopes or [SCOPE_DRIVE_READONLY, SCOPE_DOCS_READONLY, SCOPE_DRIVE_FILE]
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


    def find_in_folder(self, parent_id: str, name: str,
                       mime_type: str | None = None) -> dict | None:
        """Return the first file/folder with `name` inside `parent_id`, or None."""
        safe_name = name.replace("'", "\\'")
        q = [f"'{parent_id}' in parents", f"name = '{safe_name}'",
             "trashed = false"]
        if mime_type:
            q.append(f"mimeType = '{mime_type}'")
        resp = self._drive_service().files().list(
            q=" and ".join(q), fields="files(id,name,mimeType)",
            pageSize=1, supportsAllDrives=True, includeItemsFromAllDrives=True,
        ).execute()
        files = resp.get("files", [])
        return files[0] if files else None


    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        """Return folder ID for `name` inside `parent_id`; create if missing."""
        existing = self.find_in_folder(parent_id, name,
            mime_type="application/vnd.google-apps.folder")
        if existing:
            return existing["id"]
        body = {"name": name, "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id]}
        new = self._drive_service().files().create(
            body=body, fields="id,name", supportsAllDrives=True,
        ).execute()
        return new["id"]


    def resolve_folder_path(self, start_folder_id: str, *path_parts: str) -> str:
        """Walk path components from start_folder_id, creating folders as needed.

        Example: resolve_folder_path(WIKI_ID, 'personal', 'journal') ->
        creates personal/ and journal/ if they don't exist, returns journal id.
        """
        current = start_folder_id
        for part in path_parts:
            if not part:
                continue
            current = self.find_or_create_folder(current, part)
        return current


    def create_text_file(self, folder_id: str, name: str, content: str,
                         mime_type: str = "text/markdown") -> dict:
        """Create a text file in folder. Returns {id, name, webViewLink}."""
        from googleapiclient.http import MediaIoBaseUpload
        body = {"name": name, "parents": [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype=mime_type, resumable=False,
        )
        return self._drive_service().files().create(
            body=body, media_body=media,
            fields="id,name,webViewLink",
            supportsAllDrives=True,
        ).execute()
