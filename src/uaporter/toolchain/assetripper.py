"""AssetRipper CLI manager and orchestrator."""

from __future__ import annotations
from pathlib import Path
import os
import stat
import zipfile
import subprocess
import httpx
from rich.console import Console

from .cache import CacheManager

import platform

console = Console()

ASSETRIPPER_BASE_URL = "https://github.com/AssetRipper/AssetRipper/releases/download/0.3.4.0/"


class AssetRipperManager:
    """Manages downloading, caching, and executing AssetRipper CLI across Linux and Windows."""

    def __init__(self, cache_mgr: CacheManager | None = None):
        self.cache_mgr = cache_mgr or CacheManager()
        self.ripper_dir = self.cache_mgr.get_assetripper_dir()
        bin_name = "AssetRipper.exe" if platform.system() == "Windows" else "AssetRipper"
        self.binary_path = self.ripper_dir / bin_name

    def is_installed(self) -> bool:
        if platform.system() == "Windows":
            return self.binary_path.is_file()
        return self.binary_path.is_file() and os.access(self.binary_path, os.X_OK)

    def get_download_url(self) -> tuple[str, str]:
        if platform.system() == "Windows":
            return f"{ASSETRIPPER_BASE_URL}AssetRipper_win_x64.zip", "AssetRipper_win_x64.zip"
        return f"{ASSETRIPPER_BASE_URL}AssetRipper_linux_x64.zip", "AssetRipper_linux_x64.zip"

    def ensure_installed(self) -> Path:
        """Download and extract AssetRipper CLI if not already present."""
        if self.is_installed():
            return self.binary_path

        download_url, zip_filename = self.get_download_url()
        zip_dest = self.cache_mgr.cache_dir / zip_filename
        try:
            with httpx.Client(follow_redirects=True, timeout=120.0) as client:
                with client.stream("GET", download_url) as resp:
                    resp.raise_for_status()
                    with open(zip_dest, "wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
            
            console.print("[cyan]Extracting AssetRipper CLI...[/cyan]")
            with zipfile.ZipFile(zip_dest, "r") as zf:
                zf.extractall(self.ripper_dir)

            # Some versions bundle a nested AssetRipper.zip
            nested_zip = self.ripper_dir / "AssetRipper.zip"
            if nested_zip.is_file():
                with zipfile.ZipFile(nested_zip, "r") as n_zf:
                    n_zf.extractall(self.ripper_dir)
                nested_zip.unlink(missing_ok=True)

            # Mark binary as executable
            if self.binary_path.exists():
                st = os.stat(self.binary_path)
                os.chmod(self.binary_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            return self.binary_path
        finally:
            if zip_dest.exists():
                zip_dest.unlink()


    def decompile(self, game_data_path: Path, output_project_path: Path) -> bool:
        """Run AssetRipper CLI headless to extract a Unity project with live animated progress updates."""
        exe = self.ensure_installed()
        output_project_path.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(exe),
            str(game_data_path),
            "-o", str(output_project_path),
            "-q"  # Quit after completion
        ]

        from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

        current_status = f"Reading {game_data_path.name}..."
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            TextColumn("[yellow]{task.fields[status]}[/yellow]"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task(f"Extracting {game_data_path.name}", status=current_status)

            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    if "Attempting to read files from" in line or "Collecting game files" in line:
                        current_status = "Scanning game files..."
                        progress.update(task_id, status=current_status)
                    elif "Loaded" in line and ("files" in line or "assets" in line):
                        current_status = line.split(" in ")[0].strip()
                        progress.update(task_id, status=current_status)
                    elif "Exporting Project Settings" in line:
                        current_status = "Exporting Project Settings..."
                        progress.update(task_id, status=current_status)
                    elif "Exporting Engine Assets" in line:
                        current_status = "Exporting Engine Assets..."
                        progress.update(task_id, status=current_status)
                    elif "Exporting Assets" in line:
                        current_status = "Extracting textures, meshes & audio..."
                        progress.update(task_id, status=current_status)
                    elif "Exporting Project" in line or "Generating Asset Collections" in line:
                        current_status = "Generating Unity project..."
                        progress.update(task_id, status=current_status)
                    elif "Moving exported files" in line or "Moving files" in line:
                        current_status = "Finalizing project directory..."
                        progress.update(task_id, status=current_status)
                    elif "Game file" in line and "found" in line:
                        fname = line.split("Game file '")[-1].split("'")[0]
                        current_status = f"Reading {fname}..."
                        progress.update(task_id, status=current_status)

            proc.wait()
            return proc.returncode == 0
