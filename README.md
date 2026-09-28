# Universal Unity Auto-Porter (UAPorter)

> **⚠️ EXPERIMENTAL — v0.1.0**: This project is in early development and may not work correctly. Many features are incomplete or untested. Use at your own risk. Bug reports and contributions are welcome!

Universal Unity Auto-Porter (`uaporter`) is a CLI tool designed to port desktop Unity games to **Linux / Steam Deck** (via zero-recompile runtime swap) and **Android APK** (via automated decompilation, touch control injection, and headless Unity rebuilds).

## How to Download & Install

### Option 1 — Clone & run (recommended)
```bash
git clone https://github.com/ediussss/uaporter.git
cd uaporter
```
Then launch directly — it auto-installs all dependencies on first run:
```bash
# Linux / Steam Deck / macOS
./uaporter scan /path/to/YourGame

# Windows
uaporter.bat scan C:\path\to\YourGame
```

### Option 2 — Install via pip
```bash
pip install git+https://github.com/ediussss/uaporter.git
uaporter scan /path/to/YourGame
```

### Requirements
- **Python 3.10+**
- **Linux / macOS** or **Windows**
- Android porting requires: Android SDK + JDK 17
- A free [Unity Personal license](https://unity.com/products) (only needed for games that require recompilation)
- AssetRipper — auto-downloaded on first Android port run


## Features

- **Pre-Flight Scanner:** Fast diagnostic inspection of game directory, detecting Unity engine version, scripting backend (Mono vs IL2CPP), and third-party plugins (`steam_api64.dll`, `discord_rpc.dll`, etc.).
- **Desktop Player Swap & Native Rebuilds:** Port Windows Mono games to Linux Standalone and Steam Deck (zero-recompile runtime swap or native headless rebuilds), generating automatic GameScope wrappers and `.desktop` shortcuts.
- **Universal Engine Support (Unity 2017–2023+):** Automated dynamic dependency resolution (`libxml2.so.2`, OpenSSL 1.1 `libssl.so.1.1` for Roslyn C# compiler), version-adaptive package manifests (Unity 2018 built-in uGUI & TMP 1.4.1, Unity 2019 TMP 2.0.0, Unity 2020–2022+ TMP 3.0.6 & 2D modules), automated resolution dialog suppression for legacy engines, and automated Linux patch for Unity Bee build system (`--stdin-canary` hang workaround).
- **Version-Adaptive Headless Builder & Teardown Resilience:** Dynamically adjusts batchmode arguments per engine version (e.g. reserving multi-worker import flags for Unity 2019.3+) and gracefully tolerates legacy Mono teardown signals (`SIGABRT -6` / `SIGSEGV -11`) once build artifacts are verified on disk.
- **Cross-Platform PostProcessing & ComputeShader Restoration:** Automatically remaps decompiled `PostProcessResources.asset` and scenes to authentic official package shaders and compute shaders (`com.unity.postprocessing`), restoring accurate AutoExposure, Bloom, and Ambient Occlusion without dark-screen rendering errors.
- **Universal Render Pipeline (URP 2D/3D) & Dummy Shader Sanitization:** Automatic pre-flight URP detection across Managed assemblies, ProjectSettings, and asset hierarchies. Pinned engine-matched URP packages (`com.unity.render-pipelines.universal` & `core`), automated assembly duplicate conflict resolution, GUID remapping for URP components (`Volume`, `VolumeProfile`, `UniversalRenderPipelineAsset`, `Renderer2DData`, `Bloom`), Tilemap engine MonoScripts (`Tile`, `TileBase`), package materials, and automatic transformation of AssetRipper legacy surface dummy shaders into native URP `Universal2D` / `UniversalForward` / `SRPDefaultUnlit` passes with sprite/unlit fallbacks, eliminating black-screen and invisible rendering issues across all Unity versions.
- **Layout & Developer Intent Preservation:** Strictly preserves native scene UI anchors, off-screen animated panels, and CanvasScaler parameters, ensuring animated menus, popups, and HUDs transition as designed without overlapping text or visual duplication.
- **High-Speed Quality-Preserving Asset Pipeline:** Optimizes `EditorSettings.asset` and diffuse texture imports for a 50x speedup while strictly preserving high visual fidelity for normal maps, UI sprites, and lightmaps.
- **TextMeshPro Cross-Version UI Harmonization:** Automatically detects and harmonizes split vs combined TextMeshPro alignment fields (e.g. `m_textAlignment: 65535` vs `m_HorizontalAlignment` / `m_VerticalAlignment`), ensuring speech bubbles, dialogue boxes, and UI text layout render with pixel accuracy across all engine generations.
- **AssetRipper Live Extraction & Smart Reuse:** Real-time animated status streaming during AssetRipper extraction (scanning game files, asset discovery, extracting textures/meshes/audio), intelligent existing-project reuse (skips redundant 5+ minute extractions during re-runs or retries, with `--force-decompile` for fresh extractions), automated C# injection (`TouchManager.cs`), headless Unity build orchestration, and APK signing.
- **Mobile Optimization:** ASTC texture compression presets and quality profiles (Flagship, Balanced, Battery Saver).

## Instant Quickstart (Zero-Setup Auto-Install)

No manual pip installation or virtual environment setup is needed! The launcher automatically initializes everything on first run.

- **On Linux / Steam Deck / macOS:**
  ```bash
  ./uaporter scan /path/to/Game
  ./uaporter port /path/to/Game -t android
  ```
- **On Windows:**
  ```cmd
  uaporter.bat scan C:\path\to\Game
  uaporter.bat port C:\path\to\Game -t android
  ```

*(If dependencies are missing, `uaporter` detects it, installs them silently in seconds, and runs your command).*

## Unity Free Personal License (10-Second Setup)

When recompiling Android APKs or games that require native shader rebuilding (e.g. DirectX-only titles), Unity requires an active free Personal license.
- **You do NOT need to install any Unity versions in Unity Hub.** UAPorter installs and manages the exact engine build versions automatically.
- **Activating your free license:**
  1. Open **Unity Hub** and sign in with any free Unity account.
  2. Click the **Gear icon (⚙️ Preferences)** in the top-left.
  3. Select **Licenses** in the left menu.
  4. Click **Add** -> **Get a free Personal license** -> **Agree and get Personal edition license**.
- That's it! UAPorter will automatically detect your free license session and proceed with compilation.

## Running Tests
```bash
pytest tests/ -v
```
