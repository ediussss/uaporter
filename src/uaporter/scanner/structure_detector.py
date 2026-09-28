"""Detector for Unity directory structure, executable, and data folder."""

from __future__ import annotations
from pathlib import Path


def detect_structure(game_dir: Path) -> tuple[str, Path | None, Path | None]:
    """Inspect game_dir and return (game_name, executable_path, data_dir).
    
    In a standard Unity Windows build:
      <game_dir>/<GameName>.exe
      <game_dir>/<GameName>_Data/
    Or Linux:
      <game_dir>/<GameName>.x86_64
      <game_dir>/<GameName>_Data/
    """
    game_dir = game_dir.resolve()
    
    # Check for *_Data directory first
    data_dirs = [d for d in game_dir.iterdir() if d.is_dir() and d.name.endswith("_Data")]
    
    exe_candidates = list(game_dir.glob("*.exe")) + list(game_dir.glob("*.x86_64"))
    # Exclude installer / uninstaller if possible
    exe_candidates = [e for e in exe_candidates if not any(x in e.name.lower() for x in ["unitycrashhandler", "unins", "setup"])]

    if data_dirs:
        data_dir = data_dirs[0]
        game_name = data_dir.name[:-5]  # strip '_Data'
        
        # Try matching executable
        matching_exe = None
        for ext in [".exe", ".x86_64", ""]:
            candidate = game_dir / f"{game_name}{ext}"
            if candidate.is_file():
                matching_exe = candidate
                break
        if not matching_exe and exe_candidates:
            matching_exe = exe_candidates[0]
            
        return game_name, matching_exe, data_dir

    # If no *_Data, but there's an executable
    if exe_candidates:
        main_exe = exe_candidates[0]
        game_name = main_exe.stem
        # check if matching data dir exists
        candidate_data = game_dir / f"{game_name}_Data"
        data_dir = candidate_data if candidate_data.is_dir() else None
        return game_name, main_exe, data_dir

    return game_dir.name, None, None
