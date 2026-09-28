"""Manager for native library stubs (e.g. Steamworks, Discord)."""

from __future__ import annotations
from pathlib import Path
import shutil
from ...core.models import PluginInfo, PluginStatus


class StubManager:
    """Handles replacing Windows native DLLs with Linux stubs or removing unnecessary ones."""

    def __init__(self, target_game_dir: Path):
        self.target_game_dir = target_game_dir

    def apply_stubs(self, plugins: list[PluginInfo]) -> list[str]:
        """Apply stubs or safe removals for known plugins."""
        actions: list[str] = []

        for p in plugins:
            if p.status != PluginStatus.STUB_SAFE:
                continue

            target_file = self.target_game_dir / p.relative_path
            if not target_file.exists():
                continue

            lower_name = p.name.lower()
            if "discord" in lower_name or "galaxy" in lower_name or "xinput" in lower_name:
                # Safe to remove for Linux standalone
                target_file.unlink()
                actions.append(f"Removed non-essential desktop plugin: {p.name}")
            elif "steam_api" in lower_name:
                # Flagged for Linux libsteam_api.so replacement
                actions.append(f"Flagged {p.name} for Linux libsteam_api.so replacement")

        return actions
