"""Headless Unity batchmode build orchestrator."""

from __future__ import annotations
from pathlib import Path
import subprocess
from rich.console import Console

from ..core.models import UnityVersion

console = Console()


class UnityBuildError(Exception):
    pass


import time
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

def _monitor_build_process(proc: subprocess.Popen, log_file_path: Path, task_title: str) -> int:
    """Monitor Unity build log in real-time, showing animated live progress spinner and status messages."""
    current_status = "Initializing Unity engine..."
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        TextColumn("[yellow]{task.fields[status]}[/yellow]"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task_id = progress.add_task(task_title, status=current_status)
        
        last_pos = 0
        while proc.poll() is None:
            time.sleep(0.5)
            if log_file_path.exists():
                try:
                    with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                        last_pos = f.tell()

                    for line in new_lines:
                        line = line.strip()
                        if "DisplayProgressbar:" in line:
                            sub = line.split("DisplayProgressbar:")[-1].strip()
                            if sub:
                                current_status = sub
                                progress.update(task_id, status=current_status)
                        elif "[UAPorter]" in line:
                            sub = line.split("[UAPorter]")[-1].strip()
                            if sub:
                                current_status = sub
                                progress.update(task_id, status=current_status)
                        elif "Compiling shader" in line:
                            current_status = line
                            progress.update(task_id, status=current_status)
                        elif "Opening scene" in line or "Loaded scene" in line:
                            current_status = line
                            progress.update(task_id, status=current_status)
                        elif "Start importing" in line:
                            asset_name = line.split("Start importing")[-1].split("using Guid")[0].strip()
                            current_status = f"Importing {Path(asset_name).name}"
                            progress.update(task_id, status=current_status)
                        elif line.startswith("Updating Assets/") or line.startswith("Updating Packages/"):
                            parts = line.split(" - GUID:")[0]
                            asset_file = parts.split("Updating ", 1)[-1].strip()
                            current_status = f"Importing {Path(asset_file).name}"
                            progress.update(task_id, status=current_status)
                        elif "Starting:" in line and "bee_backend" in line:
                            current_status = "Compiling project scripts (Bee)..."
                            progress.update(task_id, status=current_status)
                        elif "Tundra build success" in line:
                            current_status = "Script compilation succeeded"
                            progress.update(task_id, status=current_status)
                        elif "BuildPlayer: start building" in line or "Building player" in line:
                            current_status = "Compiling player binary & shaders..."
                            progress.update(task_id, status=current_status)
                        elif "Begin MonoManager ReloadAssembly" in line:
                            current_status = "Reloading assemblies..."
                            progress.update(task_id, status=current_status)
                        elif "[Package Manager]" in line:
                            current_status = "Resolving packages..."
                            progress.update(task_id, status=current_status)
                except Exception:
                    pass

        return proc.returncode


def _get_project_unity_version(project_path: Path) -> UnityVersion | None:
    """Extract Unity engine version from ProjectVersion.txt if present."""
    import re
    ver_file = project_path / "ProjectSettings" / "ProjectVersion.txt"
    if ver_file.is_file():
        try:
            content = ver_file.read_text(encoding="utf-8")
            match = re.search(r"m_EditorVersion:\s*([^\s]+)", content)
            if match:
                return UnityVersion.parse(match.group(1))
        except Exception:
            pass
    return None


def _verify_build_success(
    returncode: int,
    output_path: Path,
    log_file_path: Path,
    build_type: str = "Linux",
) -> bool:
    """Verify if the build artifact was created and succeeded, tolerating post-build shutdown crashes."""
    if not output_path.exists():
        return False
    if returncode == 0:
        return True
    if returncode in (-6, -11, 134, 139) and log_file_path.is_file():
        try:
            log_content = log_file_path.read_text(encoding="utf-8", errors="ignore")
            success_marker = f"{build_type} Build Succeeded"
            if success_marker in log_content or "Build Succeeded:" in log_content:
                console.print(f"[yellow]Notice: Unity exited with code {returncode} during shutdown, but {build_type} build completed successfully.[/yellow]")
                return True
        except Exception:
            pass
    return False


def _read_build_diagnostics(log_file_path: Path, limit: int = 8) -> str:
    """Return the most useful compiler/build error lines from a Unity log."""
    if not log_file_path.is_file():
        return ""
    try:
        lines = log_file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""

    diagnostics = [
        line.strip()
        for line in lines
        if any(marker in line for marker in ("error CS", "Build Failed", "Scripts have compiler errors"))
    ]
    if not diagnostics:
        return ""
    return " Compiler diagnostics: " + " | ".join(diagnostics[-limit:])


def _clean_stale_locks(project_path: Path) -> None:
    """Clean up stale lockfiles and orphaned temporary sockets from previous aborted runs."""
    import glob
    lock = project_path / "Temp" / "UnityLockfile"
    if lock.exists():
        try:
            lock.unlink()
        except OSError:
            pass

    for sock in glob.glob("/tmp/Y9t*"):
        try:
            Path(sock).unlink(missing_ok=True)
        except OSError:
            pass


def run_headless_build(
    unity_editor_path: Path,
    project_path: Path,
    output_apk_path: Path,
    log_file_path: Path | None = None,
) -> Path:
    """Invoke Unity in headless batchmode to compile the Android APK."""
    if not unity_editor_path.is_file():
        raise FileNotFoundError(f"Unity Editor executable not found at: {unity_editor_path}")

    project_path = project_path.resolve()
    output_apk_path = output_apk_path.resolve()
    output_apk_path.parent.mkdir(parents=True, exist_ok=True)

    if log_file_path is None:
        log_file_path = project_path / "unity_build.log"

    if log_file_path.exists():
        log_file_path.unlink()

    _clean_stale_locks(project_path)

    from ..toolchain.unity_manager import UnityManager
    UnityManager.patch_bee_backend(unity_editor_path)

    unity_version = _get_project_unity_version(project_path)
    # Package resolution may recreate Library/PackageCache after the project
    # patch phase. Sanitize resolved SRP sources immediately before Unity
    # starts compiling assemblies.
    from .project_patcher import sanitize_render_pipeline_package_apis
    sanitize_render_pipeline_package_apis(project_path, unity_version)
    cmd = [
        str(unity_editor_path),
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath", str(project_path),
        "-executeMethod", "UAPorter.Editor.PortBuilder.BuildAndroid",
        "-logFile", str(log_file_path),
        "-apkOutput", str(output_apk_path),
        "-disable-assembly-updater",
    ]

    # -projectImportWorkerCount and -assetServerUseLocal were introduced in Unity 2019.3
    if unity_version is None or unity_version >= UnityVersion(2019, 3, 0):
        import os
        cpu_workers = str(max(2, os.cpu_count() or 4))
        cmd.extend(["-projectImportWorkerCount", cpu_workers, "-assetServerUseLocal"])

    console.print(f"[bold cyan]Launching Unity headless build...[/bold cyan]")

    from ..toolchain.env import get_unity_env
    env = get_unity_env()

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    returncode = _monitor_build_process(proc, log_file_path, "Compiling Android APK")

    if not _verify_build_success(returncode, output_apk_path, log_file_path, "Android"):
        err_msg = f"Unity headless build failed with exit code {returncode}."
        err_msg += _read_build_diagnostics(log_file_path)
        if log_file_path.exists():
            err_msg += f" See log: {log_file_path}"
        raise UnityBuildError(err_msg)

    console.print(f"[bold green]APK built successfully at: {output_apk_path}[/bold green]")
    return output_apk_path


def run_headless_linux_build(
    unity_editor_path: Path,
    project_path: Path,
    output_bin_path: Path,
    log_file_path: Path | None = None,
) -> Path:
    """Invoke Unity in headless batchmode to compile a native Linux Standalone build."""
    if not unity_editor_path.is_file():
        raise FileNotFoundError(f"Unity Editor executable not found at: {unity_editor_path}")

    project_path = project_path.resolve()
    output_bin_path = output_bin_path.resolve()
    output_bin_path.parent.mkdir(parents=True, exist_ok=True)

    if log_file_path is None:
        log_file_path = project_path / "unity_linux_build.log"

    if log_file_path.exists():
        log_file_path.unlink()

    _clean_stale_locks(project_path)

    from ..toolchain.unity_manager import UnityManager
    UnityManager.patch_bee_backend(unity_editor_path)

    unity_version = _get_project_unity_version(project_path)
    from .project_patcher import sanitize_render_pipeline_package_apis
    sanitize_render_pipeline_package_apis(project_path, unity_version)
    cmd = [
        str(unity_editor_path),
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath", str(project_path),
        "-executeMethod", "UAPorter.Editor.PortBuilder.BuildLinux",
        "-logFile", str(log_file_path),
        "-linuxOutput", str(output_bin_path),
        "-disable-assembly-updater",
    ]

    # -projectImportWorkerCount and -assetServerUseLocal were introduced in Unity 2019.3
    if unity_version is None or unity_version >= UnityVersion(2019, 3, 0):
        import os
        cpu_workers = str(max(2, os.cpu_count() or 4))
        cmd.extend(["-projectImportWorkerCount", cpu_workers, "-assetServerUseLocal"])

    console.print(f"[bold cyan]Compiling native Linux Standalone (compiling OpenGL & Vulkan shaders)...[/bold cyan]")

    from ..toolchain.env import get_unity_env
    env = get_unity_env()

    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    returncode = _monitor_build_process(proc, log_file_path, "Compiling Linux Standalone")

    if not _verify_build_success(returncode, output_bin_path, log_file_path, "Linux"):
        err_msg = f"Unity headless Linux build failed with exit code {returncode}."
        err_msg += _read_build_diagnostics(log_file_path)
        if log_file_path.exists():
            err_msg += f" See log: {log_file_path}"
        raise UnityBuildError(err_msg)

    console.print(f"[bold green]Linux Standalone built successfully at: {output_bin_path}[/bold green]")
    return output_bin_path
