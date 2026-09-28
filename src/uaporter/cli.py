"""Command-line interface for UAPorter."""

from __future__ import annotations
from pathlib import Path
import click
from rich.console import Console

from . import __version__
from .core.models import ScanReport, TargetPlatform
from .scanner import scan_game_directory, print_scan_report
from .desktop.swapper import swap_to_linux

console = Console()


@click.group(invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show UAPorter version and exit.")
@click.pass_context
def main(ctx: click.Context, version: bool) -> None:
    """UAPorter - Universal Unity Auto-Porter to Android APK & Linux/Steam Deck."""
    if version:
        console.print(f"[bold cyan]UAPorter[/bold cyan] version [green]{__version__}[/green]")
        return
    if ctx.invoked_subcommand is None:
        console.print("[bold cyan]UAPorter[/bold cyan] - Universal Unity Auto-Porter")
        console.print("Run [bold yellow]uaporter --help[/bold yellow] to see available commands.")


@main.command()
@click.argument("game_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
def scan(game_dir: Path) -> None:
    """Inspect and diagnose a Unity game directory."""
    try:
        report = scan_game_directory(game_dir)
        print_scan_report(report, console)
    except Exception as e:
        console.print(f"[bold red]Scan error:[/bold red] {e}")
        raise click.Abort()


def ensure_unity_editor(target_version: UnityVersion, target_desc: str, include_android: bool = False) -> Path:
    """Resolve, install, or switch Unity Editor version with user confirmation."""
    from .toolchain.unity_manager import UnityManager
    from .toolchain.hub_bridge import UnityHubBridge

    exact_editor = UnityHubBridge.find_exact_editor(target_version)
    if exact_editor:
        console.print(f"[bold green]✓ Found matching Unity Editor ({target_version}) at: {exact_editor}[/bold green]")
        return exact_editor

    best_match = UnityHubBridge.find_best_installed_editor(target_version)
    if best_match:
        installed_ver, candidate_path = best_match
        console.print(f"\n[yellow]This port needs Unity [bold]{target_version}[/bold], but you have Unity [bold]{installed_ver}[/bold] installed.[/yellow]")
        console.print(f"[dim]Path: {candidate_path}[/dim]")
        console.print(f"[cyan]For a clean installation and to save disk space, it is recommended to uninstall the previous version ({installed_ver}) first.[/cyan]\n")

        uninstall_old = click.confirm(
            f"Would you like to uninstall the previous version (Unity {installed_ver}) first?",
            default=False,
        )
        if uninstall_old:
            unity_mgr = UnityManager()
            console.print(f"[bold cyan]Uninstalling Unity {installed_ver}...[/bold cyan]")
            unity_mgr.uninstall_editor(installed_ver)
            console.print(f"[bold green]✓ Unity {installed_ver} uninstalled successfully.[/bold green]\n")

        install_new = click.confirm(
            f"Would you like to install the required version (Unity {target_version}) now?",
            default=True,
        )
        if install_new:
            unity_mgr = UnityManager()
            return unity_mgr.install_editor(target_version, include_android=include_android)
        else:
            if uninstall_old:
                console.print(f"[bold red]An installed Unity Editor is required to compile the {target_desc}.[/bold red]")
                raise click.Abort()
            console.print(f"[bold cyan]Proceeding with installed Unity {installed_ver}...[/bold cyan]")
            return candidate_path

    console.print(f"\n[bold yellow]No Unity Editor was detected on your machine.[/bold yellow]")
    install_now = click.confirm(
        f"Would you like UAPorter to automatically download and install Unity {target_version} now?",
        default=True,
    )
    if not install_now:
        console.print(f"[bold red]An installed Unity Editor is required to compile the {target_desc}.[/bold red]")
        raise click.Abort()
    unity_mgr = UnityManager()
    return unity_mgr.install_editor(target_version, include_android=include_android)


@main.command()
@click.argument("game_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--target", "-t", type=click.Choice(["linux", "android"], case_sensitive=False), default="linux", help="Target platform to port to.")
@click.option("--output", "-o", type=click.Path(file_okay=False, path_type=Path), default=None, help="Output destination folder.")
@click.option("--force-decompile", is_flag=True, default=False, help="Force re-decompilation with AssetRipper even if project exists.")
def port(game_dir: Path, target: str, output: Path | None, force_decompile: bool = False) -> None:
    """Port a game to the target platform."""
    report = scan_game_directory(game_dir)
    print_scan_report(report, console)

    if output is None:
        output = game_dir.parent / f"{report.game_name}_{target}"

    if target.lower() == "linux":
        if not report.is_linux_supported:
            console.print("[bold red]Cannot port to Linux due to blocking issues.[/bold red]")
            raise click.Abort()

        from .scanner.shader_detector import LINUX_SUPPORTED_SHADER_PLATFORMS

        # If game has native Linux shaders (OpenGL/Vulkan) or no shader restrictions detected, do quick swap
        has_native_shaders = bool(report.shader_platforms & LINUX_SUPPORTED_SHADER_PLATFORMS)
        is_directx_only = bool(report.shader_platforms and not has_native_shaders)

        if not is_directx_only:
            # Game already has native Linux OpenGL / Vulkan shaders
            console.print(f"[bold green]Starting Desktop Linux swap -> {output}[/bold green]")
            res = swap_to_linux(report, output)
            console.print(f"[bold green]Done! Ported build ready at: {res}[/bold green]")
            return

        # Game only contains DirectX shaders: A full native Linux build via Unity is required
        # to compile all shaders (materials, UI, TextMeshPro, postprocessing) for OpenGL and Vulkan.
        console.print("\n[bold yellow]Notice: Game only contains DirectX shaders.[/bold yellow]")
        console.print("[cyan]To produce working OpenGL and Vulkan graphics on Linux (avoiding missing/pink shaders), UAPorter will decompile and compile a native Linux build using Unity.[/cyan]")

        # Fall through to full Unity rebuild for DirectX-only Linux games
        from .toolchain.license_manager import UnityLicenseManager

        if not report.unity_version:
            console.print("[bold red]Cannot compile native Linux build: Unity engine version is unknown.[/bold red]")
            return

        editor_path = ensure_unity_editor(report.unity_version, "native Linux build", include_android=False)

        if not UnityLicenseManager.ensure_valid_license(editor_path, console):
            console.print("[bold red]Valid Unity license is required to proceed.[/bold red]")
            raise click.Abort()

        console.print(f"[bold cyan]Starting project decompilation & preparation -> {output}[/bold cyan]")
        from .android.decompiler import decompile_game
        project_dir = decompile_game(report, output, is_android=False, force_decompile=force_decompile)
        console.print(f"[bold green]Unity project ready at: {project_dir}[/bold green]")

        from .android.builder import run_headless_linux_build
        from .desktop.steamdeck import generate_gamescope_wrapper, generate_desktop_entry

        bin_dest = output / f"{report.game_name}.x86_64"
        console.print(f"\n[bold cyan]Compiling native Linux Standalone: {bin_dest}...[/bold cyan]")
        run_headless_linux_build(
            unity_editor_path=editor_path,
            project_path=project_dir,
            output_bin_path=bin_dest,
        )

        generate_gamescope_wrapper(output, bin_dest.name)
        generate_desktop_entry(output, report.game_name, bin_dest)
        console.print(f"[bold green]✓ Native Linux build with compiled OpenGL/Vulkan shaders ready at: {output}[/bold green]")

    elif target.lower() == "android":
        if not report.is_android_supported:
            console.print("[bold red]Cannot port to Android: Mono backend is required without blocking issues.[/bold red]")
            raise click.Abort()

        from .toolchain.license_manager import UnityLicenseManager

        if not report.unity_version:
            console.print("[bold red]Cannot compile APK: Unity engine version is unknown.[/bold red]")
            return

        editor_path = ensure_unity_editor(report.unity_version, "Android APK", include_android=True)

        # If running standalone editor without Hub, verify license
        if not UnityLicenseManager.ensure_valid_license(editor_path, console):
            console.print("[bold red]Valid Unity license is required to proceed.[/bold red]")
            raise click.Abort()

        console.print(f"[bold cyan]Starting Android project decompilation & preparation -> {output}[/bold cyan]")
        from .android.decompiler import decompile_game
        project_dir = decompile_game(report, output, is_android=True, force_decompile=force_decompile)
        console.print(f"[bold green]Unity project ready with touch controls at: {project_dir}[/bold green]")

        from .android.builder import run_headless_build
        from .android.signer import ensure_debug_keystore, sign_apk
        from .toolchain.cache import CacheManager

        # Compile APK headlessly
        apk_dest = output / f"{report.game_name}.apk"
        console.print(f"\n[bold cyan]Compiling Android APK: {apk_dest}...[/bold cyan]")
        run_headless_build(
            unity_editor_path=editor_path,
            project_path=project_dir,
            output_apk_path=apk_dest,
        )

        # Sign APK with debug keystore
        cache_mgr = CacheManager()
        keystore_path = cache_mgr.root_dir / "debug.keystore"
        try:
            console.print("[cyan]Signing APK with debug keystore...[/cyan]")
            ensure_debug_keystore(keystore_path)
            sign_apk(apk_dest, keystore_path)
            console.print(f"[bold green]✓ Signed APK ready for sideloading: {apk_dest}[/bold green]")
        except Exception as e:
            console.print(f"[yellow]Note on signing: {e}. Unsigned APK is at {apk_dest}[/yellow]")



@main.command()
@click.option("--username", "-u", prompt="Unity Account Email / Username", help="Unity account email.")
@click.option("--password", "-p", prompt=True, hide_input=True, help="Unity account password.")
@click.option("--serial", "-s", default="", help="Unity Personal or Plus/Pro serial (leave empty for Personal).")
def setup_license(username: str, password: str, serial: str) -> None:
    """Configure your personal Unity license credentials."""
    from .core.config import UserConfig
    from .toolchain.license_manager import UnityLicenseManager
    from .toolchain.unity_manager import UnityManager

    cfg = UserConfig.load()
    cfg.unity_username = username
    cfg.unity_serial = serial
    cfg.save()
    console.print(f"[green]Saved Unity credentials for: {username}[/green]")

    # If any Unity Editor is present locally, attempt immediate activation
    mgr = UnityManager()
    editors = list(mgr.editors_dir.glob("*/Editor/Unity"))
    if editors:
        target_editor = editors[0]
        console.print(f"[cyan]Activating local Unity installation at {target_editor}...[/cyan]")
        success = UnityLicenseManager.activate_with_credentials(target_editor, username, password, serial)
        if success:
            console.print("[bold green]License activated successfully![/bold green]")
        else:
            console.print("[yellow]Activation command completed. Verify with Unity Hub if needed.[/yellow]")
    else:
        console.print("[dim]No local Unity Editor found yet. Credentials will be used when Unity is downloaded during porting.[/dim]")


if __name__ == "__main__":
    main()

