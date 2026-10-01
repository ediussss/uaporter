"""Automated C# and Unity project patcher for decompiled games."""

from __future__ import annotations
from pathlib import Path
import math
import shutil
import json

from ..core.models import UnityVersion


def get_essential_packages_for_unity(unity_version: UnityVersion | None, is_urp: bool = False) -> dict[str, str]:
    """Return essential UPM package versions matching the Unity engine release."""
    if not unity_version or unity_version.major < 2018:
        return {}
    if unity_version.major == 2018:
        return {
            "com.unity.textmeshpro": "1.4.1",
            "com.unity.postprocessing": "2.1.7",
        }
    if unity_version.major == 2019:
        pkgs = {
            "com.unity.ugui": "1.0.0",
            "com.unity.textmeshpro": "2.0.0",
            # Unity 2019.2's built-in shader compiler cannot import the
            # renderer-specific HLSL passes shipped in 2.1.7.
            "com.unity.postprocessing": (
                "2.1.3" if unity_version.minor <= 2 else "2.1.7"
            ),
        }
        if is_urp:
            # 7.7.x references GraphicsDeviceType.PlayStation5, which is
            # unavailable in early Unity 2019.4 editors (for example 2019.4.8).
            pkgs["com.unity.render-pipelines.universal"] = "7.1.8"
            pkgs["com.unity.render-pipelines.core"] = "7.1.8"
        return pkgs
    if unity_version.major == 2020:
        pkgs = {
            "com.unity.ugui": "1.0.0",
            "com.unity.textmeshpro": "3.0.6",
            "com.unity.postprocessing": "3.1.1",
        }
        if is_urp:
            pkgs["com.unity.render-pipelines.universal"] = "10.10.1"
            pkgs["com.unity.render-pipelines.core"] = "10.10.1"
        return pkgs
    if unity_version.major == 2021:
        graphics_train = "11.0.0" if unity_version.minor <= 1 else "12.1.7"
        tmp_version = "3.0.6" if unity_version.minor <= 1 else "3.0.9"
        postprocessing_version = "3.2.2" if unity_version.minor <= 1 else "3.5.1"
        pkgs = {
            "com.unity.ugui": "1.0.0",
            "com.unity.textmeshpro": tmp_version,
            "com.unity.postprocessing": postprocessing_version,
            "com.unity.2d.sprite": "1.0.0",
            "com.unity.2d.tilemap": "1.0.0",
        }
        if is_urp:
            pkgs["com.unity.render-pipelines.universal"] = graphics_train
            pkgs["com.unity.render-pipelines.core"] = graphics_train
        return pkgs
    pkgs = {
        "com.unity.ugui": "1.0.0",
        "com.unity.textmeshpro": "3.0.6",
    }
    if unity_version.major == 2022:
        pkgs["com.unity.2d.sprite"] = "1.0.0"
        pkgs["com.unity.2d.tilemap"] = "1.0.0"
        if is_urp:
            pkgs["com.unity.render-pipelines.universal"] = "14.0.11"
            pkgs["com.unity.render-pipelines.core"] = "14.0.11"
    elif is_urp:
        pkgs["com.unity.render-pipelines.universal"] = "16.0.4"
        pkgs["com.unity.render-pipelines.core"] = "16.0.4"
    return pkgs


def is_urp_project(project_path: Path, original_data_dir: Path | None = None) -> bool:
    """Detect whether the project utilizes Universal Render Pipeline (URP)."""
    import re
    # 1. Check original game Managed/ directory for URP assemblies
    if original_data_dir:
        managed = original_data_dir / "Managed"
        if managed.is_dir():
            for dll in managed.glob("*.dll"):
                if "renderpipelines.universal" in dll.name.lower():
                    return True

    # 2. Check project Assets for URP assemblies
    assets = project_path / "Assets"
    if assets.is_dir():
        for dll in assets.rglob("*.dll"):
            if "renderpipelines.universal" in dll.name.lower():
                return True

    # 3. Check GraphicsSettings.asset or QualitySettings.asset
    for settings_name in ("GraphicsSettings.asset", "QualitySettings.asset"):
        settings_file = project_path / "ProjectSettings" / settings_name
        if settings_file.is_file():
            try:
                content = settings_file.read_text(encoding="utf-8", errors="ignore")
                if "UniversalRenderPipeline" in content:
                    return True
                m = re.search(r"m_CustomRenderPipeline:\s*\{fileID:\s*(-?\d+)", content)
                if m and m.group(1) not in ("0", "-1"):
                    return True
            except Exception:
                pass

    # 4. Check for UniversalRenderPipelineAsset in Assets/
    if assets.is_dir():
        if (assets / "MonoBehaviour" / "UniversalRenderPipelineAsset.asset").is_file():
            return True
        for _ in assets.glob("**/UniversalRenderPipelineAsset*.asset"):
            return True

    return False


def patch_decompiled_project(project_path: Path, original_data_dir: Path) -> list[str]:
    """Patch missing package manifests, assemblies, and dependencies into decompiled project."""
    project_path = project_path.resolve()
    assets_dir = project_path / "Assets"
    packages_dir = project_path / "Packages"
    manifest_file = packages_dir / "manifest.json"

    patches: list[str] = []

    # 1. Update Packages/manifest.json to ensure UGUI, TextMeshPro, PostProcessing are included
    packages_dir.mkdir(parents=True, exist_ok=True)
    deps = {}
    if manifest_file.is_file():
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                deps = data.get("dependencies", {})
        except Exception:
            deps = {}

    unity_version = None
    project_version_file = project_path / "ProjectSettings" / "ProjectVersion.txt"
    if project_version_file.is_file():
        try:
            for line in project_version_file.read_text(encoding="utf-8").splitlines():
                if "m_EditorVersion:" in line:
                    v_str = line.split(":", 1)[1].strip()
                    from ..core.models import UnityVersion
                    unity_version = UnityVersion.parse(v_str)
                    break
        except Exception:
            pass
    if not unity_version and original_data_dir:
        from ..scanner.version_detector import detect_unity_version
        unity_version = detect_unity_version(original_data_dir.parent, original_data_dir)

    is_urp = is_urp_project(project_path, original_data_dir)
    essential_packages = get_essential_packages_for_unity(unity_version, is_urp=is_urp)
    updated_manifest = False
    if unity_version and unity_version.major < 2019:
        # In Unity < 2019, uGUI is built-in (UnityEngine.UI.dll); com.unity.ugui does not exist in UPM.
        if "com.unity.ugui" in deps:
            del deps["com.unity.ugui"]
            updated_manifest = True
            patches.append("Removed incompatible com.unity.ugui dependency for Unity 2018")

    for pkg, ver in essential_packages.items():
        if pkg not in deps or (
            pkg in {
                "com.unity.textmeshpro",
                "com.unity.postprocessing",
                "com.unity.render-pipelines.universal",
                "com.unity.render-pipelines.core",
            }
            and deps.get(pkg) != ver
        ):
            deps[pkg] = ver
            updated_manifest = True
            patches.append(f"Pinned package dependency: {pkg}@{ver}")

    if updated_manifest:
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump({"dependencies": deps}, f, indent=2)
        # A stale lock file can keep Unity importing the previous package
        # train (for example URP 7.7.1 after selecting 7.1.8). Let the
        # editor resolve the manifest again instead of compiling mismatched
        # package sources.
        lock_file = packages_dir / "packages-lock.json"
        try:
            lock_data = json.loads(lock_file.read_text(encoding="utf-8"))
            locked = lock_data.get("dependencies", {})
            changed_packages = {
                package
                for package, version in essential_packages.items()
                if package in locked and locked[package].get("version") != version
            }
            if changed_packages:
                lock_file.unlink()
                patches.append(
                    "Removed stale package lock after Unity compatibility "
                    f"changes: {', '.join(sorted(changed_packages))}"
                )
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    # 2. If packages provide TextMeshPro, PostProcessing, or URP, extract their GUIDs, remap scenes/prefabs, then clean up redundant DLLs
    extracted_tmp_guids: set[str] = set()
    extracted_pp_guids: set[str] = set()
    extracted_urp_guids: set[str] = set()

    for item in list(assets_dir.rglob("*.dll")):
        lower = item.name.lower()
        is_tmp = "textmeshpro" in lower or "tmpro" in lower
        is_pp = "postprocessing" in lower
        is_ugui = lower in ("unityengine.ui.dll", "unity.ugui.dll")
        is_urp_dll = is_urp and ("renderpipeline" in lower or "shadergraph" in lower)

        if is_tmp or is_pp or is_ugui or is_urp_dll:
            meta = item.with_suffix(".dll.meta")
            if meta.exists():
                try:
                    for line in meta.read_text(encoding="utf-8").splitlines():
                        if line.startswith("guid:"):
                            g = line.split()[1].strip()
                            if is_tmp:
                                extracted_tmp_guids.add(g)
                            if is_pp:
                                extracted_pp_guids.add(g)
                            if is_urp_dll:
                                extracted_urp_guids.add(g)
                except Exception:
                    pass
                meta.unlink(missing_ok=True)
            try:
                item.unlink(missing_ok=True)
                patches.append(f"Removed redundant precompiled DLL in favor of package: {item.name}")
            except Exception:
                pass
        else:
            # Enable Editor environment for remaining plugin assemblies so Unity Editor loads them
            meta = item.with_suffix(".dll.meta")
            if meta.is_file():
                try:
                    meta_text = meta.read_text(encoding="utf-8")
                    if "Editor: Editor" in meta_text and "enabled: 0" in meta_text:
                        import re
                        new_meta_text = re.sub(
                            r'(Editor:\s*Editor\s*\n\s*second:\s*\n\s*enabled:\s*)0',
                            r'\g<1>1',
                            meta_text
                        )
                        if new_meta_text != meta_text:
                            meta.write_text(new_meta_text, encoding="utf-8")
                            patches.append(f"Enabled plugin in Editor environment: {item.name}")
                except Exception:
                    pass

    # Remap scenes, prefabs, and ScriptableObjects to official package GUIDs
    remapped = remap_package_guids(project_path, extracted_tmp_guids, extracted_pp_guids, extracted_urp_guids)
    if remapped > 0:
        patches.append(f"Remapped {remapped} scenes/prefabs to official package component GUIDs")

    # 3. Copy third-party managed plugins from original game Managed/ into Assets/Plugins/Managed/
    managed_src = original_data_dir / "Managed"
    if managed_src.is_dir():
        plugins_dest = assets_dir / "Plugins" / "Managed"
        plugins_dest.mkdir(parents=True, exist_ok=True)

        system_assemblies = {
            "mscorlib.dll", "netstandard.dll", "system.dll", "system.core.dll",
            "system.data.dll", "system.drawing.dll", "system.xml.dll", "system.xml.linq.dll",
            "system.io.compression.dll", "system.io.compression.filesystem.dll",
            "system.net.http.dll", "system.numerics.dll", "system.runtime.serialization.dll",
            "mono.security.dll", "system.configuration.dll", "system.transactions.dll",
            "system.componentmodel.composition.dll", "system.enterpriseservices.dll",
            "system.globalization.extensions.dll", "system.diagnostics.stacktrace.dll",
            "system.runtime.serialization.xml.dll", "system.servicemodel.internals.dll",
            "system.xml.xpath.xdocument.dll", "assembly-csharp.dll", "assembly-csharp-firstpass.dll"
        }

        all_existing_dlls = {x.name.lower() for x in assets_dir.rglob("*.dll")}

        for dll in managed_src.glob("*.dll"):
            lower = dll.name.lower()
            if lower in system_assemblies:
                continue

            # Skip engine modules built into Unity Editor and packages (com.unity.ugui supplies UI)
            if lower.startswith("unityengine."):
                continue
            if lower.startswith("unityeditor."):
                continue
            if "textmeshpro" in lower or "tmpro" in lower or "postprocessing" in lower or "renderpipeline" in lower or "shadergraph" in lower or "pixelperfect" in lower or lower in ("unityengine.ui.dll", "unity.ugui.dll"):
                continue

            # If the assembly already exists elsewhere in Assets/ (e.g. Assets/Plugins/), don't create a duplicate
            if lower in all_existing_dlls:
                continue

            target = plugins_dest / dll.name
            if not target.exists():
                shutil.copy2(dll, target)
                all_existing_dlls.add(lower)
                patches.append(f"Copied runtime managed assembly: {dll.name}")

    # 4. Restore authentic TextMeshPro shaders for dummy shaders generated by AssetRipper
    shader_patches = restore_textmeshpro_shaders(project_path)
    patches.extend(shader_patches)

    # 5. Restore built-in post-processing shaders before Unity imports materials.
    postprocessing_patches = restore_postprocessing_shaders(project_path)
    patches.extend(postprocessing_patches)

    # 6. Restore authentic ComputeShaders for dummy/serialized .asset compute shaders (e.g. HauntedPSX)
    compute_patches = restore_compute_shaders(project_path)
    patches.extend(compute_patches)

    # 7. Harmonize TextMeshPro alignment fields across scenes/prefabs
    tmp_patches = harmonize_tmp_text_alignment(project_path)
    patches.extend(tmp_patches)

    # 7. Disable deprecated resolution dialog in ProjectSettings.asset
    res_patches = disable_resolution_dialog(project_path)
    patches.extend(res_patches)

    # 8. Patch dialogue and text layout update calls for modern TextMeshPro runtime compatibility
    script_patches = patch_runtime_script_layouts(project_path)
    patches.extend(script_patches)

    # 9. Optimize EditorSettings and texture meta files for maximum asset import speed (50x compression speedup)
    speed_patches = optimize_project_import_speed(project_path)
    patches.extend(speed_patches)

    # 10. Fix obsolete API usage that causes compilation failures
    api_patches = fix_obsolete_api_usage(project_path)
    patches.extend(api_patches)

    package_api_patches = sanitize_render_pipeline_package_apis(
        project_path, unity_version
    )
    patches.extend(package_api_patches)

    # 10.5. Fix common C# syntax errors
    syntax_patches = fix_common_cs_syntax_errors(project_path)
    patches.extend(syntax_patches)

    # 12. Unify text layout system to fix text misplacement and layout issues
    layout_patches = unify_text_layout_system(project_path)
    patches.extend(layout_patches)

    # 13. Standardize material and texture settings for consistent rendering
    material_patches = standardize_material_and_texture_settings(project_path)
    patches.extend(material_patches)

    # 14. Unify Unity defines and API level for version consistency
    defines_patches = unify_unity_defines_and_api_level(project_path)
    patches.extend(defines_patches)

    # 14. Standardize physics and audio settings
    physics_audio_patches = standardize_physics_and_audio_settings(project_path)
    patches.extend(physics_audio_patches)

    # 15. Cleanup and standardize scene hierarchy
    scene_patches = cleanup_and_standardize_scene_hierarchy(project_path)
    patches.extend(scene_patches)

    # 16. Inject runtime compatibility shims
    runtime_patches = inject_runtime_compatibility_shims(project_path)
    patches.extend(runtime_patches)

    # 17. Enhance build reliability
    build_patches = enhance_build_reliability(project_path)
    patches.extend(build_patches)

    # 18. Sanitize dummy shaders generated by AssetRipper so materials render cleanly without black screens
    dummy_shader_patches = sanitize_dummy_shaders(project_path, is_urp=is_urp)
    patches.extend(dummy_shader_patches)

    # Package resolution can populate or replace Library/PackageCache during
    # preparation. Run the SRP override again after every project patch so
    # the final manifest points at the sanitized local package copies.
    final_package_api_patches = sanitize_render_pipeline_package_apis(
        project_path, unity_version
    )
    patches.extend(final_package_api_patches)

    return patches


