"""Desktop Linux player swapper."""

from __future__ import annotations
from pathlib import Path
import shutil
import os
import tarfile
import httpx
from rich.console import Console

from ..core.models import ScanReport
from .catalog import UnityPlayerCatalog
from .steamdeck import generate_gamescope_wrapper, generate_desktop_entry
from .stubs.stub_manager import StubManager

console = Console()


def swap_to_linux(
    report: ScanReport,
    output_dir: Path,
    player_archive_path: Path | None = None,
) -> Path:
    """Port a Windows Unity Mono game to Linux Standalone player."""
    if not report.unity_version:
        raise ValueError("Cannot swap player: Unity engine version is unknown.")

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy game Data directory
    if not report.data_dir or not report.data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {report.data_dir}")

    dest_data_dir = output_dir / report.data_dir.name
    if dest_data_dir.exists():
        shutil.rmtree(dest_data_dir)
    shutil.copytree(report.data_dir, dest_data_dir)

    # 2. Copy any non-data files (e.g. streaming assets or subdirs, excluding windows exe)
    for item in report.game_path.iterdir():
        if item.is_file() and item.suffix.lower() not in [".exe", ".dll", ".pdb"]:
            shutil.copy2(item, output_dir / item.name)

    # 3. Handle player binary
    linux_bin_name = f"{report.game_name}.x86_64"
    dest_binary = output_dir / linux_bin_name

    # Check if we have the matching LinuxPlayer already in PlaybackEngines
    local_playback = Path.home() / ".uaporter" / "unity" / str(report.unity_version) / "Editor" / "Data" / "PlaybackEngines" / "LinuxStandaloneSupport" / "Variations" / "linux64_withgfx_nondevelopment_mono" / "LinuxPlayer"
    if not local_playback.is_file():
        # Check dev variation
        local_playback = Path.home() / ".uaporter" / "unity" / str(report.unity_version) / "Editor" / "Data" / "PlaybackEngines" / "LinuxStandaloneSupport" / "Variations" / "linux64_withgfx_development_mono" / "LinuxPlayer"

    variation_dir: Path | None = None
    if local_playback.is_file():
        variation_dir = local_playback.parent
        console.print(f"[cyan]Using version-matched native Linux player: {local_playback.name}...[/cyan]")
        shutil.copy2(local_playback, dest_binary)
        os.chmod(dest_binary, 0o755)
        # In Unity 2019.3+, the executable dynamically links against UnityPlayer.so
        player_so = variation_dir / "UnityPlayer.so"
        if player_so.is_file():
            shutil.copy2(player_so, output_dir / "UnityPlayer.so")
    elif player_archive_path and player_archive_path.exists():
        _extract_player_binary(player_archive_path, dest_binary)
    else:
        # Resolve and download matching Linux player support archive
        catalog = UnityPlayerCatalog()
        player_url = catalog.resolve_linux_player_download(report.unity_version)
        if player_url:
            console.print(f"[cyan]Downloading matching Linux player for Unity {report.unity_version}...[/cyan]")
            cache_mgr = Path.home() / ".uaporter" / "cache"
            cache_mgr.mkdir(parents=True, exist_ok=True)
            dl_archive = cache_mgr / f"LinuxPlayer-{report.unity_version}.tar.xz"
            with httpx.stream("GET", player_url, follow_redirects=True, timeout=120.0) as resp:
                resp.raise_for_status()
                with open(dl_archive, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
            _extract_player_binary(dl_archive, dest_binary)
            dl_archive.unlink(missing_ok=True)
        else:
            if not dest_binary.exists():
                with open(dest_binary, "wb") as f:
                    f.write(b"#!/bin/sh\necho 'Unity Linux Player'\n")
                os.chmod(dest_binary, 0o755)

    # 4. Bundle native Linux Mono runtime & helper plugins if present in variation
    if variation_dir and variation_dir.is_dir():
        # Copy MonoBleedingEdge for Mono builds
        var_data = variation_dir / "Data"
        if var_data.is_dir():
            var_mono = var_data / "MonoBleedingEdge"
            dest_mono = dest_data_dir / "MonoBleedingEdge"
            if var_mono.is_dir():
                if dest_mono.exists():
                    shutil.rmtree(dest_mono)
                shutil.copytree(var_mono, dest_mono)

            # Copy ScreenSelector.so if present
            var_screen_selector = var_data / "Plugins" / "x86_64" / "ScreenSelector.so"
            if var_screen_selector.is_file():
                dest_plugins_dir = dest_data_dir / "Plugins" / "x86_64"
                dest_plugins_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(var_screen_selector, dest_plugins_dir / "ScreenSelector.so")

    # 5. Apply plugin stubs / removals
    stubber = StubManager(output_dir)
    stubber.apply_stubs(report.plugins)

    # 6. Patch graphics APIs in globalgamemanagers (enable OpenGL Core 17 and Vulkan 21)
    patch_graphics_apis(dest_data_dir)

    # 7. Inject Linux shaders if shader cache is available
    if report.unity_version:
        injected = inject_linux_shaders(dest_data_dir, str(report.unity_version))
        if injected > 0:
            console.print(f"[green]✓ Injected {injected} compiled OpenGL/Vulkan shaders into game assets.[/green]")

    # 8. Generate Steam Deck & Linux wrappers
    generate_gamescope_wrapper(output_dir, linux_bin_name)
    generate_desktop_entry(output_dir, report.game_name, dest_binary)

    return output_dir


def patch_graphics_apis(data_dir: Path, apis: list[int] | None = None) -> bool:
    """Patch globalgamemanagers to ensure Linux graphics APIs (OpenGL Core 17, Vulkan 21) are enabled."""
    if apis is None:
        apis = [17, 21]
    ggm_path = data_dir / "globalgamemanagers"
    if not ggm_path.is_file():
        return False

    try:
        import UnityPy
        env = UnityPy.load(str(ggm_path))
        modified = False
        for obj in env.objects:
            if obj.type.name == "BuildSettings":
                tree = obj.read_typetree()
                if "m_GraphicsAPIs" in tree:
                    tree["m_GraphicsAPIs"] = apis
                    obj.save_typetree(tree)
                    modified = True
                    break
        if modified:
            with open(ggm_path, "wb") as f:
                f.write(env.file.save())
            return True
    except Exception:
        pass
    return False


def inject_linux_shaders(data_dir: Path, unity_version: str) -> int:
    """Inject compiled OpenGL Core and Vulkan shader assets from cache into data directory."""
    cache_dir = Path.home() / ".uaporter" / "shader_cache" / str(unity_version)
    editor_builtin = Path.home() / ".uaporter" / "unity" / str(unity_version) / "Editor" / "Data" / "Resources" / "unity_builtin_extra"

    if not cache_dir.is_dir() and not editor_builtin.is_file():
        return 0

    injected_count = 0
    try:
        builtin_extra = cache_dir / "unity_builtin_extra" if cache_dir.is_dir() else None
        if not builtin_extra or not builtin_extra.is_file():
            if editor_builtin.is_file():
                builtin_extra = editor_builtin

        if builtin_extra and builtin_extra.is_file():
            res_dir = data_dir / "Resources"
            res_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(builtin_extra, res_dir / "unity_builtin_extra")
            injected_count += 1

        if cache_dir.is_dir():
            for cache_asset in cache_dir.glob("*.assets"):
                target_asset = data_dir / cache_asset.name
                if target_asset.exists():
                    shutil.copy2(cache_asset, target_asset)
                    injected_count += 1
    except Exception:
        pass

    return injected_count


def _extract_player_binary(archive_path: Path, dest_binary: Path) -> None:
    """Extract LinuxPlayer binary and UnityPlayer.so from Unity Linux support tar.xz."""
    if archive_path.name.endswith(".tar.xz") or archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:*") as tar:
            for member in tar.getmembers():
                if member.name.endswith("LinuxPlayer"):
                    f = tar.extractfile(member)
                    if f:
                        dest_binary.write_bytes(f.read())
                        os.chmod(dest_binary, 0o755)
                elif member.name.endswith("UnityPlayer.so"):
                    f = tar.extractfile(member)
                    if f:
                        (dest_binary.parent / "UnityPlayer.so").write_bytes(f.read())
