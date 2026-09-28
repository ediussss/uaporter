"""User configuration and credential management (~/.uaporter/config.yaml)."""

from __future__ import annotations
from pathlib import Path
from dataclasses import dataclass, asdict
import yaml


@dataclass
class UserConfig:
    unity_username: str = ""
    unity_serial: str = ""
    custom_unity_path: str = ""
    auto_download_tools: bool = True

    @classmethod
    def load(cls, config_path: Path | None = None) -> UserConfig:
        config_file = config_path or (Path.home() / ".uaporter" / "config.yaml")
        if not config_file.is_file():
            return cls()

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
                return cls(
                    unity_username=data.get("unity_username", ""),
                    unity_serial=data.get("unity_serial", ""),
                    custom_unity_path=data.get("custom_unity_path", ""),
                    auto_download_tools=data.get("auto_download_tools", True),
                )
        except Exception:
            return cls()

    @property
    def is_configured(self) -> bool:
        return bool(self.unity_username.strip())

    def prompt_credentials_if_needed(self, console=None) -> None:
        """If credentials are not yet configured, prompt the user right in the CLI."""
        if self.is_configured:
            return

        from rich.console import Console
        import click

        c = console or Console()
        c.print()
        c.print("[bold yellow]════════════════════ Unity Account Setup Required ════════════════════[/bold yellow]")
        c.print("To automatically build Android APKs, a free Unity Personal license is needed.")
        c.print("Please enter your Unity account credentials (saved locally to [dim]~/.uaporter/config.yaml[/dim]):")
        c.print()

        username = click.prompt("Unity Email / Username", type=str)
        serial = click.prompt("Unity Serial Key (Press Enter to skip if using Personal)", default="", show_default=False)

        self.unity_username = username
        self.unity_serial = serial
        self.save()
        c.print("[bold green]✓ Credentials saved successfully![/bold green]\n")

    def save(self, config_path: Path | None = None) -> None:
        config_file = config_path or (Path.home() / ".uaporter" / "config.yaml")
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(asdict(self), f, default_flow_style=False)