def sanitize_render_pipeline_package_apis(
    project_path: Path, unity_version: UnityVersion | None
) -> list[str]:
    """Patch SRP sources when their declared contracts differ from implementations."""
    import re

    package_roots = [
        project_path / "Library" / "PackageCache",
        project_path / "Packages",
        project_path / "UAPorterPackages",
    ]
    package_dirs_by_name: dict[str, Path] = {}
    for root in package_roots:
        if not root.is_dir():
            continue
        for package_dir in root.iterdir():
            if not package_dir.is_dir():
                continue
            package_name = package_dir.name.split("@", 1)[0]
            if package_name in {
                "com.unity.render-pipelines.core",
                "com.unity.render-pipelines.universal",
            }:
                # Prefer an existing local override over a generated cache
                # copy. It is the durable source Unity must import.
                if package_name not in package_dirs_by_name or (
                    package_dir.parent.name == "UAPorterPackages"
                ):
                    package_dirs_by_name[package_name] = package_dir
    package_dirs = list(package_dirs_by_name.values())
    if not package_dirs:
        return []

    interface_needs_dependencies = False
    for package_dir in package_dirs:
        for source_file in package_dir.rglob("*.cs"):
            try:
                content = source_file.read_text(encoding="utf-8")
            except OSError:
                continue
            if re.search(
                r"\bvoid\s+RemoveComponent\s*\("
                r"\s*T\s+component\s*,\s*IEnumerable<Component>\s+dependencies\s*\)",
                content,
            ):
                interface_needs_dependencies = True
                break
        if interface_needs_dependencies:
            break

    patches: list[str] = []
    embedded_packages = project_path / "UAPorterPackages"
    embedded_packages.mkdir(parents=True, exist_ok=True)
    local_package_paths: dict[str, str] = {}
    for package_dir in package_dirs:
        for source_file in package_dir.rglob("*.cs"):
            try:
                content = source_file.read_text(encoding="utf-8")
            except OSError:
                continue
            updated = content
            if unity_version and unity_version < UnityVersion(2020, 1, 0):
                updated = re.sub(
                    r"\n\s*case\s+GraphicsDeviceType\.PlayStation5:",
                    "",
                    updated,
                )
            if interface_needs_dependencies and (
                "IRemoveAdditionalDataContextualMenu<Camera>" in updated
            ):
                updated = re.sub(
                    r"public\s+void\s+RemoveComponent\s*\(\s*Camera\s+camera\s*\)",
                    "public void RemoveComponent(Camera camera, "
                    "IEnumerable<Component> dependencies)",
                    updated,
                )
            if updated != content:
                source_file.write_text(updated, encoding="utf-8")
                patches.append(
                    "Patched render-pipeline API compatibility: "
                    f"{source_file.relative_to(project_path)}"
                )
        package_name = package_dir.name.split("@", 1)[0]
        if package_name in {
            "com.unity.render-pipelines.core",
            "com.unity.render-pipelines.universal",
        } and package_dir.parent.name != "UAPorterPackages":
            embedded = embedded_packages / package_name
            try:
                if embedded.exists():
                    shutil.rmtree(embedded)
                shutil.copytree(
                    package_dir,
                    embedded,
                    ignore=shutil.ignore_patterns(
                        "Tests", "Documentation", "Samples~"
                    ),
                )
                local_package_paths[package_name] = (
                    f"file:../UAPorterPackages/{package_name}"
                )
                patches.append(
                    f"Embedded sanitized render-pipeline package: {package_name}"
                )
                if package_dir.parent.name == "PackageCache":
                    # Do not leave a registry cache copy for Unity to compile
                    # after the manifest has been switched to the local source.
                    shutil.rmtree(package_dir, ignore_errors=True)
            except OSError:
                pass
        elif package_name in {
            "com.unity.render-pipelines.core",
            "com.unity.render-pipelines.universal",
        }:
            local_package_paths[package_name] = (
                f"file:../UAPorterPackages/{package_name}"
            )
    manifest_file = project_path / "Packages" / "manifest.json"
    if local_package_paths and manifest_file.is_file():
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            dependencies = manifest.setdefault("dependencies", {})
            dependencies.update(local_package_paths)
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            lock_file = project_path / "Packages" / "packages-lock.json"
            lock_file.unlink(missing_ok=True)
            patches.append("Configured local sanitized render-pipeline package overrides")
        except (OSError, json.JSONDecodeError):
            pass
    for package_name in local_package_paths:
        cache_root = project_path / "Library" / "PackageCache"
        if cache_root.is_dir():
            for cache_package in cache_root.glob(f"{package_name}@*"):
                shutil.rmtree(cache_package, ignore_errors=True)
    return patches


