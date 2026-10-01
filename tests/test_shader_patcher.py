"""Tests for TextMeshPro shader restoration and dummy shader replacement."""

from pathlib import Path
import json
from uaporter.android.project_patcher import restore_textmeshpro_shaders, patch_decompiled_project


def test_restore_textmeshpro_dummy_shaders(tmp_path: Path):
    """Test that dummy TextMeshPro shaders are replaced with authentic ones and GUIDs are preserved."""
    proj = tmp_path / "TestProject"
    shaders_dir = proj / "Assets" / "Resources" / "shaders"
    shaders_dir.mkdir(parents=True)

    # 1. Create a dummy TextMeshPro Distance Field shader
    dummy_code = (
        'Shader "TextMeshPro/Distance Field" {\n'
        '  //DummyShaderTextExporter\n'
        '  SubShader {\n'
        '    Tags { "RenderType"="Opaque" }\n'
        '    CGPROGRAM\n'
        '    #pragma surface surf Standard\n'
        '    ENDCG\n'
        '  }\n'
        '}\n'
    )
    shader_file = shaders_dir / "TextMeshPro_Distance Field.shader"
    shader_file.write_text(dummy_code, encoding="utf-8")

    meta_file = shaders_dir / "TextMeshPro_Distance Field.shader.meta"
    original_guid = "520a9015d20eec441bc5788509f9898b"
    meta_file.write_text(f"fileFormatVersion: 2\nguid: {original_guid}\n", encoding="utf-8")

    # 2. Create a dummy Mobile Distance Field shader
    mobile_dummy_code = (
        'Shader "TextMeshPro/Mobile/Distance Field" {\n'
        '  //DummyShaderTextExporter\n'
        '  SubShader { Tags { "RenderType"="Opaque" } }\n'
        '}\n'
    )
    mobile_shader_file = shaders_dir / "TextMeshPro_Mobile_Distance Field.shader"
    mobile_shader_file.write_text(mobile_dummy_code, encoding="utf-8")

    mobile_meta_file = shaders_dir / "TextMeshPro_Mobile_Distance Field.shader.meta"
    mobile_guid = "1e70b8c5df1c1134786992f46b370ea2"
    mobile_meta_file.write_text(f"fileFormatVersion: 2\nguid: {mobile_guid}\n", encoding="utf-8")

    # 3. Create a non-dummy custom shader that should NOT be modified
    custom_shader = shaders_dir / "CustomUnlit.shader"
    custom_shader.write_text('Shader "Custom/Unlit" { SubShader {} }', encoding="utf-8")

    # 4. Create dummy CGProgram .asset and .asset.meta
    dummy_asset = shaders_dir / "TMPro.asset"
    dummy_asset.write_text("%YAML 1.1\nCGProgram:", encoding="utf-8")
    dummy_asset_meta = shaders_dir / "TMPro.asset.meta"
    dummy_asset_meta.write_text("guid: 12345\n", encoding="utf-8")

    # Run restoration
    patches = restore_textmeshpro_shaders(proj)

    assert len(patches) >= 2
    # Verify dummy code is gone and replaced with genuine SDF shader
    new_content = shader_file.read_text(encoding="utf-8")
    assert "//DummyShaderTextExporter" not in new_content
    assert "Blend One OneMinusSrcAlpha" in new_content
    assert "_FaceColor" in new_content

    # Verify GUID was strictly preserved
    assert f"guid: {original_guid}" in meta_file.read_text(encoding="utf-8")

    # Verify mobile shader was also restored
    new_mobile_content = mobile_shader_file.read_text(encoding="utf-8")
    assert "//DummyShaderTextExporter" not in new_mobile_content
    assert "Blend One OneMinusSrcAlpha" in new_mobile_content
    assert f"guid: {mobile_guid}" in mobile_meta_file.read_text(encoding="utf-8")

    # Verify custom shader was untouched
    assert custom_shader.read_text(encoding="utf-8") == 'Shader "Custom/Unlit" { SubShader {} }'

    # Verify includes were injected
    assert (shaders_dir / "TMPro.cginc").is_file()
    assert (shaders_dir / "TMPro_Properties.cginc").is_file()
    assert (shaders_dir / "TMPro_Surface.cginc").is_file()

    # Verify dummy .asset and .asset.meta were deleted
    assert not dummy_asset.exists()
    assert not dummy_asset_meta.exists()


def test_restore_standard_tmp_shaders_fallback(tmp_path: Path):
    """Test fallback provisioning when project has TMP dependency but no shaders in Assets."""
    proj = tmp_path / "FallbackProject"
    assets_dir = proj / "Assets"
    assets_dir.mkdir(parents=True)
    pkgs_dir = proj / "Packages"
    pkgs_dir.mkdir(parents=True)
    manifest = pkgs_dir / "manifest.json"
    manifest.write_text(json.dumps({"dependencies": {"com.unity.textmeshpro": "2.0.0"}}), encoding="utf-8")

    patches = restore_textmeshpro_shaders(proj)
    assert any("Provisioned standard TextMeshPro shader resources" in p for p in patches)

    dest = assets_dir / "TextMesh Pro" / "Resources" / "Shaders"
    assert (dest / "TMP_SDF.shader").is_file()
    assert (dest / "TMP_SDF-Mobile.shader").is_file()
    assert (dest / "TMPro.cginc").is_file()

