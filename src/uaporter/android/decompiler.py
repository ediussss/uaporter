"""Android decompilation and project preparation workflow."""

from __future__ import annotations
from pathlib import Path
from rich.console import Console

from ..core.models import ScanReport
from ..toolchain.assetripper import AssetRipperManager
from .injector import inject_android_assets

console = Console()


class DecompilationError(Exception):
    pass


def decompile_game(
    report: ScanReport,
    output_project_path: Path,
    ripper_mgr: AssetRipperManager | None = None,
    is_android: bool = False,
    force_decompile: bool = False,
) -> Path:
    """Decompile a Mono Unity game into a full Unity Editor project directory."""
    if not report.data_dir or not report.data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {report.data_dir}")

    ripper = ripper_mgr or AssetRipperManager()
    output_project_path = output_project_path.resolve()
    output_project_path.mkdir(parents=True, exist_ok=True)

    existing_project = None
    if not force_decompile:
        # Check if an already decompiled project exists in output_project_path or nested ExportedProject
        candidates = [output_project_path, output_project_path / "ExportedProject"]
        for cand in candidates:
            if (cand / "ProjectSettings" / "ProjectVersion.txt").is_file() and (cand / "Assets").is_dir():
                existing_project = cand
                break

    if existing_project:
        console.print(f"[bold green]Reusing existing decompiled Unity project at: {existing_project}[/bold green]")
        console.print("[dim]Skipping AssetRipper extraction (pass --force-decompile to re-extract from scratch).[/dim]")
        output_project_path = existing_project
    else:
        console.print(f"[bold cyan]Decompiling game assets from {report.data_dir.name}...[/bold cyan]")
        success = ripper.decompile(report.data_dir, output_project_path)

        # In synthetic test environments or when AssetRipper output nests files:
        # Check if Assets/ folder exists
        assets_dir = output_project_path / "Assets"
        if not assets_dir.is_dir():
            # Check if AssetRipper created a nested subfolder (e.g. ExportedProject/Assets)
            for nested in output_project_path.rglob("Assets"):
                if nested.is_dir():
                    assets_dir = nested
                    output_project_path = nested.parent
                    break

        if not assets_dir.is_dir():
            if not success:
                raise DecompilationError("AssetRipper failed to extract Unity project.")
            # Create Assets directory if empty extraction
            assets_dir.mkdir(parents=True, exist_ok=True)

        console.print("[green]Assets decompiled successfully.[/green]")

    # Patch missing assemblies and dependencies
    from .project_patcher import patch_decompiled_project
    patches = patch_decompiled_project(output_project_path, report.data_dir)
    for p in patches:
        console.print(f"  [dim]• {p}[/dim]")

    # Inject runtime and build scripts
    if is_android:
        console.print("[cyan]Injecting mobile touch overlay and build scripts...[/cyan]")
    else:
        console.print("[cyan]Injecting native build scripts...[/cyan]")
    injected = inject_android_assets(output_project_path, is_android=is_android)
    for item in injected:
        console.print(f"  [dim]+ Injected {item}[/dim]")

    return output_project_path