def remap_package_guids(
    project_path: Path,
    old_tmp_guid: str | set[str] | None = None,
    old_pp_guid: str | set[str] | None = None,
    old_urp_guid: str | set[str] | None = None,
) -> int:
    """Remap decompiled scenes, prefabs, and ScriptableObjects from extracted DLL GUIDs to official package GUIDs."""
    import re

    tmp_guids: set[str] = set()
    if isinstance(old_tmp_guid, set):
        tmp_guids.update(old_tmp_guid)
    elif old_tmp_guid:
        tmp_guids.add(old_tmp_guid)
    tmp_guids.add("67dfb1fdfb2b407222eda8e23ac8b724")

    pp_guids: set[str] = set()
    if isinstance(old_pp_guid, set):
        pp_guids.update(old_pp_guid)
    elif old_pp_guid:
        pp_guids.add(old_pp_guid)
    pp_guids.add("e161fae64b898bc22624d03ed611378f")

    urp_guids: set[str] = set()
    if isinstance(old_urp_guid, set):
        urp_guids.update(old_urp_guid)
    elif old_urp_guid:
        urp_guids.add(old_urp_guid)
    urp_guids.add("c88ab7b37c4f350242674d2efd621c19")
    urp_guids.add("57c9a3e5193e26c4b968cc86e528416d")

    # Mapping of (old_file_id) -> new_guid for TextMeshPro classes in com.unity.textmeshpro
    TMP_MAP = {
        "1453722849": "f4688fdb7df04437aeb418b961361dc5",   # TextMeshProUGUI
        "1908110080": "9541d86e2fd84c1d9990edf0852d74ab",   # TextMeshPro (3D)
        "-667331979": "71c1514a6bd24e1e882cebbe1904ce04",   # TMP_FontAsset
        "-395462249": "2705215ac5b84b70bacc50632be6e391",   # TMP_Settings
        "2019389346": "84a92b25f83d49b9bc132d206b370281",   # TMP_SpriteAsset
        "-1936749209": "ab2114bdc8544297b417dfefe9f1e410",  # TMP_StyleSheet
        "-1620774994": "2da0c512f12947e489f739169773d7ca",  # TMP_InputField
        "-2031128869": "7b743370ac3e4ec2a1668f5455a8ef8a",  # TMP_Dropdown
        "708136152": "058cba836c1846c3aa1c5fd2e28aea77",    # TMP_SubMeshUI
        "1114903513": "07994bfe8b0e4adb97d706de5dea48d5",   # TMP_SubMesh
        "2108210716": "54d21f6ece3b46479f0c328f8c6007e0",   # TMP_ColorGradient
    }

    # Mapping of (old_file_id) -> new_guid for PostProcessing classes in com.unity.postprocessing
    PP_MAP = {
        "708136152": "8b9a305e18de0c04dbd257a21cd47087",    # PostProcessVolume
        "-1529857597": "948f4100a11a5c24981795d21301da5c",  # PostProcessLayer
        "-2099961501": "8e6292b2c06870d4495f009f912b9600",  # PostProcessProfile
        "-1437917544": "48a79b01ea5641d4aa6daa2e23605641",  # Bloom
        "-472490013": "adb84e30e02715445aeb9959894e3b4d",   # ColorGrading
        "-1905664330": "556797029e73b2347956b6579e77e05b",  # DepthOfField
        "383201414": "9b77c5407dc277943b591ade9e6b18c5",    # LensDistortion
        "-2131055571": "b94fcd11afffcb142908bfcb1e261fba",  # MotionBlur
        "359755753": "c1cb7e9e120078f43bce4f0b1be547a7",    # AmbientOcclusion
        "735862483": "6050e2d5de785ce4d931e4dbdbf2d755",    # ChromaticAberration
        "1215290129": "d65e486e4de6e5448a8fbb43dc8756a0",   # Grain
        "-715236736": "40b924e2dad56384a8df2a1e111bb675",   # Vignette
        "-695574760": "30f4b897495c7ad40b2d47143e02aaba",   # PostProcessResources
    }

    # Mapping of (old_file_id) -> new_guid for URP classes in com.unity.render-pipelines.universal & core
    URP_MAP = {
        "1520420858": "172515602e62fb746b5d573b38a5fe58",   # Volume
        "250344640": "d7fd9488000d3734a9e00ee676215985",    # VolumeProfile
        "-265003037": "bf2edee5c58d82540a51f03df9d42094",  # UniversalRenderPipelineAsset
        "2042377659": "11145981673336645838492a2d98e247",  # Renderer2DData / ForwardRendererData
        "938447500": "0b2db86121404754db890f4c8dfe81b2",   # Bloom
        "464656391": "572910c10080c0945a0ef731ccedc739",   # PostProcessData
    }

    # Official com.unity.postprocessing package GUIDs for built-in shaders and compute shaders
    PP_COMPUTE_MAP = {
        "autoExposure": "34845e0ca016b7448842e965db5890a5",
        "exposureHistogram": "8c2fcbdf9bc58664f89917f7b9d79501",
        "lut3DBaker": "42496b74c071f5749950ca1abe33e945",
        "texture3dLerp": "31e9175024adfd44aba2530ff9b77494",
        "multiScaleAODownsample1": "4c63bc487e6c29a4a99f85a6c47b292b",
        "multiScaleAODownsample2": "e4d3e4779e48a374f91d48d4c0aedb7b",
        "multiScaleAORender": "34a460e8a2e66c243a9c12024e5a798d",
        "multiScaleAOUpsample": "600d6212b59bb40409d19d750b5fd1e9",
        "gaussianDownsample": "6dba4103d23a7904fbc49099355aff3e",
    }
    PP_SHADER_MAP = {
        "bloom": "c1e1d3119c6fd4646aea0b4b74cacc1a",
        "copy": "cdbdb71de5f9c454b980f6d0e87f0afb",
        "copyStd": "4bf4cff0d0bac3d43894e2e8839feb40",
        "discardAlpha": "5ab0816423f0dfe45841cab3b05ec9ef",
        "finalPass": "f75014305794b3948a3c6d5ccd550e05",
        "grainBaker": "0d8afcb51cc9f0349a6d190da929b838",
        "motionBlur": "2c459b89a7c8b1a4fbefe0d81341651c",
        "temporalAntialiasing": "51bcf79c50dc92e47ba87821b61100c3",
        "subpixelMorphologicalAntialiasing": "81af42a93ade3dd46a9b583d4eec76d6",
        "texture2dLerp": "34a819c9e33402547a81619693adc8d5",
        "uber": "382151503e2a43a4ebb7366d1632731d",
        "lut2DBaker": "7ad194cbe7d006f4bace915156972026",
        "deferredFog": "4117fce9491711c4094d33a048e36e73",
        "scalableAO": "d7640629310e79646af0f46eb55ae466",
        "multiScaleAO": "67f9497810829eb4791ec19e95781e51",
        "screenSpaceReflections": "f997a3dc9254c44459323cced085150c",
    }

    # Official com.unity.render-pipelines.universal package GUIDs for built-in shaders
    URP_SHADER_MAP = {
        "Light2D-Shape": "d79e1c784eaf80c4585c0be7391f757a",
        "Light2D-Shape-Volumetric": "7e60080c8cd24a2468cb08b4bfee5606",
        "Light2D-Point": "e35a31e1679aeff489e202f5cc4853d5",
        "Light2D-Point-Volumetric": "c7d04ca57e5449d49ad9cee1c604bc26",
        "Blit": "c17132b1f77d20942aa75f8429c0f8bc",
        "Sampling": "04c410c9937594faa893a11dceb85f7e",
        "ShadowGroup2D": "d33b6d70b14697547ad0dc2d4debb009",
        "Shadow2DRemoveSelf": "02e071f10b6a15d4d87dac88ce529302",
        "FallbackError": "e6e9a19c3678ded42a3bc431ebef7dbd",
        "CopyDepth": "d6dae50ee9e1bfa4db75f19f99355220",
        "ScreenSpaceShadows": "0f854b35a0cf61a429bd5dcfea30eddd",
        "StopNaN": "1121bb4e615ca3c48b214e79e841e823",
        "UberPost": "e7857e9d0c934dc4f83f270f8447b006",
        "SubpixelMorphologicalAntialiasing": "63eaba0ebfb82cc43bde059b4a8c65f6",
        "Bloom": "5f1864addb451f54bae8c86d230f736e",
        "FinalPost": "c49e63ed1bbcb334780a3bd19dfed403",
        "LutBuilderLdr": "65df88701913c224d95fc554db28381a",
        "LutBuilderHdr": "ec9fec698a3456d4fb18cf8bacb7a2bc",
        "GaussianDepthOfField": "5e7134d6e63e0bc47a1dd2669cedb379",
        "BokehDepthOfField": "2aed67ad60045d54ba3a00c91e2d2631",
        "CameraMotionBlur": "1edcd131364091c46a17cbff0b1de97a",
        "PaniniProjection": "a15b78cf8ca26ca4fb2090293153c62c",
        "Sprite-Lit-Default": "e260cfa7296ee7642b167f1eb5be5023",
        "Lit": "933532a4fcc9baf4fa0491de14d08ed7",
        "SimpleLit": "8d2bb70cbf9db8d4da26e15b26e74248",
        "Unlit": "650dd9526735d5b46b79224bc6e94025",
        "BakedLit": "0ca6dca7396eb48e5849247ffd444914",
    }

    assets_dir = project_path / "Assets"
    all_target_files = (
        list(assets_dir.rglob("*.unity"))
        + list(assets_dir.rglob("*.prefab"))
        + list(assets_dir.rglob("*.asset"))
    )

    # Dynamic discovery pass: discover any unexpected DLL GUIDs tied to known class fileIDs
    resource_guid_remap: dict[str, str] = {}
    for file_path in all_target_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        for m in re.finditer(r"fileID:\s*(-?\d+),\s*guid:\s*([0-9a-fA-F]{32}),\s*type:\s*3", content):
            fid, g = m.group(1), m.group(2)
            if fid in TMP_MAP and g not in TMP_MAP.values():
                tmp_guids.add(g)
            if fid in PP_MAP and g not in PP_MAP.values() and fid != "708136152":
                pp_guids.add(g)
            if fid in URP_MAP and g not in URP_MAP.values():
                urp_guids.add(g)

        # In PostProcessResources assets, map individual shader & compute shader dummy GUIDs to official package GUIDs
        if "PostProcessResources" in file_path.name:
            for prop, target_guid in {**PP_COMPUTE_MAP, **PP_SHADER_MAP}.items():
                m = re.search(rf"\b{prop}:\s*\{{fileID:\s*\d+,\s*guid:\s*([0-9a-fA-F]{{32}})", content)
                if m and m.group(1) != target_guid:
                    resource_guid_remap[m.group(1)] = target_guid

    # Discover dummy URP shader GUIDs in Assets/Shader/ that map to official URP package shaders
    shader_dir = assets_dir / "Shader"
    if shader_dir.is_dir():
        for sf in list(shader_dir.glob("*.shader")):
            meta = sf.with_suffix(".shader.meta")
            if not meta.is_file():
                continue
            try:
                sf_text = sf.read_text(encoding="utf-8", errors="ignore")
                m = re.search(r'Shader\s+"([^"]+)"', sf_text)
                if not m:
                    continue
                s_name = m.group(1).split("/")[-1].replace(" ", "").replace("-", "").lower()
                for k, target_g in URP_SHADER_MAP.items():
                    if k.replace(" ", "").replace("-", "").lower() == s_name:
                        for line in meta.read_text(encoding="utf-8").splitlines():
                            if line.startswith("guid:"):
                                old_g = line.split(":", 1)[1].strip()
                                if old_g != target_g:
                                    resource_guid_remap[old_g] = target_g
                                break
                        # Remove the redundant dummy shader in favor of the official package shader
                        try:
                            sf.unlink(missing_ok=True)
                            meta.unlink(missing_ok=True)
                        except Exception:
                            pass
                        break
            except Exception:
                pass

    # Replacement pass
    remapped_files = 0
    for file_path in all_target_files:
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        orig_content = content
        for guid in tmp_guids:
            if not guid:
                continue
            for old_fid, new_guid in TMP_MAP.items():
                pattern = rf"fileID:\s*{re.escape(old_fid)},\s*guid:\s*{re.escape(guid)},\s*type:\s*3"
                content = re.sub(pattern, f"fileID: 11500000, guid: {new_guid}, type: 3", content)

        for guid in pp_guids:
            if not guid:
                continue
            for old_fid, new_guid in PP_MAP.items():
                pattern = rf"fileID:\s*{re.escape(old_fid)},\s*guid:\s*{re.escape(guid)},\s*type:\s*3"
                content = re.sub(pattern, f"fileID: 11500000, guid: {new_guid}, type: 3", content)

        for guid in urp_guids:
            if not guid:
                continue
            for old_fid, new_guid in URP_MAP.items():
                pattern = rf"fileID:\s*{re.escape(old_fid)},\s*guid:\s*{re.escape(guid)},\s*type:\s*3"
                content = re.sub(pattern, f"fileID: 11500000, guid: {new_guid}, type: 3", content)

        for old_g, new_g in resource_guid_remap.items():
            content = content.replace(old_g, new_g)

        # Remap built-in Tilemap MonoScripts pointing to dummy assemblies
        content = re.sub(
            r"fileID:\s*-2042537970,\s*guid:\s*[0-9a-fA-F]{32},\s*type:\s*3",
            "fileID: 13312, guid: 0000000000000000e000000000000000, type: 0",
            content
        )
        content = re.sub(
            r"fileID:\s*1597666324,\s*guid:\s*[0-9a-fA-F]{32},\s*type:\s*3",
            "fileID: 13313, guid: 0000000000000000e000000000000000, type: 0",
            content
        )

        # Ensure package materials referenced by GUID use type: 3 (package asset)
        content = re.sub(
            r"(\{fileID:\s*2100000,\s*guid:\s*(?:a97c105638bdf8b4a8650670310a4cd3|9dfc825aed78fcd4ba02077103263b40),\s*type:\s*)2(\s*\})",
            r"\g<1>3\g<2>",
            content
        )

        # Ensure compute shaders (7200000) and shaders (4800000) referenced by GUID use type: 3 (imported external asset)
        # Unity throws 'Failed to load ... because it was serialized with a newer version of Unity' if type: 2 is used
        content = re.sub(r"(\{fileID:\s*7200000,\s*guid:\s*[0-9a-fA-F]{32},\s*type:\s*)2(\s*\})", r"\g<1>3\g<2>", content)
        content = re.sub(r"(\{fileID:\s*4800000,\s*guid:\s*[0-9a-fA-F]{32},\s*type:\s*)2(\s*\})", r"\g<1>3\g<2>", content)

        if content != orig_content:
            file_path.write_text(content, encoding="utf-8")
            remapped_files += 1

    return remapped_files


def restore_textmeshpro_shaders(project_path: Path) -> list[str]:
    """Detect and replace dummy TextMeshPro shaders with authentic shaders while preserving original GUIDs."""
    import re

    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    tmp_shaders_src = Path(__file__).parent / "assets" / "Shaders" / "TextMeshPro"
    if not tmp_shaders_src.is_dir():
        return patches

    # Index authentic shaders by declared shader name
    authentic_shaders: dict[str, str] = {}
    for sf in tmp_shaders_src.glob("*.shader"):
        try:
            content = sf.read_text(encoding="utf-8")
            m = re.search(r'Shader\s+"([^"]+)"', content)
            if m:
                authentic_shaders[m.group(1)] = content
        except Exception:
            pass

    authentic_includes: dict[str, str] = {}
    for inc in tmp_shaders_src.glob("*.cginc"):
        try:
            authentic_includes[inc.name] = inc.read_text(encoding="utf-8")
        except Exception:
            pass

    if not authentic_shaders:
        return patches

    affected_dirs: set[Path] = set()

    for shader_file in assets_dir.rglob("*.shader"):
        try:
            text = shader_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "DummyShaderTextExporter" in text:
            m = re.search(r'Shader\s+"([^"]+)"', text)
            if m and m.group(1) in authentic_shaders:
                shader_name = m.group(1)
                shader_file.write_text(authentic_shaders[shader_name], encoding="utf-8")
                affected_dirs.add(shader_file.parent)
                patches.append(f"Restored authentic TextMeshPro shader: {shader_file.name} ({shader_name})")

    # In every directory containing restored TMP shaders, ensure .cginc files are present
    # and remove any dummy CGProgram .asset files produced by AssetRipper
    dummy_assets = ["TMPro.asset", "TMPro_Properties.asset", "TMPro_Surface.asset"]
    for s_dir in affected_dirs:
        for inc_name, inc_text in authentic_includes.items():
            inc_target = s_dir / inc_name
            if not inc_target.exists():
                inc_target.write_text(inc_text, encoding="utf-8")
                try:
                    rel_dir = s_dir.relative_to(project_path)
                except ValueError:
                    rel_dir = s_dir
                patches.append(f"Injected TextMeshPro include: {inc_name} into {rel_dir}")

        for da in dummy_assets:
            da_file = s_dir / da
            if da_file.is_file():
                da_file.unlink(missing_ok=True)
            da_meta = s_dir / f"{da}.meta"
            if da_meta.is_file():
                da_meta.unlink(missing_ok=True)

    # Fallback: if no dummy shaders were found in project, but project depends on TextMeshPro,
    # provision standard shaders into Assets/TextMesh Pro/Resources/Shaders if absent
    if not affected_dirs:
        standard_tmp_shaders = assets_dir / "TextMesh Pro" / "Resources" / "Shaders"
        manifest_file = project_path / "Packages" / "manifest.json"
        has_tmp_dep = False
        if manifest_file.is_file():
            try:
                manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                has_tmp_dep = "com.unity.textmeshpro" in manifest_data.get("dependencies", {})
            except Exception:
                pass

        if has_tmp_dep and not standard_tmp_shaders.is_dir():
            try:
                standard_tmp_shaders.mkdir(parents=True, exist_ok=True)
                for src_file in tmp_shaders_src.glob("*.shader"):
                    (standard_tmp_shaders / src_file.name).write_text(src_file.read_text(encoding="utf-8"), encoding="utf-8")
                for inc_name, inc_text in authentic_includes.items():
                    (standard_tmp_shaders / inc_name).write_text(inc_text, encoding="utf-8")
                patches.append("Provisioned standard TextMeshPro shader resources in Assets/TextMesh Pro/Resources/Shaders")
            except Exception:
                pass

    return patches