def test_restore_postprocessing_dummy_shaders_from_package_cache(tmp_path: Path):
    from uaporter.android.project_patcher import restore_postprocessing_shaders

    project = tmp_path / "PostProcessingProject"
    shader_dir = project / "Assets" / "Shader"
    package_dir = (
        project / "Library" / "PackageCache" / "com.unity.postprocessing@2.1.7"
        / "PostProcessing" / "Shaders" / "Builtins"
    )
    shader_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)

    dummy = shader_dir / "Hidden_PostProcessing_Uber.shader"
    dummy.write_text(
        'Shader "Hidden/PostProcessing/Uber" {\n'
        '  //DummyShaderTextExporter\n'
        '  SubShader { }\n'
        '}\n',
        encoding="utf-8",
    )
    meta = dummy.with_suffix(".shader.meta")
    meta.write_text(
        "fileFormatVersion: 2\nguid: 1234567890abcdef1234567890abcdef\n",
        encoding="utf-8",
    )
    (package_dir / "Uber.shader").write_text(
        'Shader "Hidden/PostProcessing/Uber"\n{\n'
        "    HLSLINCLUDE\n"
        "    ENDHLSL\n"
        "}\n",
        encoding="utf-8",
    )
    (package_dir.parent / "StdLib.hlsl").write_text("// support include\n", encoding="utf-8")

    patches = restore_postprocessing_shaders(project)

    assert patches
    assert "DummyShaderTextExporter" not in dummy.read_text(encoding="utf-8")
    assert "HLSLINCLUDE" in dummy.read_text(encoding="utf-8")
    assert "1234567890abcdef1234567890abcdef" in meta.read_text(encoding="utf-8")
    assert (project / "Assets/Shader/PostProcessing/StdLib.hlsl").is_file()


def test_restore_postprocessing_uses_safe_fallback_without_package(tmp_path: Path):
    from uaporter.android.project_patcher import restore_postprocessing_shaders

    shader_dir = tmp_path / "Assets" / "Shader"
    shader_dir.mkdir(parents=True)
    shader = shader_dir / "Hidden_PostProcessing_Unavailable.shader"
    shader.write_text(
        'Shader "Hidden/PostProcessing/Unavailable" {\n'
        "  //DummyShaderTextExporter\n"
        "}\n",
        encoding="utf-8",
    )

    patches = restore_postprocessing_shaders(tmp_path)

    assert patches
    result = shader.read_text(encoding="utf-8")
    assert "DummyShaderTextExporter" not in result
    assert "#pragma vertex vert_img" in result
    assert "tex2D(_MainTex" in result


def test_patch_decompiled_project_integration(tmp_path: Path):
    """Integration test verifying patch_decompiled_project restores shaders alongside DLL and manifest patches."""
    proj = tmp_path / "FullProject"
    assets_dir = proj / "Assets"
    assets_dir.mkdir(parents=True)
    shaders_dir = assets_dir / "Resources" / "shaders"
    shaders_dir.mkdir(parents=True)

    dummy_shader = shaders_dir / "TextMeshPro_Sprite.shader"
    dummy_shader.write_text('Shader "TextMeshPro/Sprite" {\n//DummyShaderTextExporter\n}\n', encoding="utf-8")
    meta = shaders_dir / "TextMeshPro_Sprite.shader.meta"
    meta.write_text("guid: aaabbb111222\n", encoding="utf-8")

    managed_dir = tmp_path / "Game_Data" / "Managed"
    managed_dir.mkdir(parents=True)

    patches = patch_decompiled_project(proj, managed_dir)
    assert any("Restored authentic TextMeshPro shader" in p for p in patches)
    assert "DummyShaderTextExporter" not in dummy_shader.read_text(encoding="utf-8")
    assert "guid: aaabbb111222" in meta.read_text(encoding="utf-8")


def test_patch_unity_2018_manifest_dependencies(tmp_path: Path):
    """Test that Unity 2018 projects do not receive com.unity.ugui and receive textmeshpro 1.4.1."""
    proj = tmp_path / "Unity2018Project"
    proj.mkdir(parents=True)
    ps_dir = proj / "ProjectSettings"
    ps_dir.mkdir()
    (ps_dir / "ProjectVersion.txt").write_text("m_EditorVersion: 2018.4.14f1\n", encoding="utf-8")

    pkgs_dir = proj / "Packages"
    pkgs_dir.mkdir()
    manifest = pkgs_dir / "manifest.json"
    # Pre-populate with stale com.unity.ugui to test removal
    manifest.write_text(json.dumps({"dependencies": {"com.unity.ugui": "1.0.0"}}), encoding="utf-8")

    managed_dir = tmp_path / "Game_Data" / "Managed"
    managed_dir.mkdir(parents=True)

    patches = patch_decompiled_project(proj, managed_dir)
    assert any("Removed incompatible com.unity.ugui dependency for Unity 2018" in p for p in patches)

    data = json.loads(manifest.read_text(encoding="utf-8"))
    deps = data.get("dependencies", {})
    assert "com.unity.ugui" not in deps
    assert deps.get("com.unity.textmeshpro") == "1.4.1"
    assert deps.get("com.unity.postprocessing") == "2.1.7"


