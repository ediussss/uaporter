"""Inspector for native and third-party plugins in Unity builds."""

from __future__ import annotations
from pathlib import Path
from ..core.models import PluginInfo, PluginStatus

# Known Windows/Desktop plugins and their compatibility profiles
KNOWN_PLUGINS = {
    # Steam
    "steam_api.dll": (PluginStatus.STUB_SAFE, "Steamworks 32-bit (can be stubbed or replaced with libsteam_api.so)"),
    "steam_api64.dll": (PluginStatus.STUB_SAFE, "Steamworks 64-bit (can be stubbed or replaced with libsteam_api.so)"),
    "CSteamworks.dll": (PluginStatus.STUB_SAFE, "Steamworks.NET wrapper (can be stubbed)"),
    # Discord
    "discord_game_sdk.dll": (PluginStatus.STUB_SAFE, "Discord Game SDK (can be removed/stubbed)"),
    "discord_rpc.dll": (PluginStatus.STUB_SAFE, "Discord RPC (can be removed/stubbed)"),
    # GOG Galaxy
    "Galaxy.dll": (PluginStatus.STUB_SAFE, "GOG Galaxy SDK (can be removed/stubbed)"),
    "Galaxy64.dll": (PluginStatus.STUB_SAFE, "GOG Galaxy 64-bit SDK (can be removed/stubbed)"),
    # Audio / Voice
    "vivoxsdk.dll": (PluginStatus.BLOCKING, "Vivox Voice Chat (requires platform-specific mobile SDK)"),
    "fmod.dll": (PluginStatus.STUB_SAFE, "FMOD Audio Engine (cross-platform, needs platform runtime)"),
    "fmodstudio.dll": (PluginStatus.STUB_SAFE, "FMOD Studio Engine (cross-platform, needs platform runtime)"),
    # Input / Controller
    "xinput1_3.dll": (PluginStatus.STUB_SAFE, "DirectX XInput wrapper (not needed on mobile/linux)"),
    "xinput1_4.dll": (PluginStatus.STUB_SAFE, "DirectX XInput wrapper (not needed on mobile/linux)"),
}


def inspect_plugins(game_dir: Path, data_dir: Path | None = None) -> list[PluginInfo]:
    """Scan game directory and Plugins/ folder for native libraries."""
    plugins: list[PluginInfo] = []
    seen_files: set[str] = set()

    search_dirs: list[Path] = []
    if data_dir and data_dir.exists():
        search_dirs.append(data_dir / "Plugins")
    search_dirs.append(game_dir)

    for s_dir in search_dirs:
        if not s_dir.exists():
            continue
        for ext in ["*.dll", "*.so", "*.dylib"]:
            for path in s_dir.rglob(ext):
                if path.name in seen_files:
                    continue
                seen_files.add(path.name)
                
                # Check if it's a known plugin
                lower_name = path.name.lower()
                matched = False
                for known_name, (status, desc) in KNOWN_PLUGINS.items():
                    if lower_name == known_name.lower():
                        rel_path = str(path.relative_to(game_dir))
                        plugins.append(PluginInfo(
                            name=path.name,
                            relative_path=rel_path,
                            status=status,
                            description=desc
                        ))
                        matched = True
                        break
                
                # If unknown native DLL in Plugins/
                if not matched and "plugins" in str(path).lower():
                    rel_path = str(path.relative_to(game_dir))
                    plugins.append(PluginInfo(
                        name=path.name,
                        relative_path=rel_path,
                        status=PluginStatus.INFO,
                        description="Custom native plugin (may require mobile/Linux replacement)"
                    ))

    return plugins