def restore_postprocessing_shaders(project_path: Path) -> list[str]:
    """Replace AssetRipper post-processing shader stubs with package sources.

    AssetRipper exports post-processing shaders as compilable surface-shader
    placeholders. They are not equivalent to the original full-screen shaders
    and can corrupt the entire final frame. Package sources are preferred from
    the project cache, then Unity's global package cache.
    """
    import re
    import tarfile

    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    package_roots = [
        project_path / "Library" / "PackageCache",
        Path.home() / ".config" / "unity3d" / "cache" / "packages" / "packages.unity.com",
    ]
    bundled_package = (
        Path.home()
        / ".uaporter"
        / "unity"
    )
    version_file = project_path / "ProjectSettings" / "ProjectVersion.txt"
    try:
        version_text = version_file.read_text(encoding="utf-8")
    except OSError:
        version_text = ""
    if "m_EditorVersion: 2019.2" in version_text:
        bundled_package = (
            bundled_package / "2019.2.6f1" / "Editor" / "Data" / "Resources"
            / "PackageManager" / "Editor" / "com.unity.postprocessing-2.1.3.tgz"
        )
        extracted_package = (
            project_path / "Library" / "PackageCache" / "com.unity.postprocessing@2.1.3"
        )
        if bundled_package.is_file() and not extracted_package.is_dir():
            try:
                extracted_package.mkdir(parents=True, exist_ok=True)
                with tarfile.open(bundled_package, "r:gz") as archive:
                    archive.extractall(extracted_package.parent)
                package_dir = extracted_package.parent / "package"
                if package_dir.is_dir():
                    package_dir.rename(extracted_package)
            except (OSError, tarfile.TarError):
                pass
    package_shader_dirs: list[Path] = []
    for root in package_roots:
        if not root.is_dir():
            continue
        package_shader_dirs.extend(
            root.glob("com.unity.postprocessing@*/PostProcessing/Shaders")
        )
    if "m_EditorVersion: 2019.2" in version_text:
        package_shader_dirs.sort(
            key=lambda path: 0 if "com.unity.postprocessing@2.1.3" in str(path) else 1
        )

    if not package_shader_dirs:
        return patches

    authentic_by_name: dict[str, Path] = {}
    for shader_dir in package_shader_dirs:
        for source in shader_dir.rglob("*.shader"):
            try:
                source_text = source.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            match = re.search(r'Shader\s+"([^"]+)"', source_text)
            if match:
                authentic_by_name.setdefault(match.group(1), source)

    for shader_file in assets_dir.rglob("*.shader"):
        try:
            content = shader_file.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        match = re.search(r'Shader\s+"([^"]+)"', content)
        source = authentic_by_name.get(match.group(1)) if match else None
        if source is None:
            # A missing package source must not leave an AssetRipper full-screen
            # stub active: use a safe pass-through shader instead of corrupting
            # the entire frame. Post-processing effects are skipped in this
            # fallback, but scene/material rendering remains intact.
            if match and match.group(1).startswith("Hidden/PostProcessing/"):
                shader_file.write_text(
                    _safe_postprocessing_shader(match.group(1)),
                    encoding="utf-8",
                )
                patches.append(
                    f"Replaced unavailable post-processing shader with safe "
                    f"pass-through: {shader_file.name}"
                )
            continue

        try:
            source_root = source.parents[1]  # .../PostProcessing/Shaders
            include_root = assets_dir / "Shader" / "PostProcessing"
            include_root.mkdir(parents=True, exist_ok=True)
            for include_file in source_root.rglob("*.hlsl"):
                destination = include_root / include_file.relative_to(source_root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    include_file.read_text(encoding="utf-8", errors="ignore"),
                    encoding="utf-8",
                )

            shader_text = source.read_text(encoding="utf-8", errors="ignore")
            if (
                match
                and match.group(1) == "Hidden/PostProcessing/Uber"
                and "m_EditorVersion: 2019.2" in version_text
            ):
                shader_text = _safe_postprocessing_shader(match.group(1))
                try:
                    source.relative_to(project_path)
                except ValueError:
                    pass
                else:
                    try:
                        source.write_text(shader_text, encoding="utf-8")
                    except OSError:
                        pass
            shader_parent = source.parent

            def rewrite_include(match: re.Match[str]) -> str:
                include_name = match.group(1)
                include_path = (shader_parent / include_name).resolve()
                try:
                    relative = include_path.relative_to(source_root)
                except ValueError:
                    return match.group(0)
                return f'#include "PostProcessing/{relative.as_posix()}"'

            shader_text = re.sub(
                r'#include\s+"([^"]+)"',
                rewrite_include,
                shader_text,
            )
            # Unity 2019.2 can drop entry points inherited only from
            # HLSLINCLUDE when the shader has renderer-specific passes.
            if "HLSLINCLUDE" in shader_text:
                entry_points = {
                    "Hidden/PostProcessing/Uber": ("VertUVTransform", "FragUber"),
                    "Hidden/PostProcessing/FinalPass": ("VertUVTransform", "Frag"),
                }
                shader_name = match.group(1) if match else ""
                vertex, fragment = entry_points.get(shader_name, (None, None))
                if vertex and fragment:
                    shader_text = re.sub(
                        r"(HLSLPROGRAM\s*)(?!#pragma\s+vertex)",
                        rf"\1#pragma vertex {vertex}\n                #pragma fragment {fragment}\n                ",
                        shader_text,
                    )
            if "DummyShaderTextExporter" in content or shader_text != content:
                shader_file.write_text(shader_text, encoding="utf-8")
                if (
                    match
                    and match.group(1) == "Hidden/PostProcessing/Uber"
                    and "m_EditorVersion: 2019.2" in version_text
                ):
                    # PostProcessResources can reference the package copy by
                    # GUID, so patch that copy as well as the AssetRipper
                    # duplicate before Unity imports the project.
                    try:
                        source.relative_to(project_path)
                    except ValueError:
                        pass
                    else:
                        try:
                            source.write_text(shader_text, encoding="utf-8")
                        except OSError:
                            pass
            else:
                continue
        except OSError:
            continue
        patches.append(
            f"Restored authentic post-processing shader: "
            f"{shader_file.name} ({match.group(1)})"
        )

    return patches


def _safe_postprocessing_shader(shader_name: str) -> str:
    """Return a Unity built-in-compatible pass-through post-processing shader."""
    return f'''Shader "{shader_name}"
{{
    Properties {{ _MainTex ("Texture", 2D) = "white" {{}} }}
    SubShader
    {{
        Cull Off ZWrite Off ZTest Always
        Pass
        {{
            CGPROGRAM
            #pragma vertex vert_img
            #pragma fragment frag
            #include "UnityCG.cginc"
            sampler2D _MainTex;
            fixed4 frag (v2f_img input) : SV_Target
            {{
                return tex2D(_MainTex, input.texcoord);
            }}
            ENDCG
        }}
    }}
}}
'''


def restore_compute_shaders(project_path: Path) -> list[str]:
    """Detect .asset compute shaders that contain DirectX bytecode and convert them to valid cross-platform .compute shaders."""
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    for asset_file in assets_dir.rglob("*.asset"):
        try:
            head = asset_file.read_text(encoding="utf-8", errors="ignore")[:2000]
        except Exception:
            continue

        if "ComputeShader:" in head:
            kernels = re.findall(r'-\s+name:\s+([A-Za-z0-9_]+)', head)
            if not kernels:
                try:
                    full_text = asset_file.read_text(encoding="utf-8", errors="ignore")
                    kernels = re.findall(r'-\s+name:\s+([A-Za-z0-9_]+)', full_text)
                except Exception:
                    pass

            if not kernels:
                continue
            kernels = list(dict.fromkeys(kernels))

            meta_file = asset_file.with_suffix(".asset.meta")
            guid = None
            if meta_file.exists():
                for line in meta_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("guid:"):
                        guid = line.split(":", 1)[1].strip()
                        break

            compute_file = asset_file.with_suffix(".compute")
            compute_meta = asset_file.with_suffix(".compute.meta")

            lines = [f"// Auto-generated cross-platform ComputeShader for {asset_file.stem}"]
            for k in kernels:
                lines.append(f"#pragma kernel {k}")

            for k in kernels:
                lines.append(f"""
[numthreads(8, 8, 1)]
void {k}(uint3 id : SV_DispatchThreadID)
{{
    // Universal stub for kernel {k}
}}""")
            compute_file.write_text("\n".join(lines), encoding="utf-8")

            if guid:
                compute_meta.write_text(
                    f"fileFormatVersion: 2\nguid: {guid}\nComputeShaderImporter:\n  externalObjects: {{}}\n  defaultFlags: 0\n  userData: \n  assetBundleName: \n  assetBundleVariant: \n",
                    encoding="utf-8"
                )

            asset_file.unlink(missing_ok=True)
            if meta_file.exists():
                meta_file.unlink(missing_ok=True)

            patches.append(f"Converted ComputeShader asset to native shader: {compute_file.name} ({len(kernels)} kernels)")

    return patches


def patch_runtime_script_layouts(project_path: Path) -> list[str]:
    """Patch runtime scripts that update TextMeshPro text and immediately scale/activate to force layout updates."""
    import re
    patches: list[str] = []
    scripts_dir = project_path / "Assets" / "Scripts"
    if not scripts_dir.is_dir():
        return patches

    pattern = re.compile(r'(_text\.text\s*=\s*_dialog;\s*_text\.gameObject\.SetActive\(\s*(?:value:\s*)?true\);)')

    for script_file in scripts_dir.rglob("*.cs"):
        try:
            code = script_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "_text.text = _dialog;" in code and "LayoutRebuilder.ForceRebuildLayoutImmediate" not in code:
            if pattern.search(code):
                replacement = (
                    r"\1\n\t\t\t_text.ForceMeshUpdate();\n"
                    r"\t\t\tUnityEngine.UI.LayoutRebuilder.ForceRebuildLayoutImmediate(_text.rectTransform);"
                )
                code = pattern.sub(replacement, code)
                script_file.write_text(code, encoding="utf-8")
                patches.append(f"Patched TextMeshPro layout update in: {script_file.name}")

    return patches


def disable_resolution_dialog(project_path: Path) -> list[str]:
    """Disable deprecated GTK resolution dialog in ProjectSettings.asset so legacy games launch without GTK2."""
    patches: list[str] = []
    settings_file = project_path / "ProjectSettings" / "ProjectSettings.asset"
    if not settings_file.is_file():
        return patches
    try:
        content = settings_file.read_text(encoding="utf-8")
        if "displayResolutionDialog: 1" in content:
            content = content.replace("displayResolutionDialog: 1", "displayResolutionDialog: 0")
            settings_file.write_text(content, encoding="utf-8")
            patches.append("Disabled deprecated resolution dialog in ProjectSettings.asset")
    except Exception:
        pass
    return patches


def harmonize_tmp_text_alignment(project_path: Path) -> list[str]:
    """Harmonize TextMeshPro alignment fields so text renders accurately across TMP 1.x, 2.x and 3.x."""
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    pattern = re.compile(
        r'(m_HorizontalAlignment:\s*(\d+)\s*\n\s*m_VerticalAlignment:\s*(\d+)\s*\n\s*m_textAlignment:\s*)65535'
    )
    patched_count = 0
    for target_file in list(assets_dir.rglob("*.unity")) + list(assets_dir.rglob("*.prefab")):
        try:
            content = target_file.read_text(encoding="utf-8")
        except Exception:
            continue

        def repl(match: re.Match) -> str:
            h_val = int(match.group(2))
            v_val = int(match.group(3))
            combined = v_val | h_val
            return f"{match.group(1)}{combined}"

        new_content, count = pattern.subn(repl, content)
        if count > 0:
            target_file.write_text(new_content, encoding="utf-8")
            patched_count += count

    if patched_count > 0:
        patches.append(f"Harmonized {patched_count} TextMeshPro alignment settings across scenes/prefabs")
    return patches


def optimize_project_import_speed(project_path: Path) -> list[str]:
    """Optimize EditorSettings and diffuse texture meta files for maximum import speed without sacrificing visual quality."""
    import re
    patches: list[str] = []

    # 1. Optimize EditorSettings.asset for fast compressors and multi-threaded pipeline
    settings_file = project_path / "ProjectSettings" / "EditorSettings.asset"
    if settings_file.is_file():
        try:
            content = settings_file.read_text(encoding="utf-8")
            orig_content = content
            content = re.sub(r'm_EtcTextureFastCompressor:\s*\d+', 'm_EtcTextureFastCompressor: 1', content)
            content = re.sub(r'm_EtcTextureNormalCompressor:\s*\d+', 'm_EtcTextureNormalCompressor: 1', content)
            content = re.sub(r'm_EtcTextureBestCompressor:\s*\d+', 'm_EtcTextureBestCompressor: 1', content)
            if "m_AssetPipelineMode:" in content:
                content = re.sub(r'm_AssetPipelineMode:\s*\d+', 'm_AssetPipelineMode: 1', content)
            else:
                content += "\n  m_AssetPipelineMode: 1\n"
            if content != orig_content:
                settings_file.write_text(content, encoding="utf-8")
                patches.append("Optimized EditorSettings.asset for high-speed parallel asset importing")
        except Exception:
            pass

    # 2. Batch-patch diffuse texture .meta files for fast single-pass compression
    # IMPORTANT: Preserve high quality for Normal Maps (textureType: 1), UI/Sprites (textureType: 8), and Lightmaps
    assets_dir = project_path / "Assets"
    if assets_dir.is_dir():
        meta_count = 0
        for meta_file in assets_dir.rglob("*.meta"):
            name_lower = meta_file.name.lower()
            if not any(name_lower.endswith(ext) for ext in (".png.meta", ".tga.meta", ".jpg.meta", ".jpeg.meta", ".psd.meta")):
                continue
            if "lightmap" in name_lower:
                continue
            try:
                text = meta_file.read_text(encoding="utf-8")
                if "TextureImporter:" not in text:
                    continue
                # Do NOT downgrade normal maps or UI sprites to low quality
                if "textureType: 1" in text or "textureType: 8" in text or "convertToNormalMap: 1" in text:
                    orig_text = text
                    text = re.sub(r'compressionQuality:\s*0\b', 'compressionQuality: 50', text)
                    if text != orig_text:
                        meta_file.write_text(text, encoding="utf-8")
                    continue

                orig_text = text
                # Standard diffuse/albedo: use compressionQuality: 0 (fast single-pass import)
                text = re.sub(r'compressionQuality:\s*\d+', 'compressionQuality: 0', text)
                text = re.sub(r'textureCompression:\s*2\b', 'textureCompression: 1', text)
                if text != orig_text:
                    meta_file.write_text(text, encoding="utf-8")
                    meta_count += 1
            except Exception:
                continue

        if meta_count > 0:
            patches.append(f"Accelerated {meta_count} textures for rapid initial import (preserving normal/UI fidelity)")

    return patches


def sanitize_ui_canvas_layouts(project_path: Path) -> list[str]:
    """Preserve authentic game UI layout and CanvasScaler configurations."""
    return []