def test_restore_compute_shaders(tmp_path: Path):
    """Test that serialized ComputeShader assets are converted to cross-platform .compute files with preserved GUIDs."""
    from uaporter.android.project_patcher import restore_compute_shaders

    proj = tmp_path / "ComputeProject"
    cs_dir = proj / "Assets" / "ComputeShader"
    cs_dir.mkdir(parents=True)

    asset_file = cs_dir / "Compression.asset"
    asset_file.write_text("""%YAML 1.1
ComputeShader:
  m_Name: Compression
  variants:
  - kernels:
    - name: CSMain0
    - name: CSMain1
    - name: CSMain2
""", encoding="utf-8")

    meta_file = cs_dir / "Compression.asset.meta"
    guid = "450871529d525d4488e042c81310bccb"
    meta_file.write_text(f"fileFormatVersion: 2\nguid: {guid}\n", encoding="utf-8")

    patches = restore_compute_shaders(proj)
    assert any("Converted ComputeShader asset to native shader: Compression.compute" in p for p in patches)

    assert not asset_file.exists()
    assert not meta_file.exists()

    compute_file = cs_dir / "Compression.compute"
    compute_meta = cs_dir / "Compression.compute.meta"
    assert compute_file.is_file()
    assert compute_meta.is_file()

    compute_text = compute_file.read_text(encoding="utf-8")
    assert "#pragma kernel CSMain0" in compute_text
    assert "#pragma kernel CSMain1" in compute_text
    assert "#pragma kernel CSMain2" in compute_text
    assert "void CSMain0(uint3 id : SV_DispatchThreadID)" in compute_text
    assert "void CSMain1(uint3 id : SV_DispatchThreadID)" in compute_text
    assert f"guid: {guid}" in compute_meta.read_text(encoding="utf-8")


def test_patch_runtime_script_layouts(tmp_path: Path):
    """Test that runtime scripts with TextMeshPro dialogue updates are patched with ForceMeshUpdate and ForceRebuildLayoutImmediate."""
    from uaporter.android.project_patcher import patch_runtime_script_layouts

    proj = tmp_path / "ScriptProject"
    scripts_dir = proj / "Assets" / "Scripts"
    scripts_dir.mkdir(parents=True)

    dialog_script = scripts_dir / "DialogUI.cs"
    dialog_script.write_text("""using UnityEngine;
public class DialogUI : MonoBehaviour
{
    public void ShowDialog(string dialog)
    {
        _text.text = _dialog;
        _text.gameObject.SetActive(value: true);
        LeanTween.scale(_text.gameObject, Vector3.one, 0.33f);
    }
}
""", encoding="utf-8")

    patches = patch_runtime_script_layouts(proj)
    assert any("Patched TextMeshPro layout update in: DialogUI.cs" in p for p in patches)

    updated_code = dialog_script.read_text(encoding="utf-8")
    assert "_text.ForceMeshUpdate();" in updated_code
    assert "LayoutRebuilder.ForceRebuildLayoutImmediate(_text.rectTransform);" in updated_code


def test_get_essential_packages_for_unity():
    """Test essential packages mapping across Unity versions."""
    from uaporter.core.models import UnityVersion
    from uaporter.android.project_patcher import get_essential_packages_for_unity

    p2018 = get_essential_packages_for_unity(UnityVersion(2018, 4, 14, "f1"))
    assert "com.unity.ugui" not in p2018
    assert p2018.get("com.unity.textmeshpro") == "1.4.1"

    p2019 = get_essential_packages_for_unity(UnityVersion(2019, 4, 8, "f1"))
    assert p2019.get("com.unity.ugui") == "1.0.0"
    assert p2019.get("com.unity.textmeshpro") == "2.0.0"
    p2019_urp = get_essential_packages_for_unity(
        UnityVersion(2019, 4, 8, "f1"), is_urp=True
    )
    assert p2019_urp.get("com.unity.render-pipelines.core") == "7.1.8"
    assert p2019_urp.get("com.unity.render-pipelines.universal") == "7.1.8"

    p2020 = get_essential_packages_for_unity(UnityVersion(2020, 3, 48, "f1"))
    assert p2020.get("com.unity.textmeshpro") == "3.0.6"

    p2021 = get_essential_packages_for_unity(UnityVersion(2021, 1, 4, "f1"))
    assert p2021.get("com.unity.textmeshpro") == "3.0.6"
    assert "com.unity.2d.sprite" in p2021

    p2021_lts = get_essential_packages_for_unity(
        UnityVersion(2021, 3, 15, "f1"), is_urp=True
    )
    assert p2021_lts.get("com.unity.textmeshpro") == "3.0.9"
    assert p2021_lts.get("com.unity.postprocessing") == "3.5.1"
    assert p2021_lts.get("com.unity.render-pipelines.core") == "12.1.7"


