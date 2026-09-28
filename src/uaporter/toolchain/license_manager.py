"""Automated Unity licensing helper."""

from __future__ import annotations
from pathlib import Path
import subprocess
import shutil
from rich.console import Console

console = Console()


class UnityLicenseManager:
    """Manages Unity batchmode licensing and activation."""

    @staticmethod
    def get_system_license_file() -> Path | None:
        """Find Unity_lic.ulf on standard OS paths."""
        candidates = [
            Path.home() / ".local" / "share" / "unity3d" / "Unity" / "Unity_lic.ulf",
            Path("/Library/Application Support/Unity/Unity_lic.ulf"),
            Path.home() / "AppData" / "Local" / "Unity" / "Unity_lic.ulf",
        ]
        for p in candidates:
            if p.is_file():
                return p
        return None

    @staticmethod
    def is_licensed(unity_editor_path: Path) -> bool:
        """Check if Unity Editor is licensed (checks local .ulf first, then tests binary)."""
        if UnityLicenseManager.get_system_license_file():
            return True

        from .env import get_unity_env
        cmd = [
            str(unity_editor_path),
            "-batchmode",
            "-nographics",
            "-quit"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=get_unity_env())
        output = (res.stderr + res.stdout).lower()
        if "no valid unity license" in output or "failed to activate" in output or "missing or bad username" in output:
            return False
        return True

    @staticmethod
    def create_activation_file(unity_editor_path: Path, output_dir: Path) -> Path | None:
        """Generate a .alf manual activation file."""
        from .env import get_unity_env
        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            str(unity_editor_path),
            "-batchmode",
            "-nographics",
            "-createManualActivationFile"
        ]
        subprocess.run(cmd, cwd=str(output_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=get_unity_env())
        for f in output_dir.glob("*.alf"):
            return f
        return None

    @staticmethod
    def install_license_file(unity_editor_path: Path, ulf_path: Path) -> bool:
        """Apply a downloaded .ulf license file."""
        from .env import get_unity_env
        cmd = [
            str(unity_editor_path),
            "-batchmode",
            "-nographics",
            "-manualLicenseFile", str(ulf_path),
            "-quit"
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=get_unity_env())
        return UnityLicenseManager.is_licensed(unity_editor_path)

    @staticmethod
    def ensure_valid_license(unity_editor_path: Path, console=None) -> bool:
        """Verify license before doing any heavy operations. Prompt user if missing/invalid."""
        from rich.console import Console
        from rich.panel import Panel
        import click
        import webbrowser

        c = console or Console()
        c.print("[cyan]Verifying Unity Editor license status...[/cyan]")
        if UnityLicenseManager.is_licensed(unity_editor_path):
            c.print("[bold green]✓ Unity Editor is licensed.[/bold green]")
            return True

        c.print()
        c.print("[bold yellow]════════════════════ Unity License Activation Required ════════════════════[/bold yellow]")
        c.print("[bold cyan]Note:[/bold cyan] You do [bold green]NOT[/bold green] need to install any Unity Editor versions in Unity Hub.")
        c.print("UAPorter has already downloaded and installed the required Unity build engine for you.")
        c.print("Unity Hub is only used to manage your [bold]free Personal License[/bold] session.\n")

        from .hub_bridge import UnityHubBridge
        hub_bin = UnityHubBridge.find_hub_binary()
        if hub_bin:
            c.print(f"[bold cyan]Unity Hub detected at:[/bold cyan] {hub_bin}")
            launch_hub = click.confirm("Would you like UAPorter to open Unity Hub for you now?", default=True)
            if launch_hub:
                import subprocess
                subprocess.Popen([str(hub_bin)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                c.print("\n" + "─" * 70)
                c.print("[bold green]HOW TO ACTIVATE YOUR FREE LICENSE IN UNITY HUB (Takes 10 seconds):[/bold green]")
                c.print("  [bold white]1. Sign In:[/bold white] Click the profile icon or 'Sign In' in Unity Hub.")
                c.print("  [bold white]2. Open Settings:[/bold white] Click the [bold yellow]Gear icon (⚙️ Preferences)[/bold yellow] in the top-left.")
                c.print("  [bold white]3. Select Licenses:[/bold white] Click on [bold cyan]'Licenses'[/bold cyan] in the left sidebar menu.")
                c.print("  [bold white]4. Add Free License:[/bold white] Click the blue [bold cyan]'Add'[/bold cyan] button (or 'Activate new license').")
                c.print("  [bold white]5. Confirm:[/bold white] Select [bold green]'Get a free Personal license'[/bold green] -> click [bold]'Agree and get Personal edition license'[/bold].")
                c.print("─" * 70 + "\n")
                
                while True:
                    click.prompt("Press Enter once you have activated your free license in Unity Hub", default="")
                    c.print("[cyan]Checking license status...[/cyan]")
                    if UnityLicenseManager.is_licensed(unity_editor_path):
                        c.print("[bold green]✓ License successfully detected from Unity Hub session![/bold green]\n")
                        return True
                    else:
                        retry = click.confirm("[yellow]License not detected yet. Did you finish clicking 'Agree and get Personal license' in Unity Hub? Try again?[/yellow]", default=True)
                        if not retry:
                            break

        # Step 1: Generate .alf as alternative
        c.print("\n[cyan]Alternative: Offline license activation file (.alf)...[/cyan]")
        alf_dir = Path.home() / ".uaporter" / "license"
        alf_path = UnityLicenseManager.create_activation_file(unity_editor_path, alf_dir)
        if not alf_path:
            c.print("[bold red]Failed to generate .alf activation file.[/bold red]")
            return False

        c.print(f"[bold green]✓ Activation file created at:[/bold green] [cyan]{alf_path}[/cyan]\n")

        # Step 2: Open browser or display link
        activate_url = "https://license.unity3d.com/manual"
        c.print(f"Opening [link={activate_url}]{activate_url}[/link] in your browser...")
        try:
            webbrowser.open(activate_url)
        except Exception:
            pass

        c.print()
        c.print(Panel(
            f"1. On the web page ([bold cyan]{activate_url}[/bold cyan]), upload this file:\n   [bold]{alf_path}[/bold]\n"
            "2. Select '[bold]Unity Personal Edition[/bold]' (Free) and choose any company option (e.g. 'I don't use Unity in a professional capacity').\n"
            "3. Click Download to get your [bold green]Unity_lic.ulf[/bold green] file.",
            title="[bold green]Simple 3-Step Free Activation[/bold green]",
            border_style="green"
        ))

        ulf_input = click.prompt(
            "\nEnter path to downloaded .ulf license file (or drag & drop here)",
            type=str
        ).strip().strip("'\"")

        ulf_file = Path(ulf_input).expanduser().resolve()
        if not ulf_file.is_file():
            c.print(f"[bold red]File not found: {ulf_file}[/bold red]")
            return False

        c.print("[cyan]Installing license...[/cyan]")
        if UnityLicenseManager.install_license_file(unity_editor_path, ulf_file):
            c.print("[bold green]✓ Unity License successfully activated! This will never be asked again.[/bold green]\n")
            return True
        else:
            c.print("[bold red]License installation failed. Please check the .ulf file.[/bold red]")
            return False