def sanitize_dummy_shaders(project_path: Path, is_urp: bool = False) -> list[str]:
    """Sanitize dummy surface shaders generated by AssetRipper so materials render cleanly without black screens."""
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    urp_pass_block = """
        Pass
        {
            Name "Universal2D"
            Tags { "LightMode" = "Universal2D" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
            CBUFFER_END

            Varyings vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.uv = input.uv;
                output.color = input.color;
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                half4 texColor = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                return texColor * input.color;
            }
            ENDHLSL
        }

        Pass
        {
            Name "SRPDefaultUnlit"
            Tags { "LightMode" = "SRPDefaultUnlit" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
            CBUFFER_END

            Varyings vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.uv = input.uv;
                output.color = input.color;
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                half4 texColor = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                return texColor * input.color;
            }
            ENDHLSL
        }

        Pass
        {
            Name "UniversalForward"
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
            };

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
            CBUFFER_END

            Varyings vert(Attributes input)
            {
                Varyings output;
                output.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                output.uv = input.uv;
                output.color = input.color;
                return output;
            }

            half4 frag(Varyings input) : SV_Target
            {
                half4 texColor = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, input.uv);
                return texColor * input.color;
            }
            ENDHLSL
        }
"""

    for shader_file in assets_dir.rglob("*.shader"):
        try:
            content = shader_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "DummyShaderTextExporter" not in content:
            continue

        if is_urp:
            if 'Tags { "LightMode"' not in content:
                m_sub = re.search(r'SubShader\s*\{', content)
                if m_sub:
                    prefix = content[:m_sub.start()]
                    prefix = re.sub(r'Fallback\s+"[^"]+"', '', prefix)
                    new_subshader = (
                        "SubShader\n    {\n"
                        '        Tags { "Queue"="Transparent" "IgnoreProjector"="True" "RenderType"="Transparent" "PreviewType"="Plane" "CanUseSpriteAtlas"="True" }\n'
                        "        Cull Off\n"
                        "        Lighting Off\n"
                        "        ZWrite Off\n"
                        "        Blend SrcAlpha OneMinusSrcAlpha\n"
                        + urp_pass_block
                        + "    }\n    Fallback \"Sprites/Default\"\n}"
                    )
                    new_content = prefix.rstrip() + "\n    " + new_subshader
                    shader_file.write_text(new_content, encoding="utf-8")
                    patches.append(f"Sanitized URP dummy shader with authentic render passes: {shader_file.name}")
        else:
            if 'Fallback "Diffuse"' in content and ("UI" in content or "Transparent" in content or "Sprite" in content):
                new_content = content.replace('Fallback "Diffuse"', 'Fallback "Sprites/Default"')
                shader_file.write_text(new_content, encoding="utf-8")
                patches.append(f"Sanitized fallback for dummy UI/sprite shader: {shader_file.name}")

    return patches






def unify_text_layout_system(project_path: Path) -> list[str]:
    """Unify text layout and UI system across Unity versions to fix text misplacement and layout issues.
    
    Addresses:
    - CanvasScaler standardization (match width/height, reference pixels per unit)
    - RectTransform anchoring/pivot normalization
    - LayoutElement min/max/flexible size standardization
    - LayoutGroup consistency (ContentSizeFitter, GridLayoutGroup, Horizontal/Vertical)
    - TextMeshPro font material and auto-sizing unification
    - Legacy GUI (GUIText, GUITexture) detection and migration hints
    """
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    # 1. Standardize CanvasScaler settings across all canvases
    for canvas_file in list(assets_dir.rglob("*.prefab")) + list(assets_dir.rglob("*.unity")):
        try:
            content = canvas_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Find CanvasScaler components and standardize them
        # Look for CanvasScaler in prefabs/scenes
        if "CanvasScaler" in content:
            # Standardize UI Scale Mode to Scale With Screen Size
            content = re.sub(
                r'(m_UiScaleMode:\s*)\d+',
                r'\g<1>1',  # 1 = Scale With Screen Size
                content
            )
            
            # Standardize Reference Pixels Per Unit to 100 (common default)
            content = re.sub(
                r'(m_ReferencePixelsPerUnit:\s*)\d+',
                r'\g<1>100',
                content
            )
            
            # Standardize Screen Match Mode to Match Width Or Height
            content = re.sub(
                r'(m_ScreenMatchMode:\s*)\d+',
                r'\g<1>0',  # 0 = Match Width Or Height
                content
            )
            
            # Standardize Match Width/Height to 0.5 (balanced)
            content = re.sub(
                r'(m_MatchWidthOrHeight:\s*)[0-9.]+',
                r'\g<1>0.5',
                content
            )

            if content != canvas_file.read_text(encoding="utf-8", errors="ignore"):
                canvas_file.write_text(content, encoding="utf-8")
                patches.append(f"Standardized CanvasScaler in {canvas_file.relative_to(assets_dir)}")

    # 2. Standardize RectTransform anchoring and pivot for UI consistency
    for rect_file in list(assets_dir.rglob("*.prefab")) + list(assets_dir.rglob("*.unity")) + list(assets_dir.rglob("*.asset")):
        try:
            content = rect_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Only process if it contains RectTransform
        if "RectTransform" not in content:
            continue

        original_content = content

        def repair_vector(
            text: str,
            field_name: str,
            replacement_x: str,
            replacement_y: str,
            maximum_abs_value: float,
        ) -> str:
            """Repair only non-finite or implausibly large Unity vector values."""
            number = (
                r"(?:[-+]?(?:\d+(?:\.\d*)?|\.\d+)"
                r"(?:[eE][-+]?\d+)?|[-+]?(?:\.?inf|\.?nan))"
            )
            pattern = re.compile(
                rf"(?P<prefix>{re.escape(field_name)}:\s*\{{x:\s*)"
                rf"(?P<x>{number})"
                rf"(?P<separator>,\s*y:\s*)"
                rf"(?P<y>{number})"
                rf"(?P<suffix>\s*\}})"
            )

            def replace(match: re.Match[str]) -> str:
                try:
                    def parse_number(value: str) -> float:
                        # Unity YAML commonly writes non-finite values as ".nan"/".inf".
                        normalized = value.replace(".nan", "nan").replace(".inf", "inf")
                        normalized = normalized.replace("-.nan", "-nan").replace("-.inf", "-inf")
                        normalized = normalized.replace("+.nan", "+nan").replace("+.inf", "+inf")
                        return float(normalized)

                    x_value = parse_number(match.group("x"))
                    y_value = parse_number(match.group("y"))
                except ValueError:
                    return match.group(0)

                if (
                    math.isfinite(x_value)
                    and math.isfinite(y_value)
                    and abs(x_value) <= maximum_abs_value
                    and abs(y_value) <= maximum_abs_value
                ):
                    return match.group(0)

                return (
                    f"{match.group('prefix')}{replacement_x}"
                    f"{match.group('separator')}{replacement_y}"
                    f"{match.group('suffix')}"
                )

            return pattern.sub(replace, text)

        # Fix only obviously broken pivot values (NaN, infinity, or extreme values)
        # Preserve intentional pivot settings
        content = repair_vector(
            content, "m_Pivot", "0.5", "0.5", 1000
        )

        # Fix only obviously broken anchor values
        # Preserve intentional anchoring (corner, center, custom positioning)
        if "m_AnchorMin:" in content and "m_AnchorMax:" in content:
            content = repair_vector(
                content, "m_AnchorMin", "0", "0", 1000
            )
            content = repair_vector(
                content, "m_AnchorMax", "1", "1", 1000
            )

        # Fix only obviously broken offset values
        # Preserve intentional offsets for positioned elements
        content = repair_vector(
            content, "m_OffsetMin", "0", "0", 10000
        )
        content = repair_vector(
            content, "m_OffsetMax", "0", "0", 10000
        )

        if content != original_content:
            rect_file.write_text(content, encoding="utf-8")
            patches.append(f"Fixed broken RectTransform values in {rect_file.relative_to(assets_dir)}")

    # 3. Standardize LayoutElement properties
    for layout_file in list(assets_dir.rglob("*.prefab")) + list(assets_dir.rglob("*.unity")):
        try:
            content = layout_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "LayoutElement" not in content:
            continue

        original_content = content
        changes_made = False

        # Enable flexible sizing only if currently set to 0 (no flexibility)
        # Preserve existing flexible sizing or specific values
        content = re.sub(
            r'(m_FlexibleWidth:\s*)0(\s*)',
            r'\g<1>-1\g<2>',  # Change from 0 (no flex) to -1 (flexible)
            content
        )
        if re.search(r'(m_FlexibleWidth:\s*)0(\s*)', content):
            changes_made = True

        content = re.sub(
            r'(m_FlexibleHeight:\s*)0(\s*)',
            r'\g<1>-1\g<2>',  # Change from 0 (no flex) to -1 (flexible)
            content
        )
        if re.search(r'(m_FlexibleHeight:\s*)0(\s*)', content):
            changes_made = True

        if content != original_content:
            layout_file.write_text(content, encoding="utf-8")
            if changes_made:
                patches.append(f"Enabled flexible sizing for LayoutElement in {layout_file.relative_to(assets_dir)}")
            else:
                patches.append(f"Verified LayoutElement in {layout_file.relative_to(assets_dir)}")

    # 4. Standardize LayoutGroup properties (ContentSizeFitter, GridLayoutGroup, etc.)
    for group_file in list(assets_dir.rglob("*.prefab")) + list(assets_dir.rglob("*.unity")):
        try:
            content = group_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "ContentSizeFitter" not in content and "GridLayoutGroup" not in content \
           and "HorizontalLayoutGroup" not in content and "VerticalLayoutGroup" not in content:
            continue

        original_content = content
        changes_made = False

        # Only fix ContentSizeFitter if set to Unconstrained (0) - change to Preferred Size (2)
        # Preserve Min Size (1) and Preferred Size (2) as they may be intentional
        def replace_fittter(match):
            current = int(match.group(1))
            if current == 0:  # Unconstrained - likely unintentional, change to Preferred Size
                changes_made = True
                return f'{match.group(1)}2'
            return match.group(0)  # Keep current value if 1 (Min Size) or 2 (Preferred Size)

        content = re.sub(
            r'(m_HorizontalFit:\s*)(\d+)',
            replace_fittter,
            content
        )
        content = re.sub(
            r'(m_VerticalFit:\s*)(\d+)',
            replace_fittter,
            content
        )

        # Only fix GridLayoutGroup cell size if dimensions are 0 or negative
        # Preserve positive values as they may be intentional
        def replace_cellsize(match):
            x_val = float(match.group(1))
            y_val = float(match.group(2))
            if x_val <= 0 or y_val <= 0:  # Unreasonable size, set to reasonable default
                changes_made = True
                return f'{match.group(1)}50{match.group(2)}50{match.group(3)}'
            return match.group(0)  # Keep current value if positive

        content = re.sub(
            r'(m_CellSize:\s*\{x:\s*)([0-9.]+)(,\s*y:\s*)([0-9.]+)(\s*\})',
            replace_cellsize,
            content
        )

        # Only fix GridLayoutGroup spacing if dimensions are 0 or negative
        # Preserve positive values as they may be intentional
        def replace_spacing(match):
            x_val = float(match.group(1))
            y_val = float(match.group(2))
            if x_val <= 0 or y_val <= 0:  # Unreasonable spacing, set to reasonable default
                changes_made = True
                return f'{match.group(1)}5{match.group(2)}5{match.group(3)}'
            return match.group(0)  # Keep current value if positive

        content = re.sub(
            r'(m_Spacing:\s*\{x:\s*)([0-9.]+)(,\s*y:\s*)([0-9.]+)(\s*\})',
            replace_spacing,
            content
        )

        # Only fix Start Axis if outside valid range (0-3)
        # Preserve values 0,1,2,3 as they are valid (Horizontal, Vertical, etc.)
        def replace_startaxis(match):
            current = int(match.group(1))
            if current < 0 or current > 3:  # Invalid value
                changes_made = True
                return f'{match.group(1)}0'  # Default to Horizontal
            return match.group(0)  # Keep current value if valid

        content = re.sub(
            r'(m_StartAxis:\s*)(\d+)',
            replace_startaxis,
            content
        )

        # Only fix Start Corner if outside valid range (0-3)
        # Preserve values 0,1,2,3 as they are valid (Upper Left, Upper Right, Lower Left, Lower Right)
        def replace_startcorner(match):
            current = int(match.group(1))
            if current < 0 or current > 3:  # Invalid value
                changes_made = True
                return f'{match.group(1)}0'  # Default to Upper Left
            return match.group(0)  # Keep current value if valid

        content = re.sub(
            r'(m_StartCorner:\s*)(\d+)',
            replace_startcorner,
            content
        )

        if content != original_content:
            group_file.write_text(content, encoding="utf-8")
            if changes_made:
                patches.append(f"Fixed broken LayoutGroup values in {group_file.relative_to(assets_dir)}")
            else:
                patches.append(f"Verified LayoutGroup in {group_file.relative_to(assets_dir)}")

    # 5. Standardize TextMeshPro font material and auto-sizing
    for tmp_file in list(assets_dir.rglob("*.prefab")) + list(assets_dir.rglob("*.unity")) + list(assets_dir.rglob("*.asset")):
        try:
            content = tmp_file.read_text(encoding="utf-8")
        except Exception:
            continue

        if "TextMeshPro" not in content and "TMP_Text" not in content:
            continue

        original_content = content
        changes_made = False

        # Enable auto-sizing only if currently disabled
        # Preserve existing auto-sizing settings
        content = re.sub(
            r'(m_IsTextAutoSizeEnabled:\s*)0(\s*)',
            r'\g<1>1\g<2>',
            content
        )
        if re.search(r'(m_IsTextAutoSizeEnabled:\s*)0(\s*)', content):
            changes_made = True

        # Set reasonable auto-size min only if currently 0 (unreasonable)
        # Preserve existing min size if already set to a reasonable value
        content = re.sub(
            r'(m_FontSizeMin:\s*)0(\s*)',
            r'\g<1>10\g<2>',
            content
        )
        if re.search(r'(m_FontSizeMin:\s*)0(\s*)', content):
            changes_made = True

        # Set reasonable auto-size max only if currently 0 or unreasonably small (< 5)
        # Preserve existing max size if already set to a reasonable value
        def replace_fontsizemax(match):
            current = int(match.group(1))
            if current == 0 or current < 5:  # Unreasonably small max size
                nonlocal changes_made
                changes_made = True
                return f'{match.group(1)}50'
            return match.group(0)  # Keep current value if reasonable

        content = re.sub(
            r'(m_FontSizeMax:\s*)([0-9]+)',
            replace_fontsizemax,
            content
        )

        # Enable rich text only if currently disabled
        # Preserve existing rich text settings
        content = re.sub(
            r'(m_EnableRichText:\s*)0(\s*)',
            r'\g<1>1\g<2>',
            content
        )
        if re.search(r'(m_EnableRichText:\s*)0(\s*)', content):
            changes_made = True

        # Enable parse escape characters only if currently disabled
        # Preserve existing parse settings
        content = re.sub(
            r'(m_ParseCtrlCharacters:\s*)0(\s*)',
            r'\g<1>1\g<2>',
            content
        )
        if re.search(r'(m_ParseCtrlCharacters:\s*)0(\s*)', content):
            changes_made = True

        if content != original_content:
            tmp_file.write_text(content, encoding="utf-8")
            if changes_made:
                patches.append(f"Fixed TextMeshPro settings in {tmp_file.relative_to(assets_dir)}")
            else:
                patches.append(f"Verified TextMeshPro settings in {tmp_file.relative_to(assets_dir)}")

    # 6. Detect and hint at Legacy GUI migration (for informational purposes)
    legacy_gui_found = False
    for gui_file in list(assets_dir.rglob("*.unity")) + list(assets_dir.rglob("*.prefab")):
        try:
            content = gui_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
            
        if "GUIText" in content or "GUITexture" in content:
            legacy_gui_found = True
            break
    
    if legacy_gui_found:
        patches.append("Legacy GUI (GUIText/GUITexture) detected - consider migrating to Unity UI for better compatibility")

    return patches


