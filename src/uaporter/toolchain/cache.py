"""Local cache and directory management for UAPorter tools and engines."""

from __future__ import annotations
from pathlib import Path
import shutil


class CacheManager:
    """Manages the ~/.uaporter cache directory."""

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or (Path.home() / ".uaporter")
        self.cache_dir = self.root_dir / "cache"
        self.tools_dir = self.root_dir / "tools"
        self.unity_dir = self.root_dir / "unity"
        self.sdk_dir = self.root_dir / "android-sdk"

        for d in [self.cache_dir, self.tools_dir, self.unity_dir, self.sdk_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def get_assetripper_dir(self) -> Path:
        p = self.tools_dir / "assetripper"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def clean_cache(self) -> None:
        """Clear temporary downloaded archives."""
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
