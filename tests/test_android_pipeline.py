"""Tests for Android pipeline: decompilation, injection, and mock build."""

from pathlib import Path
from unittest.mock import MagicMock
from uaporter.core.models import Backend, ScanReport, UnityVersion
from uaporter.android.injector import inject_android_assets
from uaporter.android.decompiler import decompile_game


def test_android_injector(tmp_path: Path):
    project_dir = tmp_path / "ExportedProject"
    assets_dir = project_dir / "Assets"
    assets_dir.mkdir(parents=True)

    injected = inject_android_assets(project_dir)
    assert len(injected) >= 2
    assert (assets_dir / "Editor" / "UAPorter" / "PortBuilder.cs").is_file()
    assert (assets_dir / "Scripts" / "UAPorter" / "TouchManager.cs").is_file()


def test_decompile_game_flow(tmp_path: Path):
    game_dir = tmp_path / "Game"
    game_dir.mkdir()
    data_dir = game_dir / "Game_Data"
    data_dir.mkdir()

    out_project = tmp_path / "DecompiledUnityProject"

    report = ScanReport(
        game_path=game_dir,
        game_name="Game",
        data_dir=data_dir,
        executable_path=None,
        unity_version=UnityVersion(2019, 3, 15, "f1"),
        backend=Backend.MONO,
    )

    # Mock AssetRipperManager
    mock_ripper = MagicMock()
    mock_ripper.decompile.return_value = True

    res = decompile_game(report, out_project, ripper_mgr=mock_ripper, is_android=True)
    assert res.exists()
    assert (res / "Assets" / "Editor" / "UAPorter" / "PortBuilder.cs").is_file()
    assert (res / "Assets" / "Scripts" / "UAPorter" / "TouchManager.cs").is_file()

    # Test Linux decompile flow does not inject TouchManager
    out_linux = tmp_path / "LinuxDecompiled"
    res_linux = decompile_game(report, out_linux, ripper_mgr=mock_ripper, is_android=False)
    assert (res_linux / "Assets" / "Editor" / "UAPorter" / "PortBuilder.cs").is_file()
    assert not (res_linux / "Assets" / "Scripts" / "UAPorter" / "TouchManager.cs").exists()


def test_decompile_game_reuse_existing(tmp_path: Path):
    game_dir = tmp_path / "Game"
    game_dir.mkdir()
    data_dir = game_dir / "Game_Data"
    data_dir.mkdir()

    existing_project = tmp_path / "ExistingProject"
    (existing_project / "ProjectSettings").mkdir(parents=True)
    (existing_project / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 2019.3.15f1")
    (existing_project / "Assets").mkdir(parents=True)

    report = ScanReport(
        game_path=game_dir,
        game_name="Game",
        data_dir=data_dir,
        executable_path=None,
        unity_version=UnityVersion(2019, 3, 15, "f1"),
        backend=Backend.MONO,
    )

    mock_ripper = MagicMock()
    # Should reuse existing project and NOT call mock_ripper.decompile
    res = decompile_game(report, existing_project, ripper_mgr=mock_ripper, is_android=False)
    assert res == existing_project
    mock_ripper.decompile.assert_not_called()

    # If force_decompile=True, mock_ripper.decompile MUST be called
    mock_ripper.decompile.return_value = True
    res_forced = decompile_game(report, existing_project, ripper_mgr=mock_ripper, is_android=False, force_decompile=True)
    mock_ripper.decompile.assert_called_once()



def test_remap_package_guids(tmp_path: Path):
    from uaporter.android.project_patcher import remap_package_guids

    project_dir = tmp_path / "Project"
    scenes_dir = project_dir / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)

    dummy_scene = scenes_dir / "SampleScene.unity"
    # TextMeshProUGUI old fileID 1453722849 with extracted DLL guid
    dummy_scene.write_text(
        "--- !u!114 &100\n"
        "MonoBehaviour:\n"
        "  m_Script: {fileID: 1453722849, guid: 67dfb1fdfb2b407222eda8e23ac8b724, type: 3}\n",
        encoding="utf-8",
    )

    remapped = remap_package_guids(project_dir, old_tmp_guid="67dfb1fdfb2b407222eda8e23ac8b724")
    assert remapped == 1

    content = dummy_scene.read_text(encoding="utf-8")
    assert "guid: f4688fdb7df04437aeb418b961361dc5" in content
    assert "fileID: 11500000" in content


def test_remap_package_guids_dynamic_discovery(tmp_path: Path):
    from uaporter.android.project_patcher import remap_package_guids

    project_dir = tmp_path / "DynamicProject"
    scenes_dir = project_dir / "Assets" / "Scenes"
    scenes_dir.mkdir(parents=True)

    dummy_scene = scenes_dir / "UnknownGameScene.unity"
    dummy_scene.write_text(
        "--- !u!114 &100\n"
        "MonoBehaviour:\n"
        "  m_Script: {fileID: 1453722849, guid: 112233445566778899aabbccddeeff00, type: 3}\n"
        "--- !u!114 &101\n"
        "MonoBehaviour:\n"
        "  m_Script: {fileID: -1529857597, guid: aabbccddeeff00112233445566778899, type: 3}\n",
        encoding="utf-8",
    )

    remapped = remap_package_guids(project_dir)
    assert remapped == 1

    content = dummy_scene.read_text(encoding="utf-8")
    assert "guid: f4688fdb7df04437aeb418b961361dc5" in content
    assert "guid: 948f4100a11a5c24981795d21301da5c" in content
    assert "112233445566778899aabbccddeeff00" not in content
    assert "aabbccddeeff00112233445566778899" not in content


def test_assetripper_decompile_live_progress(tmp_path: Path):
    """Test that AssetRipperManager.decompile streams stdout lines and reports success."""
    from unittest.mock import patch, MagicMock
    from uaporter.toolchain.assetripper import AssetRipperManager

    mgr = AssetRipperManager()
    mgr.binary_path = tmp_path / "mock_AssetRipper"
    mgr.binary_path.touch()

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = [
        "Processing Game_Data\n",
        "Collecting game files...\n",
        "Loaded 500 assets in 12ms\n",
        "Exporting Assets\n",
        "Moving exported files to output directory\n",
    ]
    mock_proc.poll.return_value = 0
    mock_proc.wait.return_value = 0

    with patch("subprocess.Popen", return_value=mock_proc):
        success = mgr.decompile(tmp_path / "Game_Data", tmp_path / "OutProj")
        assert success is True