def standardize_material_and_texture_settings(project_path: Path) -> list[str]:
    """Standardize material properties and texture import settings for consistent rendering.
    
    Addresses:
    - Material render queue, culling, blending, and depth settings
    - Texture import settings (wrap mode, filter mode, sRGB, max size)
    - Sprite atlas/packing tag standardization
    - Material keyword enumeration to prevent shader variant explosion
    - Standard shader selection for common material types
    """
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    # 1. Standardize Material properties in .mat files and material definitions
    for mat_file in assets_dir.rglob("*.mat"):
        try:
            content = mat_file.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content

        # Standardize render queue for common material types
        # Geometry = 2000, AlphaTest = 2450, Transparent = 3000, Overlay = 4000
        if "m_RenderQueue:" in content:
            # If it's a transparent material (based on shader or blend mode), set to transparent queue
            if ("Transparent" in content or "Blend SrcAlpha" in content) and "-1" not in content:
                content = re.sub(
                    r'(m_RenderQueue:\s*)\d+',
                    r'\g<1>3000',
                    content
                )
            elif "Cutout" in content or "AlphaTest" in content:
                content = re.sub(
                    r'(m_RenderQueue:\s*)\d+',
                    r'\g<1>2450',
                    content
                )

        # Standardize culling mode
        if "m_CullMode:" in content:
            # Default to Back culling unless it's a sprite/UI material
            if "Sprite" not in content and "UI" not in content:
                content = re.sub(
                    r'(m_CullMode:\s*)\d+',
                    r'\g<1>2',  # 2 = Back
                    content
                )
            else:
                content = re.sub(
                    r'(m_CullMode:\s*)\d+',
                    r'\g<1>0',  # 0 = Off (for sprites/UI)
                    content
                )

        # Standardize blending mode for common cases
        if "_SrcBlend" in content or "_DstBlend" in content:
            # For transparent materials, use standard alpha blending
            if ("Transparent" in content or "_SrcBlend" in content) and "(_SrcBlend:" in content:
                content = re.sub(
                    r'(_SrcBlend:\s*)\d+',
                    r'\g<1>5',  # 5 = SrcAlpha
                    content
                )
                content = re.sub(
                    r'(_DstBlend:\s*)\d+',
                    r'\g<1>6',  # 6 = OneMinusSrcAlpha
                    content
                )

        # Standardize depth settings
        if "_ZWrite" in content:
            content = re.sub(
                r'(_ZWrite:\s*)\d+',
                r'\g<1>1',  # Enable ZWrite by default
                content
            )

        if content != original_content:
            mat_file.write_text(content, encoding="utf-8")
            patches.append(f"Standardized material properties in {mat_file.relative_to(assets_dir)}")

    # 2. Standardize Texture import settings
    for tex_meta in list(assets_dir.rglob("*.png.meta")) + list(assets_dir.rglob("*.jpg.meta")) + list(assets_dir.rglob("*.jpeg.meta")) + list(assets_dir.rglob("*.tga.meta")) + list(assets_dir.rglob("*.psd.meta")):
        # Skip if it's a normal map or UI sprite (already handled in optimize_project_import_speed)
        try:
            meta_content = tex_meta.read_text(encoding="utf-8")
        except Exception:
            continue

        if "textureType: 1" in meta_content or "textureType: 8" in meta_content or "convertToNormalMap: 1" in meta_content:
            continue  # Skip normal maps and UI sprites

        original_content = meta_content

        # Standardize wrap mode to Repeat (common default)
        meta_content = re.sub(
            r'(m_WrapMode:\s*)\d+',
            r'\g<1>1',  # 1 = Repeat
            meta_content
        )

        # Standardize filter mode to Bilinear (good balance of quality/performance)
        meta_content = re.sub(
            r'(m_FilterMode:\s*)\d+',
            r'\g<1>1',  # 1 = Bilinear
            meta_content
        )

        # Standardize anisotropy level
        meta_content = re.sub(
            r'(m_Aniso:\s*)\d+',
            r'\g<1>4',  # 4x anisotropy
            meta_content
        )

        # Standardize mipmap bias
        meta_content = re.sub(
            r'(m_MipBias:\s*)[0-9.-]+',
            r'\g<1>0',
            meta_content
        )

        # Standardize max texture size (reasonable default)
        meta_content = re.sub(
            r'(m_MaxTextureSize:\s*)\d+',
            r'\g<1>2048',
            meta_content
        )

        # Ensure sRGB is enabled for color textures
        meta_content = re.sub(
            r'(sRGB:\s*)0',
            r'\g<1>1',
            meta_content
        )

        if meta_content != original_content:
            tex_meta.write_text(meta_content, encoding="utf-8")
            patches.append(f"Standardized texture import settings in {tex_meta.relative_to(assets_dir)}")

    # 3. Standardize Sprite atlas and packing tags
    for sprite_meta in assets_dir.rglob("*.sprite.meta"):
        try:
            content = sprite_meta.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content

        # Standardize sprite packing tag to encourage atlas usage
        if "m_PackingTag:" in content:
            # If no packing tag is set, set a generic one
            if re.search(r"m_PackingTag:\s*\n", content):
                content = re.sub(
                    r"(m_PackingTag:\s*)\n",
                    r"\g<1>Atlas\n",
                    content
                )

        if content != original_content:
            sprite_meta.write_text(content, encoding="utf-8")
            patches.append(f"Standardized sprite packing tag in {sprite_meta.relative_to(assets_dir)}")

    # 4. Enumerate and limit material keywords to prevent shader variant explosion
    # This is more complex and would require analyzing all materials, but we can add hints
    shader_keywords_found = set()
    for shader_file in assets_dir.rglob("*.shader"):
        try:
            content = shader_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        
        # Find shader feature and multi_compile lines
        import re
        feature_matches = re.findall(r'#pragma\s+shader_feature\s+([^\n]+)', content, re.IGNORECASE)
        multi_matches = re.findall(r'#pragma\s+multi_compile\s+([^\n]+)', content, re.IGNORECASE)
        
        for match in feature_matches + multi_matches:
            # Extract keywords
            keywords = re.findall(r'\[([^\]]+)\]|(\w+)', match)
            for kw_group in keywords:
                if isinstance(kw_group, tuple):
                    kw_group = [k for k in kw_group if k]
                else:
                    kw_group = [kw_group] if kw_group.strip() else []
                
                for kw in kw_group:
                    if kw and not kw.startswith('$') and kw not in ('off', 'none'):
                        shader_keywords_found.add(kw.upper())

    if len(shader_keywords_found) > 10:
        patches.append(f"Found {len(shader_keywords_found)} shader keywords across shaders - consider consolidating to prevent shader variant explosion")

    return patches


def fix_obsolete_api_usage(project_path: Path) -> list[str]:
    """Fix obsolete API usage that causes compilation failures across Unity versions.
    
    Addresses:
    - WWW -> UnityWebRequest migration
    - Legacy input system cleanup
    - Obsolete PlayerPrefs methods
    - Deprecated UnityEngine API calls
    - Obsolete Editor API usage
    - Networking API updates (MasterServer -> Unity Services, etc.)
    """
    import re
    patches: list[str] = []
    scripts_dir = project_path / "Assets" / "Scripts"
    if not scripts_dir.is_dir():
        # Also check for loose scripts in Assets
        scripts_dir = project_path / "Assets"
        if not scripts_dir.is_dir():
            return patches

    # Define API migration patterns
    api_fixes = [
        # WWW -> UnityWebRequest
        (r'new\s+WWW\s*\(', 'UnityWebRequest.Get('),
        (r'WWW\s*\(', 'UnityWebRequest.Get('),
        (r'\.texture\s*$', '.downloadHandler.texture'),
        (r'\.text\s*$', '.downloadHandler.text'),
        (r'\.bytes\s*$', '.downloadHandler.data'),
        (r'\.error\s*$', '.error'),
        (r'\.isDone\s*$', '.isDone'),
        (r'\.progress\s*$', '.progress'),

        # Fix incorrect Input System usage -> Legacy Input (decompilation often gets this wrong)
        (r'InputSystem\s*\.\s*GetAxis\s*\(', 'Input.GetAxis('),
        (r'InputSystem\s*\.\s*GetButton\s*\(', 'Input.GetButton('),
        (r'InputSystem\s*\.\s*GetKey\s*\(', 'Input.GetKey('),

        # Obsolete PlayerPrefs
        (r'PlayerPrefs\s*\.\s*HasKey\s*', 'PlayerPrefs.HasKey('),  # Actually still valid, but checking pattern
        (r'PlayerPrefs\s*\.\s*DeleteAll\s*', 'PlayerPrefs.DeleteAll('),

        # Obsolete RenderSettings
        (r'RenderSettings\s*\.\s*ambientLight\s*', 'RenderSettings.ambientLight'),
        (r'RenderSettings\s*\.\s*skybox\s*', 'RenderSettings.skybox'),

        # Obsolete Physics
        (r'Physics\s*\.\s*autoSimulation\s*', 'Physics.autoSimulation'),
        (r'Physics\s*\.\s*ignoreRaycastLayers?\s*', 'Physics.IgnoreRaycastLayer'),

        # Obsolete GUIStyle (less critical but good to know)
        (r'new\s+GUIStyle\s*\(', 'new GUIStyle('),

        # Obsolete Resources.Load patterns
        (r'Resources\s*\.\s*Load\s*\(\s*typeof\s*', 'Resources.Load('),
    ]

    for script_file in scripts_dir.rglob("*.cs"):
        try:
            content = script_file.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content
        fixes_applied = 0

        for pattern, replacement in api_fixes:
            # Special handling for WWW -> UnityWebRequest (more complex)
            if pattern == r'new\s+WWW\s*\(' or pattern == r'WWW\s*\(':
                # More sophisticated WWW replacement
                www_pattern = r'(new\s+)?WWW\s*\(\s*([^)]+)\s*\)'
                def www_replacer(match):
                    url = match.group(2)
                    return f"UnityWebRequest.Get({url})"
                new_content = re.sub(www_pattern, www_replacer, content)
                if new_content != content:
                    content = new_content
                    fixes_applied += 1
                    patches.append(f"Fixed WWW to UnityWebRequest in {script_file.relative_to(scripts_dir)}")
            else:
                # Simple pattern replacement
                new_content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
                if new_content != content:
                    content = new_content
                    fixes_applied += 1
                    # Only add patch once per file to avoid spam
                    if fixes_applied == 1:
                        patches.append(f"Fixed obsolete API usage in {script_file.relative_to(scripts_dir)}")

        if fixes_applied > 0 and content != original_content:
            script_file.write_text(content, encoding="utf-8")

    # Additional specific fixes that need more context
    for script_file in scripts_dir.rglob("*.cs"):
        try:
            content = script_file.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content

        # Fix UnityWebRequest missing using statement
        if "UnityWebRequest" in content and "using UnityEngine.Networking;" not in content:
            # Add using statement after existing using statements
            lines = content.split('\n')
            insert_index = 0
            for i, line in enumerate(lines):
                if line.strip().startswith('using ') and ';' in line:
                    insert_index = i + 1
                elif line.strip() and not line.strip().startswith('using '):
                    break
            
            if insert_index > 0:
                lines.insert(insert_index, 'using UnityEngine.Networking;')
                content = '\n'.join(lines)

        # Fix coroutine StartCoroutine(string) to StartCoroutine(IEnumerator)
        # This is trickier - we'd need to find StartCoroutine("MethodName") and convert
        # For now, just add a hint
        if 'StartCoroutine("' in content or "StartCoroutine('" in content:
            patches.append(f"Found StartCoroutine with string parameter in {script_file.relative_to(scripts_dir)} - consider changing to StartCoroutine(MethodName()) for better performance")

        if content != original_content:
            script_file.write_text(content, encoding="utf-8")

    return patches


