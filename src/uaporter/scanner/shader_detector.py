"""Detector for compiled shader platforms and graphics APIs in Unity assets."""

from __future__ import annotations
from pathlib import Path

# Mapping of Unity ShaderCompilerPlatform enum integers to human-readable names
SHADER_PLATFORM_NAMES: dict[int, str] = {
    0: "OpenGL (Legacy)",
    1: "Direct3D 9",
    2: "Xbox 360",
    3: "PS3",
    4: "Direct3D 11",
    5: "OpenGL ES 2.0",
    8: "Direct3D 11 (9x)",
    9: "OpenGL ES 3.0+",
    10: "PSP2",
    11: "PS4",
    12: "Xbox One",
    14: "Metal",
    15: "OpenGL Core",
    16: "Nintendo 3DS",
    17: "Wii U",
    18: "Vulkan",
    19: "Nintendo Switch",
    20: "Xbox One D3D12",
}

# Platforms supported on Linux Standalone
LINUX_SUPPORTED_SHADER_PLATFORMS = {15, 18, 0}
# Platforms supported on Android
ANDROID_SUPPORTED_SHADER_PLATFORMS = {5, 9, 18}


def detect_shader_platforms(data_dir: Path | None) -> set[int]:
    """Inspect serialized assets in Data directory and detect compiled shader target platforms."""
    if not data_dir or not data_dir.exists():
        return set()

    try:
        import UnityPy
    except ImportError:
        return set()

    platforms: set[int] = set()

    # Prioritize sharedassets0, resources, sharedassets1 where shaders reside
    asset_files = sorted(
        data_dir.glob("*.assets"),
        key=lambda p: (0 if "sharedassets0" in p.name else (1 if "resources" in p.name else 2))
    )

    for asset_file in asset_files[:5]:
        try:
            env = UnityPy.load(str(asset_file))
            for obj in env.objects:
                if obj.type.name in ["Shader", "ComputeShader"]:
                    tree = obj.read_typetree()
                    obj_platforms = tree.get("platforms", [])
                    if isinstance(obj_platforms, list):
                        platforms.update(obj_platforms)
                    if platforms:
                        return platforms
        except Exception:
            continue

    return platforms


def format_shader_platforms(platforms: set[int]) -> str:
    """Format platform IDs into a readable summary string."""
    if not platforms:
        return "Unknown"
    names = [SHADER_PLATFORM_NAMES.get(p, f"Platform {p}") for p in sorted(platforms)]
    return ", ".join(names)
