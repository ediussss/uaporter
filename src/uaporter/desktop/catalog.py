"""Unity Player release catalog resolver."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import httpx
from ..core.models import UnityVersion

UNITY_RELEASES_URL = "https://public-cdn.cloud.unity3d.com/hub/prod/releases-linux.json"
OFFICIAL_ARCHIVE_URL = "https://unity.com/releases/editor/archive"


@dataclass
class UnityReleaseInfo:
    version: UnityVersion
    version_string: str
    download_url: str
    linux_player_url: str | None = None
    changeset: str | None = None


class UnityPlayerCatalog:
    """Manages discovery and resolution of Unity Linux Standalone player binaries."""

    def __init__(self, cache_dir: Path | None = None):
        self.cache_dir = cache_dir or (Path.home() / ".uaporter" / "cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.catalog_cache_file = self.cache_dir / "unity_releases_linux.json"

    def fetch_catalog(self, force_refresh: bool = False) -> dict:
        """Fetch the Unity Linux release JSON from Unity CDN or cache."""
        if not force_refresh and self.catalog_cache_file.is_file():
            try:
                with open(self.catalog_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # 1. Try official releases API
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(UNITY_RELEASES_URL)
                if resp.status_code == 200:
                    data = resp.json()
                    with open(self.catalog_cache_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    return data
        except Exception:
            pass

        # 2. Scrape official Unity download archive as dynamic fallback
        try:
            import re
            headers = {"User-Agent": "Mozilla/5.0"}
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(OFFICIAL_ARCHIVE_URL, headers=headers)
                if resp.status_code == 200:
                    matches = re.findall(r"unityhub://([0-9a-zA-Z._-]+)/([0-9a-f]{12})", resp.text)
                    releases = []
                    for v_str, h_str in matches:
                        releases.append({
                            "version": v_str,
                            "downloadUrl": f"https://download.unity3d.com/download_unity/{h_str}/LinuxEditorInstaller/Unity.tar.xz",
                            "changeset": h_str
                        })
                    data = {"official": releases}
                    with open(self.catalog_cache_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    return data
        except Exception:
            pass

        # Fallback to empty if offline and not cached
        return {"official": []}

    def resolve_linux_player_download(self, version: UnityVersion) -> str | None:
        """Find the download URL for Linux Standalone Support / player archive.
        
        Unity standard component URL pattern:
          https://download.unity3d.com/download_unity/{changeset}/TargetSupportInstaller/UnitySetup-Linux-Support-for-Editor-{version}.tar.xz
          or
          https://download.unity3d.com/download_unity/{changeset}/LinuxEditorTargetInstaller/UnitySetup-Linux-Support-for-Editor-{version}.tar.xz
        """
        catalog = self.fetch_catalog()
        ver_str = str(version)

        # Search in catalog entries
        for release in catalog.get("official", []):
            if release.get("version") == ver_str:
                # Find Linux Support module in modules list
                modules = release.get("modules", [])
                for mod in modules:
                    if mod.get("id") in ["linux", "linux-mono", "linux-il2cpp"]:
                        return mod.get("downloadUrl")
                # Alternatively, check downloadUrl root
                changeset = release.get("downloadUrl", "").split("/download_unity/")[-1].split("/")[0]
                if changeset:
                    return f"https://download.unity3d.com/download_unity/{changeset}/TargetSupportInstaller/UnitySetup-Linux-Support-for-Editor-{ver_str}.tar.xz"

        return None