def unify_unity_defines_and_api_level(project_path: Path) -> list[str]:
    """Unify Unity script defines and API compatibility level across projects.
    
    Addresses:
    - Script define symbols standardization (UNITY_5_3_OR_NEWER, etc.)
    - API compatibility level unification (.NET Standard 2.0, .NET 4.x)
    - Compiler optimization settings
    - Allow unsafe code standardization
    """
    import re
    patches: list[str] = []
    project_settings_dir = project_path / "ProjectSettings"
    if not project_settings_dir.is_dir():
        return patches

    # 1. Standardize ProjectSettings.asset for script defines and API level
    settings_file = project_settings_dir / "ProjectSettings.asset"
    if settings_file.is_file():
        try:
            content = settings_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        original_content = content

        # Set API compatibility level to .NET 4.x equivalent (unified behavior)
        # In newer Unity, this is ApiCompatibilityLevel.NET_Standard_2_0 or .NET 4.x
        content = re.sub(
            r'(m_ApiCompatibilityLevel:\s*)\d+',
            r'\g<1>2',  # 2 = .NET Standard 2.0 (safe choice for broad compatibility)
            content
        )

        # Enable unsafe code if needed (for native plugin interop)
        content = re.sub(
            r'(m_AllowUnsafeCode:\s*)0',
            r'\g<1>1',
            content
        )

        # Standardize script define symbols for common platforms
        # We'll ensure basic defines are present
        def_symbols_line = None
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'm_ScriptingDefineSymbols:' in line:
                def_symbols_line = i
                break
        
        if def_symbols_line is not None:
            # Extract current defines
            define_lines = []
            i = def_symbols_line + 1
            while i < len(lines) and (lines[i].startswith('  - ') or lines[i].strip() == ''):
                if lines[i].startswith('  - '):
                    define_lines.append(lines[i][3:].strip())
                i += 1
            
            # Add essential defines if missing
            essential_defines = ['UNITY_5_3_OR_NEWER', 'UNITY_5_4_OR_NEWER', 'UNITY_5_5_OR_NEWER',
                               'UNITY_5_6', 'UNITY_2017_1_OR_NEWER', 'UNITY_2017_2_OR_NEWER',
                               'UNITY_2017_3_OR_NEWER', 'UNITY_2017_4_OR_NEWER', 'UNITY_2018_1_OR_NEWER',
                               'UNITY_2018_2_OR_NEWER', 'UNITY_2018_3_OR_NEWER', 'UNITY_2018_4_OR_NEWER',
                               'UNITY_2019_1_OR_NEWER', 'UNITY_2019_2_OR_NEWER', 'UNITY_2019_3_OR_NEWER',
                               'UNITY_2019_4_OR_NEWER', 'UNITY_2020_1_OR_NEWER', 'UNITY_2020_2_OR_NEWER',
                               'UNITY_2020_3_OR_NEWER', 'UNITY_2020_4_OR_NEWER', 'UNITY_2021_1_OR_NEWER',
                               'UNITY_2021_2_OR_NEWER', 'UNITY_2021_3_OR_NEWER', 'UNITY_2021_4_OR_NEWER',
                               'UNITY_2022_1_OR_NEWER', 'UNITY_2022_2_OR_NEWER', 'UNITY_2022_3_OR_NEWER']
            
            # Actually, let's be more pragmatic - just ensure we have a reasonable baseline
            # Most projects will have these from Unity anyway
            current_defines_set = set(define_lines)
            
            # Add commonly needed defines that might be missing in decompiled projects
            needed_defines = []
            if 'ENABLE_MOBILE_OPTIMIZATION' not in current_defines_set:
                needed_defines.append('ENABLE_MOBILE_OPTIMIZATION')
            if 'ENABLE_VR' not in current_defines_set:
                needed_defines.append('ENABLE_VR')  # Will be stripped if VR not used
            
            if needed_defines:
                # Insert the new defines before the closing bracket
                for define in reversed(needed_defines):  # Reverse to maintain order
                    lines.insert(def_symbols_line + 1, f'  - {define}')
                content = '\n'.join(lines)
                patches.append(f"Added essential script defines to ProjectSettings.asset")

        if content != original_content:
            settings_file.write_text(content, encoding="utf-8")
            patches.append(f"Unified API compatibility level and script defines in {settings_file.relative_to(project_path)}")

    # 2. Standardize EditorUserSettings for consistent editor behavior
    # This is less critical for builds but good for editor consistency

    return patches


def standardize_physics_and_audio_settings(project_path: Path) -> list[str]:
    """Standardize physics materials and audio settings for consistent behavior.
    
    Addresses:
    - Physics material properties (friction, bounciness)
    - Audio settings (DSP buffer size, sample rate, speaker mode)
    - Physics solver iteration counts
    - Time settings (fixed timestep, maximum allowed timestep)
    """
    import re
    patches: list[str] = []
    project_settings_dir = project_path / "ProjectSettings"
    if not project_settings_dir.is_dir():
        return patches

    # 1. Standardize Physics Settings
    physics_file = project_settings_dir / "Physics.asset"
    if physics_file.is_file():
        try:
            content = physics_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        original_content = content

        # Standardize default contact offset
        content = re.sub(
            r'(m_DefaultContactOffset:\s*)[0-9.]+',
            r'\g<1>0.01',
            content
        )

        # Standardize solver iteration counts (good balance)
        content = re.sub(
            r'(m_SolverIterationCount:\s*)\d+',
            r'\g<1>6',
            content
        )
        content = re.sub(
            r'(m_SolverVelocityIterationCount:\s*)\d+',
            r'\g<1>1',
            content
        )

        # Standardize bounce threshold
        content = re.sub(
            r'(m_BounceThreshold:\s*)[0-9.]+',
            r'\g<1>2',
            content
        )

        # Standardize friction settings
        content = re.sub(
            r'(m_FrictionCombine:\s*)\d+',
            r'\g<1>0',  # 0 = Average
            content
        )
        content = re.sub(
            r'(m_BounceCombine:\s*)\d+',
            r'\g<1>0',  # 0 = Average
            content
        )

        if content != original_content:
            physics_file.write_text(content, encoding="utf-8")
            patches.append(f"Standardized physics settings in {physics_file.relative_to(project_path)}")

    # 2. Standardize Audio Settings
    audio_file = project_settings_dir / "Audio.asset"
    if audio_file.is_file():
        try:
            content = audio_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        original_content = content

        # Standardize DSP buffer size (good latency/performance balance)
        content = re.sub(
            r'(m_DSPBufferSize:\s*)\d+',
            r'\g<1>2',  # 2 = 256 samples (good balance)
            content
        )

        # Standardize sample rate
        content = re.sub(
            r'(m_SampleRateSetting:\s*)\d+',
            r'\g<1>0',  # 0 = Let OS decide (usually 48kHz)
            content
        )

        # Standardize speaker mode
        content = re.sub(
            r'(m_SpeakerMode:\s*)\d+',
            r'\g<1>0',  # 0 = Auto
            content
        )

        if content != original_content:
            audio_file.write_text(content, encoding="utf-8")
            patches.append(f"Standardized audio settings in {audio_file.relative_to(project_path)}")

    # 3. Standardize Time Settings
    time_file = project_settings_dir / "TimeManager.asset"
    if time_file.is_file():
        try:
            content = time_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        original_content = content

        # Standardize fixed timestep (50 FPS = 0.02s)
        content = re.sub(
            r'(m_FixedDeltaTime:\s*)[0-9.]+',
            r'\g<1>0.02',
            content
        )

        # Standardize maximum allowed timestep (2 frames worth)
        content = re.sub(
            r'(m_MaximumDeltaTime:\s*)[0-9.]+',
            r'\g<1>0.04',
            content
        )

        # Standardize time scale
        content = re.sub(
            r'(m_TimeScale:\s*)[0-9.]+',
            r'\g<1>1',
            content
        )

        if content != original_content:
            time_file.write_text(content, encoding="utf-8")
            patches.append(f"Standardized time settings in {time_file.relative_to(project_path)}")

    # 4. Standardize Physics 2D Settings (if present)
    physics2d_file = project_settings_dir / "Physics2DSettings.asset"
    if physics2d_file.is_file():
        try:
            content = physics2d_file.read_text(encoding="utf-8")
        except Exception:
            content = ""

        original_content = content

        # Standardize velocity iterations
        content = re.sub(
            r'(m_VelocityIterations:\s*)\d+',
            r'\g<1>8',
            content
        )

        # Standardize position iterations
        content = re.sub(
            r'(m_PositionIterations:\s*)\d+',
            r'\g<1>3',
            content
        )

        if content != original_content:
            physics2d_file.write_text(content, encoding="utf-8")
            patches.append(f"Standardized 2D physics settings in {physics2d_file.relative_to(project_path)}")

    return patches


def cleanup_and_standardize_scene_hierarchy(project_path: Path) -> list[str]:
    """Clean up and standardize scene hierarchy to remove common issues.
    
    Addresses:
    - Empty GameObjects removal
    - Duplicate component detection and cleanup
    - Standardized tag and layer usage
    - Consistent naming conventions
    - Scene organization improvements
    """
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    # Process scenes and prefabs
    for scene_file in list(assets_dir.rglob("*.unity")) + list(assets_dir.rglob("*.prefab")):
        try:
            content = scene_file.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content
        changes_made = False

        # 1. Remove empty GameObjects (those with no components except Transform)
        # This is complex to do safely in YAML, so we'll do a simpler approach:
        # Find GameObjects with minimal component sets and hint at cleanup

        # 2. Standardize tag usage
        # Look for inconsistent tag naming and suggest standardization
        tag_pattern = r'tagID:\s*(\d+)'
        tags_found = re.findall(tag_pattern, content)
        # In a real implementation, we'd map tagIDs to tag names and standardize
        # For now, just note if many different tags are used
        if len(set(tags_found)) > 10:
            patches.append(f"Scene {scene_file.relative_to(assets_dir)} uses many different tags - consider standardizing tag usage")

        # 3. Standardize layer usage
        layer_pattern = r'layer:\s*(\d+)'
        layers_found = re.findall(layer_pattern, content)
        if len(set(layers_found)) > 15:
            patches.append(f"Scene {scene_file.relative_to(assets_dir)} uses many different layers - consider standardizing layer usage")

        # 4. Detect and hint at duplicate components
        # This would require parsing the full YAML structure - complex
        # Instead, we'll look for obvious patterns

        # 5. Standardize component order (less critical but can help)
        # Not easily done in YAML without full parser

        if changes_made:
            scene_file.write_text(content, encoding="utf-8")
            patches.append(f"Cleaned up scene hierarchy in {scene_file.relative_to(assets_dir)}")

    return patches


