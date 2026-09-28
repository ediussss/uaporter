"""Detector for Unity scripting backend (Mono vs IL2CPP)."""

from __future__ import annotations
from pathlib import Path
from ..core.models import Backend


def detect_backend(game_dir: Path, data_dir: Path | None = None) -> Backend:
    """Detect whether a game uses Mono or IL2CPP backend.
    
    Detection criteria:
    - IL2CPP: GameAssembly.dll, libGameAssembly.so, or il2cpp_data directory.
    - Mono: MonoBleedingEdge/ or Mono/ directory, or Assembly-CSharp.dll inside Managed/.
    """
    # 1. Check for IL2CPP indicators in game root and data dir
    il2cpp_files = ["GameAssembly.dll", "libGameAssembly.so"]
    for fname in il2cpp_files:
        if (game_dir / fname).exists():
            return Backend.IL2CPP
        if data_dir and (data_dir / fname).exists():
            return Backend.IL2CPP
            
    if (game_dir / "il2cpp_data").is_dir() or (data_dir and (data_dir / "il2cpp_data").is_dir()):
        return Backend.IL2CPP

    # 2. Check for Mono indicators
    mono_dirs = ["MonoBleedingEdge", "Mono"]
    for mdir in mono_dirs:
        if (game_dir / mdir).is_dir():
            return Backend.MONO
        if data_dir and (data_dir / mdir).is_dir():
            return Backend.MONO

    if data_dir:
        managed_dir = data_dir / "Managed"
        if managed_dir.is_dir():
            # If Managed contains Assembly-CSharp.dll, it is definitely Mono
            if (managed_dir / "Assembly-CSharp.dll").is_file():
                return Backend.MONO
            # Even if Assembly-CSharp is missing (e.g. empty game), mscorlib or UnityEngine.dll indicates Mono
            if (managed_dir / "mscorlib.dll").is_file() or (managed_dir / "UnityEngine.dll").is_file():
                return Backend.MONO

    return Backend.UNKNOWN
