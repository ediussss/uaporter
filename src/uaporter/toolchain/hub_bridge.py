"""Bridge to Unity Hub CLI and installations."""

from __future__ import annotations
from pathlib import Path
import os
import platform
import shutil
import subprocess
from ..core.models import UnityVersion


class UnityHubBridge:
    """Discovers Unity Hub, lists installed editors, and launches builds with user's active Hub session."""

    @staticmethod
    def find_hub_binary() -> Path | None:
        """Locate unityhub / Unity Hub executable on Linux, Windows, or Mac."""
        system = platform.system()

        # 1. PATH search
        for name in ["unityhub", "unity-hub", "UnityHub.exe"]:
            p = shutil.which(name)
            if p:
                return Path(p)

        # 2. Standard Linux paths
        if system == "Linux":
            candidates = [
                Path.home() / "Applications" / "UnityHub.AppImage",
                Path.home() / ".local" / "bin" / "unityhub",
                Path("/usr/bin/unityhub"),
                Path("/opt/unityhub/unityhub"),
                Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin" / "com.unity.UnityHub",
                Path("/var/lib/flatpak/exports/bin/com.unity.UnityHub"),
            ]
            for c in candidates:
                if c.is_file() and os.access(c, os.X_OK):
                    return c

        # 3. Standard Windows paths
        elif system == "Windows":
            candidates = [
                Path("C:\\Program Files\\Unity Hub\\Unity Hub.exe"),
                Path("C:\\Program Files (x86)\\Unity Hub\\Unity Hub.exe"),
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Unity Hub" / "Unity Hub.exe",
            ]
            for c in candidates:
                if c.is_file():
                    return c

        # 4. Standard macOS paths
        elif system == "Darwin":
            mac_p = Path("/Applications/Unity Hub.app/Contents/MacOS/Unity Hub")
            if mac_p.is_file():
                return mac_p

        return None

    @staticmethod
    def get_installed_editors() -> list[tuple[str, Path]]:
        """List editors registered with Unity Hub or found in Hub directories."""
        editors = []
        system = platform.system()
        bin_name = "Unity.exe" if system == "Windows" else "Unity"

        search_dirs = [
            Path.home() / "Unity" / "Hub" / "Editor",
            Path.home() / ".uaporter" / "unity",
        ]
        if system == "Windows":
            search_dirs.extend([
                Path("C:\\Program Files\\Unity\\Hub\\Editor"),
                Path("C:\\Program Files (x86)\\Unity\\Hub\\Editor"),
            ])
        elif system == "Darwin":
            search_dirs.append(Path("/Applications/Unity/Hub/Editor"))

        for s_dir in search_dirs:
            if not s_dir.is_dir():
                continue
            for ver_dir in s_dir.iterdir():
                if not ver_dir.is_dir():
                    continue
                editor_bin = ver_dir / "Editor" / bin_name
                if editor_bin.is_file():
                    editors.append((ver_dir.name, editor_bin))

        return editors

    @staticmethod
    def find_exact_editor(target_version: UnityVersion) -> Path | None:
        """Find an exact version match among installed editors."""
        editors = UnityHubBridge.get_installed_editors()
        target_str = str(target_version)
        for ver_str, path in editors:
            if ver_str == target_str:
                return path
        return None

    @staticmethod
    def find_best_installed_editor(target_version: UnityVersion) -> tuple[str, Path] | None:
        """Find the best installed Editor returning (version_string, path)."""
        editors = UnityHubBridge.get_installed_editors()
        if not editors:
            return None

        target_str = str(target_version)
        major_minor = f"{target_version.major}.{target_version.minor}"

        # 1. Exact match (e.g. 2019.2.6f1)
        for ver_str, path in editors:
            if ver_str == target_str:
                return ver_str, path

        # 2. Same major.minor (e.g. 2019.2.x)
        for ver_str, path in editors:
            if ver_str.startswith(major_minor):
                return ver_str, path

        # 3. Same major (e.g. 2019.x)
        for ver_str, path in editors:
            if ver_str.startswith(str(target_version.major)):
                return ver_str, path

        # 4. Fallback to any installed editor
        return editors[0][0], editors[0][1]
