"""Core data models for UAPorter."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import re


class Backend(str, Enum):
    MONO = "Mono"
    IL2CPP = "IL2CPP"
    UNKNOWN = "Unknown"


class TargetPlatform(str, Enum):
    LINUX = "Linux / Steam Deck"
    ANDROID = "Android APK"
    WINDOWS = "Windows"


class PluginStatus(str, Enum):
    STUB_SAFE = "STUB_SAFE"
    BLOCKING = "BLOCKING"
    INFO = "INFO"


@dataclass
class PluginInfo:
    name: str
    relative_path: str
    status: PluginStatus
    description: str


@dataclass(frozen=True, order=True)
class UnityVersion:
    major: int
    minor: int
    patch: int
    suffix: str = ""  # e.g. "f1", "b2"

    @classmethod
    def parse(cls, version_str: str) -> UnityVersion | None:
        """Parse standard Unity version string like '2019.3.15f1' or '2021.1.0b5'."""
        match = re.search(r"(\d+)\.(\d+)\.(\d+)([a-zA-Z]\d+)?", version_str)
        if not match:
            return None
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        suffix = match.group(4) or ""
        return cls(major=major, minor=minor, patch=patch, suffix=suffix)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}{self.suffix}"


@dataclass
class ScanReport:
    game_path: Path
    game_name: str
    data_dir: Path | None
    executable_path: Path | None
    unity_version: UnityVersion | None
    backend: Backend
    plugins: list[PluginInfo] = field(default_factory=list)
    shader_platforms: set[int] = field(default_factory=set)
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_android_supported(self) -> bool:
        return self.backend == Backend.MONO and not self.blocking_issues

    @property
    def is_linux_supported(self) -> bool:
        return self.unity_version is not None and not any(
            p.status == PluginStatus.BLOCKING for p in self.plugins
        )
