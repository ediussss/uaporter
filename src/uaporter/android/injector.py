"""Touch control overlay and asset injector for Android projects."""

from __future__ import annotations
from pathlib import Path
import shutil

ASSETS_DIR = Path(__file__).parent / "assets"


def inject_android_assets(project_path: Path, is_android: bool = True) -> list[str]:
    """Inject TouchManager runtime scripts and PortBuilder editor scripts into decompiled project."""
    project_path = project_path.resolve()
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(f"Unity Assets directory not found in {project_path}")

    injected: list[str] = []

    # 1. Inject Editor/PortBuilder.cs
    editor_dest = assets_dir / "Editor" / "UAPorter"
    editor_dest.mkdir(parents=True, exist_ok=True)
    port_builder_src = ASSETS_DIR / "Editor" / "PortBuilder.cs"
    if port_builder_src.is_file():
        shutil.copy2(port_builder_src, editor_dest / "PortBuilder.cs")
        injected.append("Assets/Editor/UAPorter/PortBuilder.cs")

    # 2. Inject Runtime/TouchManager.cs (only for Android ports)
    if is_android:
        runtime_dest = assets_dir / "Scripts" / "UAPorter"
        runtime_dest.mkdir(parents=True, exist_ok=True)
        touch_mgr_src = ASSETS_DIR / "Runtime" / "TouchManager.cs"
        if touch_mgr_src.is_file():
            shutil.copy2(touch_mgr_src, runtime_dest / "TouchManager.cs")
            injected.append("Assets/Scripts/UAPorter/TouchManager.cs")

    return injected
