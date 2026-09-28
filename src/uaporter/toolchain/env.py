"""Environment helpers for Unity execution across different Linux distributions."""

from __future__ import annotations
from pathlib import Path
import os

TOOLCHAIN_LIB64 = Path(__file__).parent / "lib64"


def get_unity_env() -> dict[str, str]:
    """Return environment variables required to run Unity Editor on modern Linux distros."""
    env = os.environ.copy()
    current_ld = env.get("LD_LIBRARY_PATH", "")
    
    if TOOLCHAIN_LIB64.is_dir():
        lib_str = str(TOOLCHAIN_LIB64.resolve())
        if lib_str not in current_ld:
            env["LD_LIBRARY_PATH"] = f"{lib_str}:{current_ld}" if current_ld else lib_str

    # Enable globalization invariant mode for .NET Core (used by Unity 2021+ Bee build system)
    # to avoid ICU library version mismatch crashes on modern Linux distributions.
    env["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = "1"

    return env