def test_sanitize_render_pipeline_apis_for_older_editor(tmp_path: Path):
    from uaporter.android.project_patcher import sanitize_render_pipeline_package_apis
    from uaporter.core.models import UnityVersion

    package = (
        tmp_path / "Library" / "PackageCache"
        / "com.unity.render-pipelines.universal@7.1.8" / "Editor"
    )
    package.mkdir(parents=True)
    source = package / "UniversalRenderPipelineCameraEditor.cs"
    source.write_text(
        "using System.Collections.Generic;\n"
        "interface IRemoveAdditionalDataContextualMenu<T> { "
        "void RemoveComponent(T component, IEnumerable<Component> dependencies); }\n"
        "class X : IRemoveAdditionalDataContextualMenu<Camera> {\n"
        "  public void RemoveComponent(Camera camera) {}\n"
        "  case GraphicsDeviceType.PlayStation5:\n"
        "}\n",
        encoding="utf-8",
    )

    patches = sanitize_render_pipeline_package_apis(
        tmp_path, UnityVersion(2019, 4, 8, "f1")
    )

    updated = (
        tmp_path
        / "UAPorterPackages"
        / "com.unity.render-pipelines.universal"
        / "Editor"
        / source.name
    ).read_text(encoding="utf-8")
    assert patches
    assert "RemoveComponent(Camera camera, I" in updated
    assert "GraphicsDeviceType.PlayStation5" not in updated
    assert not (
        tmp_path
        / "Library"
        / "PackageCache"
        / "com.unity.render-pipelines.universal@7.1.8"
    ).exists()


def test_sanitize_render_pipeline_apis_follows_declared_interface(tmp_path: Path):
    from uaporter.android.project_patcher import sanitize_render_pipeline_package_apis
    from uaporter.core.models import UnityVersion

    package = (
        tmp_path / "Packages" / "com.unity.render-pipelines.core@custom"
    )
    package.mkdir(parents=True)
    (package / "ContextualMenuDispatcher.cs").write_text(
        "using System.Collections.Generic;\n"
        "interface IRemoveAdditionalDataContextualMenu<T> { "
        "void RemoveComponent(T component, IEnumerable<Component> dependencies); }\n",
        encoding="utf-8",
    )
    source = package / "CameraEditor.cs"
    source.write_text(
        "class X : IRemoveAdditionalDataContextualMenu<Camera> { "
        "public void RemoveComponent(Camera camera) {} }\n",
        encoding="utf-8",
    )

    sanitize_render_pipeline_package_apis(
        tmp_path, UnityVersion(2022, 3, 0, "f1")
    )

    assert "IEnumerable<Component> dependencies" in source.read_text(
        encoding="utf-8"
    )


def test_sanitize_render_pipeline_apis_preserves_local_override_on_rerun(
    tmp_path: Path,
):
    from uaporter.android.project_patcher import sanitize_render_pipeline_package_apis
    from uaporter.core.models import UnityVersion

    package = tmp_path / "UAPorterPackages" / "com.unity.render-pipelines.universal"
    editor = package / "Editor"
    editor.mkdir(parents=True)
    (editor / "ContextualMenuDispatcher.cs").write_text(
        "using System.Collections.Generic;\n"
        "interface IRemoveAdditionalDataContextualMenu<T> { "
        "void RemoveComponent(T component, IEnumerable<Component> dependencies); }\n",
        encoding="utf-8",
    )
    source = editor / "UniversalRenderPipelineCameraEditor.cs"
    source.write_text(
        "class X : IRemoveAdditionalDataContextualMenu<Camera> { "
        "public void RemoveComponent(Camera camera) {} }\n",
        encoding="utf-8",
    )
    packages = tmp_path / "Packages"
    packages.mkdir()
    manifest = packages / "manifest.json"
    manifest.write_text(
        '{"dependencies": {"com.unity.render-pipelines.universal": "7.1.8"}}',
        encoding="utf-8",
    )
    (packages / "packages-lock.json").write_text("{}", encoding="utf-8")

    sanitize_render_pipeline_package_apis(
        tmp_path, UnityVersion(2019, 4, 8, "f1")
    )

    assert json.loads(manifest.read_text(encoding="utf-8"))["dependencies"][
        "com.unity.render-pipelines.universal"
    ] == "file:../UAPorterPackages/com.unity.render-pipelines.universal"
    assert not (packages / "packages-lock.json").exists()
    assert "IEnumerable<Component> dependencies" in source.read_text(
        encoding="utf-8"
    )


def test_disable_resolution_dialog(tmp_path: Path):
    """Test that displayResolutionDialog: 1 is changed to 0 in ProjectSettings.asset."""
    from uaporter.android.project_patcher import disable_resolution_dialog

    proj = tmp_path / "ResProj"
    ps_dir = proj / "ProjectSettings"
    ps_dir.mkdir(parents=True)
    ps_asset = ps_dir / "ProjectSettings.asset"
    ps_asset.write_text("  displayResolutionDialog: 1\n  runInBackground: 1\n", encoding="utf-8")

    patches = disable_resolution_dialog(proj)
    assert any("Disabled deprecated resolution dialog" in p for p in patches)
    assert "displayResolutionDialog: 0" in ps_asset.read_text(encoding="utf-8")


