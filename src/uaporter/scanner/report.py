"""Scan report generator and rich terminal visualizer."""

from __future__ import annotations
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..core.models import ScanReport, Backend, PluginStatus
from .structure_detector import detect_structure
from .version_detector import detect_unity_version
from .backend_detector import detect_backend
from .plugin_inspector import inspect_plugins
from .shader_detector import (
    detect_shader_platforms,
    format_shader_platforms,
    LINUX_SUPPORTED_SHADER_PLATFORMS,
)


def scan_game_directory(game_path: Path) -> ScanReport:
    """Run full diagnostic scan on game directory."""
    game_path = game_path.resolve()
    if not game_path.exists():
        raise FileNotFoundError(f"Game directory does not exist: {game_path}")

    game_name, exe_path, data_dir = detect_structure(game_path)
    unity_ver = detect_unity_version(game_path, data_dir)
    backend = detect_backend(game_path, data_dir)
    plugins = inspect_plugins(game_path, data_dir)
    shader_platforms = detect_shader_platforms(data_dir)

    blocking_issues: list[str] = []
    warnings: list[str] = []

    if not data_dir:
        blocking_issues.append("Could not locate Unity '_Data' folder.")
    if not unity_ver:
        warnings.append("Could not extract Unity engine version from binary files.")
    if backend == Backend.UNKNOWN:
        warnings.append("Scripting backend could not be conclusively determined.")
    elif backend == Backend.IL2CPP:
        warnings.append("Game uses IL2CPP backend. Android decompilation is not supported (Desktop only).")

    if shader_platforms and not (shader_platforms & LINUX_SUPPORTED_SHADER_PLATFORMS):
        warnings.append(
            f"Compiled shaders only target ({format_shader_platforms(shader_platforms)}). "
            "Native Linux runtime swap requires OpenGL or Vulkan bytecode. "
            "A full rebuild or decompilation is recommended for graphical rendering on Linux."
        )

    for p in plugins:
        if p.status == PluginStatus.BLOCKING:
            blocking_issues.append(f"Blocking native plugin found: {p.name} ({p.description})")

    return ScanReport(
        game_path=game_path,
        game_name=game_name,
        data_dir=data_dir,
        executable_path=exe_path,
        unity_version=unity_ver,
        backend=backend,
        plugins=plugins,
        shader_platforms=shader_platforms,
        blocking_issues=blocking_issues,
        warnings=warnings,
    )


def print_scan_report(report: ScanReport, console: Console | None = None) -> None:
    """Render rich visual table and summary of the scan report."""
    if console is None:
        console = Console()

    table = Table(title=f"UAPorter Diagnostic Scan: [bold green]{report.game_name}[/bold green]", expand=True)
    table.add_column("Property", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Game Directory", str(report.game_path))
    table.add_row(
        "Executable",
        str(report.executable_path.name) if report.executable_path else "[red]Not found[/red]"
    )
    table.add_row(
        "Data Folder",
        str(report.data_dir.name) if report.data_dir else "[red]Not found[/red]"
    )
    table.add_row(
        "Unity Version",
        f"[bold]{report.unity_version}[/bold]" if report.unity_version else "[yellow]Unknown[/yellow]"
    )

    backend_str = f"[bold green]{report.backend.value}[/bold green]" if report.backend == Backend.MONO else f"[yellow]{report.backend.value}[/yellow]"
    table.add_row("Scripting Backend", backend_str)

    if report.shader_platforms:
        shader_str = format_shader_platforms(report.shader_platforms)
        table.add_row("Shader Platforms", f"[magenta]{shader_str}[/magenta]")

    # Platform feasibility
    linux_status = "[bold green]Supported ✅[/bold green]" if report.is_linux_supported else "[red]Unsupported ❌[/red]"
    android_status = "[bold green]Supported ✅[/bold green]" if report.is_android_supported else "[red]Blocked ❌[/red]"
    table.add_row("Target: Linux / Steam Deck", linux_status)
    table.add_row("Target: Android APK", android_status)

    console.print()
    console.print(table)

    if report.plugins:
        plugin_table = Table(title="Detected Plugins & Libraries", expand=True)
        plugin_table.add_column("Plugin", style="cyan")
        plugin_table.add_column("Relative Path", style="dim")
        plugin_table.add_column("Status")
        plugin_table.add_column("Notes", style="dim")

        for p in report.plugins:
            if p.status == PluginStatus.STUB_SAFE:
                status_str = "[green]STUB_SAFE[/green]"
            elif p.status == PluginStatus.BLOCKING:
                status_str = "[bold red]BLOCKING[/bold red]"
            else:
                status_str = "[blue]INFO[/blue]"
            plugin_table.add_row(p.name, p.relative_path, status_str, p.description)

        console.print()
        console.print(plugin_table)

    if report.blocking_issues:
        console.print()
        console.print(Panel(
            "\n".join(f"[bold red]•[/bold red] {issue}" for issue in report.blocking_issues),
            title="[bold red]Blocking Issues[/bold red]",
            border_style="red"
        ))

    if report.warnings:
        console.print()
        console.print(Panel(
            "\n".join(f"[bold yellow]•[/bold yellow] {warn}" for warn in report.warnings),
            title="[bold yellow]Warnings & Considerations[/bold yellow]",
            border_style="yellow"
        ))
