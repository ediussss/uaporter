"""Detector for Unity engine version from binary files."""

from __future__ import annotations
from pathlib import Path
import re
from ..core.models import UnityVersion

# Regex pattern for Unity version string, e.g. "2019.3.15f1", "2020.3.30f1"
UNITY_VER_REGEX = re.compile(rb"(\d{4}\.\d+\.\d+[a-zA-Z]\d+)")


def detect_unity_version(game_dir: Path, data_dir: Path | None = None) -> UnityVersion | None:
    """Attempt to detect the Unity version from various files in the game directory.
    
    Order of checks:
    1. globalgamemanagers / data.unity3d in Data directory
    2. level0 / mainData in Data directory
    3. UnityPlayer.dll or .exe strings
    """
    candidates: list[Path] = []
    
    if data_dir and data_dir.exists():
        candidates.extend([
            data_dir / "globalgamemanagers",
            data_dir / "data.unity3d",
            data_dir / "mainData",
            data_dir / "level0",
        ])
    
    # Also search game_dir root for UnityPlayer.dll or executables
    if game_dir.exists():
        unity_player = game_dir / "UnityPlayer.dll"
        if unity_player.exists():
            candidates.append(unity_player)
        for exe in game_dir.glob("*.exe"):
            candidates.append(exe)

    for file_path in candidates:
        if file_path.is_file():
            ver = extract_version_from_file(file_path)
            if ver:
                return ver

    return None


def extract_version_from_file(file_path: Path, max_bytes: int = 1024 * 1024) -> UnityVersion | None:
    """Read binary file up to max_bytes and look for the Unity version string."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(max_bytes)
            
        match = UNITY_VER_REGEX.search(chunk)
        if match:
            ver_str = match.group(1).decode("ascii", errors="ignore")
            return UnityVersion.parse(ver_str)
    except Exception:
        pass
    return None