def test_harmonize_tmp_text_alignment(tmp_path: Path):
    """Test that TextMeshPro alignment 65535 is harmonized to combined horizontal and vertical flags."""
    from uaporter.android.project_patcher import harmonize_tmp_text_alignment

    proj = tmp_path / "AlignProj"
    scenes_dir = proj / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)
    scene_file = scenes_dir / "Main.unity"
    scene_file.write_text("""  m_HorizontalAlignment: 2
  m_VerticalAlignment: 1024
  m_textAlignment: 65535
""", encoding="utf-8")

    patches = harmonize_tmp_text_alignment(proj)
    assert any("Harmonized 1 TextMeshPro alignment" in p for p in patches)
    new_text = scene_file.read_text(encoding="utf-8")
    assert "m_textAlignment: 1026" in new_text


def test_optimize_project_import_speed(tmp_path: Path):
    """Test that EditorSettings and texture meta files are optimized for fast asset importing."""
    from uaporter.android.project_patcher import optimize_project_import_speed

    proj = tmp_path / "SpeedProj"
    ps_dir = proj / "ProjectSettings"
    ps_dir.mkdir(parents=True)
    (ps_dir / "EditorSettings.asset").write_text("""EditorSettings:
  m_EtcTextureFastCompressor: 1
  m_EtcTextureNormalCompressor: 2
  m_EtcTextureBestCompressor: 4
""", encoding="utf-8")

    tex_dir = proj / "Assets" / "Texture2D"
    tex_dir.mkdir(parents=True)
    meta_file = tex_dir / "test.png.meta"
    meta_file.write_text("""TextureImporter:
  compressionQuality: 50
  platformSettings:
  - textureCompression: 2
    compressionQuality: 50
""", encoding="utf-8")

    patches = optimize_project_import_speed(proj)
    assert any("Optimized EditorSettings.asset" in p for p in patches)
    assert any("Accelerated 1 textures" in p for p in patches)

    new_meta = meta_file.read_text(encoding="utf-8")
    assert "compressionQuality: 0" in new_meta
    assert "textureCompression: 1" in new_meta

    new_settings = (ps_dir / "EditorSettings.asset").read_text(encoding="utf-8")
    assert "m_EtcTextureNormalCompressor: 1" in new_settings
    assert "m_AssetPipelineMode: 1" in new_settings


def test_sanitize_ui_canvas_layouts(tmp_path: Path):
    """Test that CanvasScaler and RectTransform layouts are preserved without destructive changes."""
    from uaporter.android.project_patcher import sanitize_ui_canvas_layouts

    proj = tmp_path / "UIPosProj"
    scenes_dir = proj / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)

    menu_scene = scenes_dir / "main_menu.unity"
    orig_text = """--- !u!114 &100
MonoBehaviour:
  m_UiScaleMode: 1
  m_ReferenceResolution: {x: 800, y: 600}
  m_ScreenMatchMode: 0
  m_MatchWidthOrHeight: 0
--- !u!224 &200
RectTransform:
  m_AnchorMin: {x: 0, y: 0.5}
  m_AnchorMax: {x: 0, y: 0.5}
  m_AnchoredPosition: {x: -229.2, y: -1.69}
  m_SizeDelta: {x: 400, y: 400}
"""
    menu_scene.write_text(orig_text, encoding="utf-8")

    patches = sanitize_ui_canvas_layouts(proj)
    # Authentic UI layout must be preserved (no-op)
    assert menu_scene.read_text(encoding="utf-8") == orig_text


def test_unify_text_layout_repairs_invalid_rect_transform_vectors(tmp_path: Path):
    """Invalid exported vectors are repaired without changing valid layout values."""
    from uaporter.android.project_patcher import unify_text_layout_system

    proj = tmp_path / "InvalidLayoutProject"
    assets_dir = proj / "Assets"
    assets_dir.mkdir(parents=True)
    scene = assets_dir / "invalid.unity"
    scene.write_text(
        """--- !u!224 &1
RectTransform:
  m_Pivot: {x: .nan, y: 0.5}
  m_AnchorMin: {x: 0, y: 0}
  m_AnchorMax: {x: 1e9, y: 1}
  m_OffsetMin: {x: -10001, y: 2}
  m_OffsetMax: {x: 3, y: .inf}
  m_AnchoredPosition: {x: 12.5, y: -3.25}
""",
        encoding="utf-8",
    )

    patches = unify_text_layout_system(proj)
    result = scene.read_text(encoding="utf-8")

    assert patches
    assert "m_Pivot: {x: 0.5, y: 0.5}" in result
    assert "m_AnchorMin: {x: 0, y: 0}" in result
    assert "m_AnchorMax: {x: 1, y: 1}" in result
    assert "m_OffsetMin: {x: 0, y: 0}" in result
    assert "m_OffsetMax: {x: 0, y: 0}" in result
    assert "m_AnchoredPosition: {x: 12.5, y: -3.25}" in result


def test_fix_common_cs_syntax_errors_normalizes_decompiler_wrapped_calls(tmp_path: Path):
    from uaporter.android.project_patcher import fix_common_cs_syntax_errors

    scripts_dir = tmp_path / "Assets" / "Scripts"
    scripts_dir.mkdir(parents=True)
    script = scripts_dir / "SaveManager.cs"
    script.write_text(
        'if (PlayerPrefs.HasKey(("save")))\n'
        '{\n'
        '    PlayerPrefs.SetString(("save"), value);\n'
        '}',
        encoding="utf-8",
    )

    patches = fix_common_cs_syntax_errors(tmp_path)

    assert patches
    assert script.read_text(encoding="utf-8") == (
        'if (PlayerPrefs.HasKey("save"))\n'
        '{\n'
        '    PlayerPrefs.SetString("save", value);\n'
        '}'
    )


