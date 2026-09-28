"""Automated Unity Editor and Android module downloader and installer."""

from __future__ import annotations
from pathlib import Path
import os
import stat
import shutil
import tarfile
import subprocess
import httpx
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn

from ..core.models import UnityVersion
from .cache import CacheManager
from ..desktop.catalog import UnityPlayerCatalog

console = Console()


class UnityManager:
    """Manages downloading, extracting, and locating Unity Editor versions for Linux."""

    def __init__(self, cache_mgr: CacheManager | None = None):
        self.cache_mgr = cache_mgr or CacheManager()
        self.catalog = UnityPlayerCatalog(self.cache_mgr.cache_dir)
        self.editors_dir = self.cache_mgr.unity_dir

    def get_editor_path(self, version: UnityVersion) -> Path | None:
        """Return the path to the Unity binary if installed locally across Linux or Windows."""
        import platform
        ver_str = str(version)
        bin_name = "Unity.exe" if platform.system() == "Windows" else "Unity"
        
        # 1. Check in ~/.uaporter/unity/<version>/Editor/Unity(.exe)
        candidate = self.editors_dir / ver_str / "Editor" / bin_name
        if candidate.is_file():
            if platform.system() == "Windows" or os.access(candidate, os.X_OK):
                self.patch_bee_backend(candidate)
                return candidate

        # 2. Check standard Unity Hub default path: ~/Unity/Hub/Editor/<version>/Editor/Unity(.exe)
        hub_path = Path.home() / "Unity" / "Hub" / "Editor" / ver_str / "Editor" / bin_name
        if hub_path.is_file():
            if platform.system() == "Windows" or os.access(hub_path, os.X_OK):
                self.patch_bee_backend(hub_path)
                return hub_path

        # 3. Check Windows Program Files default path: C:\Program Files\Unity\Hub\Editor\<version>\Editor\Unity.exe
        if platform.system() == "Windows":
            for base in ["C:\\Program Files", "C:\\Program Files (x86)"]:
                p = Path(base) / "Unity" / "Hub" / "Editor" / ver_str / "Editor" / "Unity.exe"
                if p.is_file():
                    return p

        return None

    @staticmethod
    def patch_bee_backend(editor_path: Path) -> None:
        """Patch Unity's bee_backend on Linux to strip --stdin-canary which causes indefinite hangs."""
        import platform
        if platform.system() != "Linux":
            return

        bee_backend = editor_path.parent / "Data" / "bee_backend"
        bee_real = editor_path.parent / "Data" / "bee_backend_real"

        if bee_backend.is_file() and not bee_real.is_file():
            try:
                with open(bee_backend, "rb") as f:
                    header = f.read(2)
                if header != b"#!":
                    shutil.move(str(bee_backend), str(bee_real))
                    wrapper_content = (
                        "#!/bin/bash\n"
                        "args=()\n"
                        "for arg in \"$@\"; do\n"
                        "    if [ \"$arg\" != \"--stdin-canary\" ]; then\n"
                        "        args+=(\"$arg\")\n"
                        "    fi\n"
                        "done\n"
                        "exec \"${0}_real\" \"${args[@]}\"\n"
                    )
                    bee_backend.write_text(wrapper_content, encoding="utf-8")
                    st = os.stat(bee_backend)
                    os.chmod(bee_backend, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass

    KNOWN_CHANGESETS = {
        "2019.2.6f1": "fe82a0e88406",
        "2019.3.0f6": "27ab2135bccf",
        "2019.3.15f1": "597fa5e3d7ea",
        "2019.4.40f1": "bf95f19e71e6",
        "2020.3.48f1": "1b97110ff716",
        "2021.3.45f1": "65b9319a3b68",
        "2022.3.50f1": "9c1b3f9453fa",
    }

    def find_changeset_online(self, version: str) -> str | None:
        """Query online changesets database if version is missing from KNOWN_CHANGESETS."""
        cache_file = self.cache_mgr.cache_dir / "unity_changesets.tsv"
        if cache_file.is_file():
            try:
                for line in cache_file.read_text(encoding="utf-8").splitlines():
                    parts = line.strip().split("\t")
                    if len(parts) >= 2 and parts[0] == version:
                        self.KNOWN_CHANGESETS[version] = parts[1]
                        return parts[1]
            except Exception:
                pass

        try:
            with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                resp = client.get("https://raw.githubusercontent.com/mob-sakai/unity-changeset/gh_pages/db")
                if resp.status_code == 200:
                    text = resp.text
                    cache_file.write_text(text, encoding="utf-8")
                    for line in text.splitlines():
                        parts = line.strip().split("\t")
                        if len(parts) >= 2 and parts[0] == version:
                            self.KNOWN_CHANGESETS[version] = parts[1]
                            return parts[1]
        except Exception:
            pass

        return None

    def uninstall_editor(self, version: UnityVersion | str) -> bool:
        """Uninstall/delete an existing Unity Editor version from local cache to free disk space."""
        ver_str = str(version)
        target_dir = self.editors_dir / ver_str
        removed = False

        if target_dir.is_dir():
            shutil.rmtree(target_dir, ignore_errors=True)
            removed = True

        # Clean up any leftover cached archive for this version
        for ext in [".tar.xz", ".exe", ".pkg"]:
            archive = self.cache_mgr.cache_dir / f"Unity-{ver_str}{ext}"
            archive.unlink(missing_ok=True)
            android_pkg = self.cache_mgr.cache_dir / f"Unity-Android-{ver_str}{ext}"
            android_pkg.unlink(missing_ok=True)

        return removed

    def resolve_editor_download_url(self, version: UnityVersion) -> tuple[str, str | None] | None:
        """Find the Editor .tar.xz and Android module download URLs from the catalog or known changesets."""
        catalog_data = self.catalog.fetch_catalog()
        ver_str = str(version)

        for release in catalog_data.get("official", []):
            if release.get("version") == ver_str:
                editor_url = release.get("downloadUrl")
                android_url = None
                for mod in release.get("modules", []):
                    if mod.get("id") == "android":
                        android_url = mod.get("downloadUrl")
                return editor_url, android_url

        # Check known changesets fallback or dynamic lookup
        changeset = self.KNOWN_CHANGESETS.get(ver_str)
        if not changeset:
            changeset = self.find_changeset_online(ver_str)

        if changeset:
            import platform
            if platform.system() == "Windows":
                editor_url = f"https://download.unity3d.com/download_unity/{changeset}/Windows64EditorInstaller/UnitySetup64-{ver_str}.exe"
                android_url = f"https://download.unity3d.com/download_unity/{changeset}/TargetSupportInstaller/UnitySetup-Android-Support-for-Editor-{ver_str}.exe"
            else:
                editor_url = f"https://download.unity3d.com/download_unity/{changeset}/LinuxEditorInstaller/Unity.tar.xz"
                android_url = f"https://download.unity3d.com/download_unity/{changeset}/MacEditorTargetInstaller/UnitySetup-Android-Support-for-Editor-{ver_str}.pkg"
            return editor_url, android_url

        return None

    def install_editor(self, version: UnityVersion, include_android: bool = False) -> Path:
        """Download and extract Unity Editor and optionally Android support module automatically."""
        existing = self.get_editor_path(version)
        playback_dir = (self.editors_dir / str(version) / "Editor" / "Data" / "PlaybackEngines" / "AndroidPlayer")
        if existing and (not include_android or playback_dir.is_dir()):
            console.print(f"[green]Using existing Unity Editor {version} at: {existing}[/green]")
            return existing

        urls = self.resolve_editor_download_url(version)
        if not urls or not urls[0]:
            raise RuntimeError(
                f"Could not automatically locate a download URL for Unity {version}. "
                f"Please ensure this version exists in the Unity Linux Hub releases catalog."
            )

        editor_url, android_url = urls
        target_dir = self.editors_dir / str(version)
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Download Editor if missing
        if not (target_dir / "Editor" / "Unity").is_file():
            archive_path = self.cache_mgr.cache_dir / f"Unity-{version}.tar.xz"
            if not archive_path.is_file():
                console.print(f"[bold cyan]Downloading Unity Editor {version} (~1-2 GB)...[/bold cyan]")
                self._download_file(editor_url, archive_path)

            console.print(f"[bold cyan]Extracting Unity Editor to {target_dir}...[/bold cyan]")
            self._extract_tar_xz(archive_path, target_dir)
            archive_path.unlink(missing_ok=True)

        # 2. Download Android Support module if requested and missing
        if include_android and not playback_dir.is_dir() and android_url:
            ext = ".pkg" if android_url.endswith(".pkg") else ".tar.xz"
            android_pkg = self.cache_mgr.cache_dir / f"Unity-Android-{version}{ext}"
            if not android_pkg.is_file():
                console.print(f"[bold cyan]Downloading Android Support Module for Unity {version}...[/bold cyan]")
                self._download_file(android_url, android_pkg)
            console.print(f"[bold cyan]Extracting Android Module...[/bold cyan]")
            self._extract_android_module(android_pkg, playback_dir)
            android_pkg.unlink(missing_ok=True)

        editor_bin = target_dir / "Editor" / "Unity"
        if editor_bin.is_file():
            st = os.stat(editor_bin)
            os.chmod(editor_bin, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            self.patch_bee_backend(editor_bin)
            console.print(f"[bold green]Unity {version} configured successfully![/bold green]")
            return editor_bin

        raise RuntimeError(f"Unity executable not found after extracting {target_dir}")

    def _extract_android_module(self, archive: Path, dest_android_player_dir: Path) -> None:
        """Extract Android playback engine module (supports both .tar.xz and .pkg formats)."""
        dest_android_player_dir.mkdir(parents=True, exist_ok=True)
        if archive.name.endswith(".pkg"):
            # Use 7z to extract Payload, then bsdtar/tar to unpack
            tmp_extract = archive.parent / "pkg_temp"
            tmp_extract.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.run(["7z", "e", str(archive), "TargetSupport.pkg.tmp/Payload", f"-o{tmp_extract}", "-y"], check=True, stdout=subprocess.DEVNULL)
                payload_file = tmp_extract / "Payload"
                if payload_file.is_file():
                    subprocess.run(["bsdtar", "-xf", str(payload_file), "-C", str(dest_android_player_dir)], check=True)
            finally:
                shutil.rmtree(tmp_extract, ignore_errors=True)
        else:
            self._extract_tar_xz(archive, dest_android_player_dir.parent)

    def _download_file(self, url: str, dest: Path) -> None:
        """Stream download file with Rich progress bar."""
        with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))

            with Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
            ) as progress:
                task = progress.add_task(f"Downloading {dest.name}", total=total)
                with open(dest, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=1024 * 64):
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))

    def _extract_tar_xz(self, archive: Path, dest_dir: Path) -> None:
        """Extract tar.xz archive."""
        # Use system tar if available for speed, otherwise tarfile
        if shutil.which("tar"):
            subprocess.run(["tar", "-xf", str(archive), "-C", str(dest_dir)], check=True)
        else:
            with tarfile.open(archive, "r:*") as tar:
                tar.extractall(dest_dir)