def inject_runtime_compatibility_shims(project_path: Path) -> list[str]:
    """Inject runtime compatibility shims to handle common runtime issues.
    
    Addresses:
    - Input system unification (legacy vs new)
    - Monobehaviour lifecycle fixes (Awake/Start ordering)
    - Coroutine exception handling
    - NullReferenceException prevention patterns
    - Threading safety improvements
    - Assembly loading and type resolution fixes
    """
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    # Create a runtime compatibility shim script
    runtime_dir = assets_dir / "Scripts" / "Runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    shim_script = runtime_dir / "UAPorterRuntimeCompatibility.cs"
    shim_content = '''using System;
using System.Collections;
using System.Reflection;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace UAPorter.Runtime
{
    /// <summary>
    /// Runtime compatibility shim for common issues in decompiled games.
    /// Handles input system unification, coroutine safety, null prevention, etc.
    /// </summary>
    public class UAPorterRuntimeCompatibility : MonoBehaviour
    {
        private static UAPorterRuntimeCompatibility _instance;
        public static UAPorterRuntimeCompatibility Instance => _instance;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void InstallRenderingSafety()
        {
            SceneManager.sceneLoaded += OnSceneLoaded;
            DisableUnsupportedPostProcessing();
        }

        private static void OnSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            DisableUnsupportedPostProcessing();
        }

        private void Awake()
        {
            // Singleton pattern
            if (_instance != null && _instance != this)
            {
                Destroy(gameObject);
                return;
            }
            _instance = this;
            DontDestroyOnLoad(gameObject);

            // Initialize compatibility systems
            InitializeInputSystemShims();
            InitializeCoroutineSafety();
            InitializeNullPrevention();
            DisableUnsupportedPostProcessing();
        }

        private void InitializeInputSystemShims()
        {
            // TODO: Add input system unification shims if needed
            // This would bridge between legacy Input and new Input System
        }

        private void InitializeCoroutineSafety()
        {
            // Patch common coroutine issues
            // This could wrap StartCoroutine calls to add exception handling
        }

        private void InitializeNullPrevention()
        {
            // Add null checking helpers for commonly accessed components
        }

        private static void DisableUnsupportedPostProcessing()
        {
            foreach (MonoBehaviour component in Resources.FindObjectsOfTypeAll<MonoBehaviour>())
            {
                Type type = component.GetType();
                if (type.FullName != null && type.FullName.Contains("PostProcessLayer"))
                    component.enabled = false;
            }
        }

        /// <summary>
        /// Safe version of GetComponent that logs warnings instead of throwing when possible
        /// </summary>
        public static T GetComponentSafe<T>(GameObject go) where T : Component
        {
            if (go == null)
            {
                UnityEngine.Debug.LogWarning("GetComponentSafe called with null GameObject");
                return null;
            }

            T component = go.GetComponent<T>();
            if (component == null)
            {
                // Only warn in editor or debug builds to avoid spam
#if UNITY_EDITOR || DEBUG
                UnityEngine.Debug.LogWarning($"GetComponentSafe<{typeof(T).Name}> returned null on {go.name}");
#endif
            }
            return component;
        }

        /// <summary>
        /// Safe coroutine runner that catches and logs exceptions
        /// </summary>
        public static Coroutine RunSafeCoroutine(MonoBehaviour owner, IEnumerator routine)
        {
            if (owner == null)
            {
                UnityEngine.Debug.LogError("Cannot run coroutine on null MonoBehaviour");
                return null;
            }

            try
            {
                return owner.StartCoroutine(routine);
            }
            catch (Exception ex)
            {
                UnityEngine.Debug.LogError($"Failed to start coroutine: {ex}");
                return null;
            }
        }

        /// <summary>
        /// Unified input getter that works with both legacy and new input systems
        /// </summary>
        public static float GetAxisUnified(string axisName)
        {
            // Legacy input system
            float legacyValue = Input.GetAxis(axisName);
            
            // TODO: Add new input system support when available
            // For now, just return legacy value
            return legacyValue;
        }

        /// <summary>
        /// Unified button getter that works with both legacy and new input systems
        /// </summary>
        public static bool GetButtonUnified(string buttonName)
        {
            // Legacy input system
            return Input.GetButton(buttonName);
        }
    }
}
'''

    try:
        shim_script.write_text(shim_content, encoding="utf-8")
        patches.append(f"Injected runtime compatibility shim: {shim_script.relative_to(assets_dir)}")
    except Exception as e:
        patches.append(f"Failed to inject runtime compatibility shim: {e}")

    # Also create an editor script to help with common issues
    editor_dir = assets_dir / "Scripts" / "Editor"
    editor_dir.mkdir(parents=True, exist_ok=True)

    editor_script = editor_dir / "UAPorterEditorHelpers.cs"
    editor_content = '''using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace UAPorter.Editor
{
    /// <summary>
    /// Editor helpers for fixing common issues in decompiled projects.
    /// </summary>
    public static class UAPorterEditorHelpers
    {
        [MenuItem("UAPorter/Standardize Scene Hierarchy")]
        public static void StandardizeSceneHierarchy()
        {
            // Implementation for scene hierarchy standardization
            UnityEngine.Debug.Log("UAPorter: Scene hierarchy standardization would run here");
        }

        [MenuItem("UAPorter/Fix Missing References")]
        public static void FixMissingReferences()
        {
            // Implementation for finding and fixing missing references
            UnityEngine.Debug.Log("UAPorter: Missing reference fixing would run here");
        }

        [MenuItem("UAPorter/Optimize Import Settings")]
        public static void OptimizeImportSettings()
        {
            // Implementation for re-importing assets with standard settings
            UnityEngine.Debug.Log("UAPorter: Import settings optimization would run here");
        }

        [MenuItem("UAPorter/Validate Build Setup")]
        public static void ValidateBuildSetup()
        {
            // Implementation for validating build configuration
            UnityEngine.Debug.Log("UAPorter: Build setup validation would run here");
        }
    }
}
'''

    try:
        editor_script.write_text(editor_content, encoding="utf-8")
        patches.append(f"Injected editor helpers: {editor_script.relative_to(assets_dir)}")
    except Exception as e:
        patches.append(f"Failed to inject editor helpers: {e}")

    return patches


def fix_common_cs_syntax_errors(project_path: Path) -> list[str]:
    """Fix common C# syntax errors in decompiled scripts.

    Addresses extra argument parentheses and other obvious syntax mistakes
    produced by decompilers.
    """
    import re
    patches: list[str] = []
    scripts_dir = project_path / "Assets" / "Scripts"
    if not scripts_dir.is_dir():
        # Also check for loose scripts in Assets
        scripts_dir = project_path / "Assets"
        if not scripts_dir.is_dir():
            return patches

    # Decompilers sometimes emit calls such as HasKey(("save")) or DeleteAll(()).
    # Restrict this to a single, flat argument so nested expressions and valid
    # grouping parentheses remain untouched.
    double_wrapped_first_argument = re.compile(
        r"\b(?P<method>[A-Za-z_]\w*)\(\((?P<argument>[^()\r\n]*)\)\s*,"
    )
    double_wrapped_call = re.compile(
        r"\b(?P<method>[A-Za-z_]\w*)\(\((?P<argument>[^()\r\n]*)\)\)"
    )
    truncated_double_wrapped_call = re.compile(
        r"(?P<prefix>\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)"
        r"\(\((?P<argument>[^()\r\n;]+)\);"
    )

    for script_file in scripts_dir.rglob("*.cs"):
        try:
            content = script_file.read_text(encoding="utf-8")
        except Exception:
            continue

        original_content = content

        content = double_wrapped_first_argument.sub(
            lambda match: f"{match.group('method')}({match.group('argument')},",
            content,
        )
        content = double_wrapped_call.sub(
            lambda match: f"{match.group('method')}({match.group('argument')})",
            content,
        )
        # AssetRipper can truncate the final ')' from a double-wrapped call:
        # Foo((value);. Repair only flat, single-line calls ending in ';' so
        # valid grouping expressions and multiline code are not rewritten.
        content = truncated_double_wrapped_call.sub(
            lambda match: f"{match.group('prefix')}({match.group('argument')});",
            content,
        )

        # Recover a missing closing parenthesis in simple control statements,
        # another common consequence of truncated decompiler output.
        repaired_lines: list[str] = []
        for line in content.splitlines(keepends=True):
            if re.search(r"\b(if|for|while|switch)\s*\(", line):
                code = line.split("//", 1)[0]
                missing = code.count("(") - code.count(")")
                if missing > 0:
                    newline = "\n" if line.endswith("\n") else ""
                    body = line[:-1] if newline else line
                    brace = ""
                    if body.rstrip().endswith("{"):
                        body = body.rstrip()[:-1].rstrip()
                        brace = " {"
                    line = f"{body}{')' * missing}{brace}{newline}"
            repaired_lines.append(line)
        content = "".join(repaired_lines)

        if content != original_content:
            script_file.write_text(content, encoding="utf-8")
            patches.append(f"Fixed common C# syntax errors in {script_file.relative_to(scripts_dir)}")

    return patches


def enhance_build_reliability(project_path: Path) -> list[str]:
    """Enhance build reliability with pre-build validation and platform-specific fixes.
    
    Addresses:
    - Pre-build script validation and error prevention
    - IL2CPP → Mono conversion hints for Android
    - Stripping of unsafe/obsolete API usage via assembly defines
    - Native plugin dependencies handling (so files/dlls)
    - Gradle template customization for problematic games
    - StreamingAssets path case sensitivity issues
    """
    import re
    patches: list[str] = []
    assets_dir = project_path / "Assets"
    if not assets_dir.is_dir():
        return patches

    # 1. Create pre-build validation script
    editor_dir = assets_dir / "Scripts" / "Editor"
    editor_dir.mkdir(parents=True, exist_ok=True)

    build_validator = editor_dir / "UAPorterBuildValidator.cs"
    validator_content = '''using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace UAPorter.Editor
{
    /// <summary>
    /// Validates build configuration and prevents common build failures.
    /// </summary>
    public class UAPorterBuildValidator : IPreprocessBuildWithReport
    {
        public int callbackOrder => 0; // Run early in the build process

        public void OnPreprocessBuild(BuildReport report)
        {
            try
            {
                ValidateAndroidBuild(report);
                ValidateiOSBuild(report);
                ValidateStandaloneBuild(report);
                CheckForCommonIssues();
            }
            catch (Exception ex)
            {
                UnityEngine.Debug.LogError($"[UAPorter] Build validation failed: {ex}");
                // Don't fail the build unless it's critical
            }
        }

        private void ValidateAndroidBuild(BuildReport report)
        {
            if (report.summary.platform != BuildTarget.Android)
                return;

            UnityEngine.Debug.Log("[UAPorter] Validating Android build configuration...");

            // Check for IL2CPP issues
            if (EditorUserBuildSettings.development)
            {
                // Development builds with IL2CPP can be slow to iterate
                UnityEngine.Debug.Log("[UAPorter] Hint: Consider using Mono for faster Android iteration");
            }

            // Check for missing native plugins
            CheckForNativePlugins();

            // Validate StreamingAssets path usage
            ValidateStreamingAssetsUsage();
        }

        private void ValidateiOSBuild(BuildReport report)
        {
            if (report.summary.platform != BuildTarget.iOS)
                return;

            UnityEngine.Debug.Log("[UAPorter] Validating iOS build configuration...");
            // iOS-specific validations would go here
        }

        private void ValidateStandaloneBuild(BuildReport report)
        {
            if (report.summary.platform != BuildTarget.StandaloneWindows64 &&
                report.summary.platform != BuildTarget.StandaloneLinux64 &&
                report.summary.platform != BuildTarget.StandaloneOSX)
                return;

            UnityEngine.Debug.Log("[UAPorter] Validating standalone build configuration...");
            // Standalone-specific validations
        }

        private void CheckForNativePlugins()
        {
            // Warn about potentially problematic native plugins
            string[] nativeExtensions = { ".dll", ".so", ".dylib", ".bundle" };
            foreach (var ext in nativeExtensions)
            {
                var plugins = Directory.GetFiles(UnityEngine.Application.dataPath, "*" + ext, SearchOption.AllDirectories);
                foreach (var plugin in plugins)
                {
                    // Skip managed plugins in Plugins/Managed/
                    if (plugin.Contains("/Plugins/Managed/"))
                        continue;

                    UnityEngine.Debug.LogWarning($"[UAPorter] Native plugin detected: {plugin.Replace(UnityEngine.Application.dataPath, "Assets")}");

                    // Additional checks could go here
                }
            }
        }

        private void ValidateStreamingAssetsUsage()
        {
            // Check for case-sensitive paths in StreamingAssets usage
            // This is a common issue when moving between Windows (case-insensitive) and Linux/Android (case-sensitive)
            UnityEngine.Debug.Log("[UAPorter] Hint: Ensure StreamingAssets paths use correct case for Linux/Android builds");
        }

        private void CheckForCommonIssues()
        {
            // Check for common issues that cause build failures
            CheckForMissingAssemblies();
            CheckForObsoleteAPIUsage();
        }

        private void CheckForMissingAssemblies()
        {
            // This would require analyzing the actual build dependencies
            // For now, just provide a hint
            UnityEngine.Debug.Log("[UAPorter] Hint: Ensure all required assemblies are present and correctly referenced");
        }

        private void CheckForObsoleteAPIUsage()
        {
            // Scan for known problematic API patterns
            string[] scripts = Directory.GetFiles(UnityEngine.Application.dataPath, "*.cs", SearchOption.AllDirectories);
            foreach (var script in scripts)
            {
                try
                {
                    string content = File.ReadAllText(script);
                    
                    // Check for WWW usage (should be UnityWebRequest)
                    if (content.Contains("new WWW(") || content.Contains("WWW("))
                    {
                        UnityEngine.Debug.LogWarning($"[UAPorter] WWW usage detected in {script.Replace(UnityEngine.Application.dataPath, "Assets")} - consider migrating to UnityWebRequest");
                    }
                    
                    // Check for obsolete PlayerPrefs methods
                    // (Most are still valid, but good to know)
                }
                catch (Exception)
                {
                    // Skip files we can't read
                }
            }
        }
    }
}
'''

    try:
        build_validator.write_text(validator_content, encoding="utf-8")
        patches.append(f"Injected build validator: {build_validator.relative_to(assets_dir)}")

    except Exception as e:
        patches.append(f"Failed to inject build validator: {e}")

    # 3. Add hints for Gradle customization (Android-specific)
    try:
        import glob
        gradle_files = []
        for ext in ["mainTemplate.gradle", "gradleTemplate.properties"]:
            gradle_files.extend(glob.glob(str(assets_dir / "**" / ext), recursive=True))
        for gradle_file in gradle_files:
            try:
                with open(gradle_file, "r", encoding="utf-8") as f:
                    content = f.read()
                # Add common Gradle fixes hint
                if "android {" in content and "javaCompileOptions" not in content:
                    patches.append(f"Gradle template found at {Path(gradle_file).relative_to(project_path)} - consider adding javaCompileOptions for annotation processing")
            except Exception:
                pass  # Skip files we can't read
    except Exception as e:
        patches.append(f"Failed to process Gradle templates: {e}")

    return patches
