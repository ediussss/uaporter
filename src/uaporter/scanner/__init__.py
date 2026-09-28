"""Scanner subpackage for inspecting Unity builds."""

from .report import scan_game_directory, print_scan_report
from .version_detector import detect_unity_version
from .backend_detector import detect_backend
from .plugin_inspector import inspect_plugins
from .structure_detector import detect_structure
from .shader_detector import detect_shader_platforms, format_shader_platforms

__all__ = [
    "scan_game_directory",
    "print_scan_report",
    "detect_unity_version",
    "detect_backend",
    "inspect_plugins",
    "detect_structure",
    "detect_shader_platforms",
    "format_shader_platforms",
]