def test_fix_common_cs_syntax_errors_repairs_missing_control_parenthesis(tmp_path: Path):
    from uaporter.android.project_patcher import fix_common_cs_syntax_errors

    scripts_dir = tmp_path / "Assets" / "Scripts"
    scripts_dir.mkdir(parents=True)
    script = scripts_dir / "SaveManager.cs"
    script.write_text('if (PlayerPrefs.HasKey("save")\n{\n}\n', encoding="utf-8")

    fix_common_cs_syntax_errors(tmp_path)

    assert 'if (PlayerPrefs.HasKey("save"))\n' in script.read_text(encoding="utf-8")


def test_fix_common_cs_syntax_errors_repairs_truncated_nested_call(tmp_path: Path):
    from uaporter.android.project_patcher import fix_common_cs_syntax_errors

    scripts_dir = tmp_path / "Assets" / "Scripts"
    scripts_dir.mkdir(parents=True)
    script = scripts_dir / "P3dHelper.cs"
    script.write_text(
        "return PlayerPrefs.HasKey((saveName);\n",
        encoding="utf-8",
    )

    fix_common_cs_syntax_errors(tmp_path)

    assert script.read_text(encoding="utf-8") == (
        "return PlayerPrefs.HasKey(saveName);\n"
    )


def test_runtime_shim_qualifies_unity_debug_api(tmp_path: Path):
    from uaporter.android.project_patcher import inject_runtime_compatibility_shims

    (tmp_path / "Assets").mkdir()
    inject_runtime_compatibility_shims(tmp_path)

    shim = (tmp_path / "Assets/Scripts/Runtime/UAPorterRuntimeCompatibility.cs").read_text(
        encoding="utf-8"
    )
    assert "UnityEngine.Debug.LogWarning" in shim
    assert "UnityEngine.Debug.LogError" in shim
    assert "\n                Debug.LogWarning" not in shim
    assert "\n                Debug.LogError" not in shim


def test_editor_helpers_qualify_unity_debug_api(tmp_path: Path):
    from uaporter.android.project_patcher import inject_runtime_compatibility_shims

    (tmp_path / "Assets").mkdir()
    inject_runtime_compatibility_shims(tmp_path)

    helpers = (tmp_path / "Assets/Scripts/Editor/UAPorterEditorHelpers.cs").read_text(
        encoding="utf-8"
    )
    assert "UnityEngine.Debug.Log(" in helpers
    assert "\n            Debug.Log(" not in helpers


def test_build_validator_qualifies_shadowable_unity_apis(tmp_path: Path):
    from uaporter.android.project_patcher import enhance_build_reliability

    (tmp_path / "Assets").mkdir()
    enhance_build_reliability(tmp_path)

    validator = (tmp_path / "Assets/Scripts/Editor/UAPorterBuildValidator.cs").read_text(
        encoding="utf-8"
    )
    assert "UnityEngine.Debug.Log" in validator
    assert "UnityEngine.Application.dataPath" in validator
    assert "\n                Debug.Log" not in validator


def test_builder_verify_build_success(tmp_path: Path):
    """Test that build verification tolerates exit-teardown signals when the binary exists and was confirmed."""
    from uaporter.android.builder import _verify_build_success

    bin_path = tmp_path / "game.x86_64"
    log_path = tmp_path / "build.log"

    # 1. Output file missing -> False
    assert not _verify_build_success(0, bin_path, log_path)

    # 2. Output file exists and returncode 0 -> True
    bin_path.write_text("ELF binary")
    assert _verify_build_success(0, bin_path, log_path)

    # 3. Output file exists, returncode -6 (SIGABRT), log contains success marker -> True
    log_path.write_text("[UAPorter] Linux Build Succeeded: 12345 bytes")
    assert _verify_build_success(-6, bin_path, log_path, "Linux")

    # 4. Output file exists, returncode -6, but log does not contain success marker -> False
    log_path.write_text("Fatal compile error occurred")
    assert not _verify_build_success(-6, bin_path, log_path, "Linux")


def test_is_urp_project_detection(tmp_path: Path):
    """Test reliable detection of URP across various project indicators."""
    from uaporter.android.project_patcher import is_urp_project

    proj = tmp_path / "URPProject"
    proj.mkdir(parents=True)

    # 1. Empty project -> False
    assert not is_urp_project(proj)

    # 2. Managed DLL indicator
    data_dir = tmp_path / "Game_Data"
    managed = data_dir / "Managed"
    managed.mkdir(parents=True)
    urp_dll = managed / "Unity.RenderPipelines.Universal.Runtime.dll"
    urp_dll.touch()
    assert is_urp_project(proj, data_dir)

    # 3. Assets DLL indicator
    urp_dll.unlink()
    assets_plugins = proj / "Assets" / "Plugins"
    assets_plugins.mkdir(parents=True)
    (assets_plugins / "Unity.RenderPipelines.Universal.Runtime.dll").touch()
    assert is_urp_project(proj)

    # Clean up Assets DLL
    (assets_plugins / "Unity.RenderPipelines.Universal.Runtime.dll").unlink()
    assert not is_urp_project(proj)

    # 4. GraphicsSettings.asset indicator
    settings_dir = proj / "ProjectSettings"
    settings_dir.mkdir(parents=True)
    graphics = settings_dir / "GraphicsSettings.asset"
    graphics.write_text("m_CustomRenderPipeline: {fileID: 11400000, guid: abc123def, type: 2}\n", encoding="utf-8")
    assert is_urp_project(proj)

    # Null custom render pipeline -> False
    graphics.write_text("m_CustomRenderPipeline: {fileID: 0}\n", encoding="utf-8")
    assert not is_urp_project(proj)

    # 5. UniversalRenderPipelineAsset.asset in Assets
    mb_dir = proj / "Assets" / "MonoBehaviour"
    mb_dir.mkdir(parents=True)
    (mb_dir / "UniversalRenderPipelineAsset.asset").touch()
    assert is_urp_project(proj)


def test_sanitize_dummy_shaders(tmp_path: Path):
    """Test sanitization of dummy surface shaders exported by AssetRipper for URP and Built-in pipelines."""
    from uaporter.android.project_patcher import sanitize_dummy_shaders

    proj = tmp_path / "DummyShaderProj"
    shader_dir = proj / "Assets" / "Shader"
    shader_dir.mkdir(parents=True)

    dummy_glow = shader_dir / "Shader Graphs_glow.shader"
    dummy_glow.write_text("""Shader "Shader Graphs/glow" {
    Properties {
        [NoScaleOffset] _MainTex ("_MainTex", 2D) = "white" {}
        _Color ("Color", Color) = (1, 1, 1, 1)
    }
    Fallback "Diffuse"
    //DummyShaderTextExporter
    SubShader{
        Tags { "RenderType"="Opaque" }
        LOD 200
        CGPROGRAM
#pragma surface surf Standard
#pragma target 3.0
        sampler2D _MainTex;
        struct Input { float2 uv_MainTex; };
        void surf (Input IN, inout SurfaceOutputStandard o) {
            fixed4 c = tex2D (_MainTex, IN.uv_MainTex);
            o.Albedo = c.rgb;
            o.Alpha = c.a;
        }
        ENDCG
    }
}
""", encoding="utf-8")

    # 1. Sanitize for URP
    patches = sanitize_dummy_shaders(proj, is_urp=True)
    assert any("Sanitized URP dummy shader with authentic render passes" in p for p in patches)

    content = dummy_glow.read_text(encoding="utf-8")
    assert '//DummyShaderTextExporter' in content
    assert 'Tags { "LightMode" = "Universal2D" }' in content
    assert 'Tags { "LightMode" = "SRPDefaultUnlit" }' in content
    assert 'Tags { "LightMode" = "UniversalForward" }' in content
    assert 'Fallback "Sprites/Default"' in content
    assert '#pragma surface surf Standard' not in content

    # 2. Built-in pipeline sanitization
    dummy_ui = shader_dir / "UI_Custom.shader"
    dummy_ui.write_text("""Shader "UI/Custom" {
    Properties { _MainTex ("Texture", 2D) = "white" {} }
    Fallback "Diffuse"
    //DummyShaderTextExporter
    SubShader { Tags { "Queue"="Transparent" } }
}
""", encoding="utf-8")
    builtin_patches = sanitize_dummy_shaders(proj, is_urp=False)
    assert any("Sanitized fallback for dummy UI/sprite shader" in p for p in builtin_patches)
    assert 'Fallback "Sprites/Default"' in dummy_ui.read_text(encoding="utf-8")


def test_remap_urp_and_tile_guids(tmp_path: Path):
    """Test remapping of URP components, Tilemap MonoScripts, package materials, and ColorGradients."""
    from uaporter.android.project_patcher import remap_package_guids

    proj = tmp_path / "URPRemapProj"
    assets_dir = proj / "Assets"
    scenes_dir = assets_dir / "Scenes"
    mb_dir = assets_dir / "MonoBehaviour"
    scenes_dir.mkdir(parents=True)
    mb_dir.mkdir(parents=True)

    # Scene with Tile MonoScript pointing to dummy assembly and URP Volume
    scene_file = scenes_dir / "Level.unity"
    scene_file.write_text("""--- !u!114 &10
MonoBehaviour:
  m_Script: {fileID: -2042537970, guid: f70555f144d8491a825f0804e09c671c, type: 3}
--- !u!114 &11
MonoBehaviour:
  m_Script: {fileID: 1520420858, guid: 57c9a3e5193e26c4b968cc86e528416d, type: 3}
""", encoding="utf-8")

    # RendererData asset with type: 2 package materials
    renderer_data = mb_dir / "New 2D Renderer Data.asset"
    renderer_data.write_text("""--- !u!114 &11400000
MonoBehaviour:
  m_Script: {fileID: 2042377659, guid: c88ab7b37c4f350242674d2efd621c19, type: 3}
  m_DefaultLitMaterial: {fileID: 2100000, guid: a97c105638bdf8b4a8650670310a4cd3, type: 2}
  m_DefaultUnlitMaterial: {fileID: 2100000, guid: 9dfc825aed78fcd4ba02077103263b40, type: 2}
""", encoding="utf-8")

    # ColorGradient preset with old TMP guid
    gradient_file = mb_dir / "Preset.asset"
    gradient_file.write_text("""--- !u!114 &11400000
MonoBehaviour:
  m_Script: {fileID: 2108210716, guid: 67dfb1fdfb2b407222eda8e23ac8b724, type: 3}
""", encoding="utf-8")

    remapped = remap_package_guids(proj)
    assert remapped == 3

    # Check Tile MonoScript remapping to built-in resources
    scene_text = scene_file.read_text(encoding="utf-8")
    assert "fileID: 13312, guid: 0000000000000000e000000000000000, type: 0" in scene_text
    # Check URP Volume remapping
    assert "guid: 172515602e62fb746b5d573b38a5fe58" in scene_text

    # Check Renderer2DData and package materials type: 3
    renderer_text = renderer_data.read_text(encoding="utf-8")
    assert "guid: 11145981673336645838492a2d98e247" in renderer_text
    assert "guid: a97c105638bdf8b4a8650670310a4cd3, type: 3" in renderer_text
    assert "guid: 9dfc825aed78fcd4ba02077103263b40, type: 3" in renderer_text

    # Check TMP_ColorGradient remapping
    grad_text = gradient_file.read_text(encoding="utf-8")
    assert "guid: 54d21f6ece3b46479f0c328f8c6007e0" in grad_text


def test_patch_decompiled_project_urp_integration(tmp_path: Path):
    """Test full patch_decompiled_project pipeline on a mock URP project."""
    proj = tmp_path / "ExportedURPProject"
    assets_dir = proj / "Assets"
    plugins_dir = assets_dir / "Plugins"
    shader_dir = assets_dir / "Shader"
    settings_dir = proj / "ProjectSettings"
    pkgs_dir = proj / "Packages"

    for d in (plugins_dir, shader_dir, settings_dir, pkgs_dir):
        d.mkdir(parents=True)

    # ProjectVersion: Unity 2021.1.0f1
    (settings_dir / "ProjectVersion.txt").write_text("m_EditorVersion: 2021.1.0f1\n", encoding="utf-8")

    # GraphicsSettings indicates URP
    (settings_dir / "GraphicsSettings.asset").write_text(
        "m_CustomRenderPipeline: {fileID: 11400000, guid: c88ab7b37c4f350242674d2efd621c19, type: 2}\n",
        encoding="utf-8"
    )

    # Redundant URP precompiled DLL
    urp_dll = plugins_dir / "Unity.RenderPipelines.Universal.Runtime.dll"
    urp_dll.touch()
    (plugins_dir / "Unity.RenderPipelines.Universal.Runtime.dll.meta").write_text(
        "fileFormatVersion: 2\nguid: c88ab7b37c4f350242674d2efd621c19\n", encoding="utf-8"
    )

    # Valid game plugin DLL with Editor: Editor enabled: 0
    tilemap_dll = plugins_dir / "Unity.2D.Tilemap.Extras.dll"
    tilemap_dll.touch()
    tilemap_meta = plugins_dir / "Unity.2D.Tilemap.Extras.dll.meta"
    tilemap_meta.write_text("""fileFormatVersion: 2
guid: aacef1ceba662d74a203c134fe7594c3
PluginImporter:
  platformData:
  - first:
      Editor: Editor
    second:
      enabled: 0
""", encoding="utf-8")

    # Dummy shader
    dummy_shader = shader_dir / "Shader Graphs_glow.shader"
    dummy_shader.write_text("""Shader "Shader Graphs/glow" {
    Properties { _MainTex ("Texture", 2D) = "white" {} }
    //DummyShaderTextExporter
    SubShader { Tags { "RenderType"="Opaque" } CGPROGRAM #pragma surface surf Standard ENDCG }
}
""", encoding="utf-8")

    # Original game data dir mock
    orig_data = tmp_path / "OrigGame_Data"
    (orig_data / "Managed").mkdir(parents=True)

    patches = patch_decompiled_project(proj, orig_data)

    # 1. Verify manifest pinned URP packages
    manifest_data = json.loads((pkgs_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_data["dependencies"].get("com.unity.render-pipelines.universal") == "11.0.0"
    assert manifest_data["dependencies"].get("com.unity.render-pipelines.core") == "11.0.0"

    # 2. Verify redundant URP DLL was cleaned up
    assert not urp_dll.exists()
    assert not (plugins_dir / "Unity.RenderPipelines.Universal.Runtime.dll.meta").exists()

    # 3. Verify game plugin DLL had Editor: Editor enabled: 1 fixed
    assert "enabled: 1" in tilemap_meta.read_text(encoding="utf-8")

    # 4. Verify dummy shader was sanitized with URP passes
    shader_text = dummy_shader.read_text(encoding="utf-8")
    assert 'Tags { "LightMode" = "Universal2D" }' in shader_text
    assert 'Fallback "Sprites/Default"' in shader_text
