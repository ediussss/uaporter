"""Tests for Unity manager and toolchain components."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uaporter.core.models import UnityVersion
from uaporter.toolchain.cache import CacheManager
from uaporter.toolchain.unity_manager import UnityManager


def test_cache_manager(tmp_path: Path):
    cache = CacheManager(root_dir=tmp_path / ".uaporter")
    assert cache.cache_dir.is_dir()
    assert cache.tools_dir.is_dir()
    assert cache.unity_dir.is_dir()
    assert cache.sdk_dir.is_dir()

    ripper_dir = cache.get_assetripper_dir()
    assert ripper_dir.is_dir()


def test_unity_manager_resolution():
    mgr = UnityManager()
    
    # Mock catalog return
    mock_catalog = {
        "official": [
            {
                "version": "2019.3.15f1",
                "downloadUrl": "https://download.unity3d.com/download_unity/597fa5e3d7ea/LinuxEditorInstaller/Unity.tar.xz",
                "modules": [
                    {
                        "id": "android",
                        "downloadUrl": "https://download.unity3d.com/download_unity/597fa5e3d7ea/TargetSupportInstaller/UnitySetup-Android-Support-for-Editor-2019.3.15f1.tar.xz"
                    }
                ]
            }
        ]
    }
    
    with patch.object(mgr.catalog, "fetch_catalog", return_value=mock_catalog):
        res = mgr.resolve_editor_download_url(UnityVersion(2019, 3, 15, "f1"))
        assert res is not None
        editor_url, android_url = res
        assert "Unity.tar.xz" in editor_url
        assert "Android-Support" in android_url


def test_unity_manager_uninstall(tmp_path: Path):
    cache = CacheManager(root_dir=tmp_path / ".uaporter")
    mgr = UnityManager(cache_mgr=cache)
    ver = UnityVersion(2019, 2, 6, "f1")
    editor_dir = cache.unity_dir / str(ver)
    editor_dir.mkdir(parents=True, exist_ok=True)
    fake_bin = editor_dir / "Editor" / "Unity"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.touch()

    # Leftover archive
    archive = cache.cache_dir / f"Unity-{ver}.tar.xz"
    archive.touch()

    assert editor_dir.is_dir()
    assert archive.is_file()

    removed = mgr.uninstall_editor(ver)
    assert removed is True
    assert not editor_dir.exists()
    assert not archive.exists()


def test_patch_bee_backend(tmp_path: Path):
    editor_path = tmp_path / "Editor" / "Unity"
    editor_path.parent.mkdir(parents=True, exist_ok=True)
    editor_path.touch()

    data_dir = tmp_path / "Editor" / "Data"
    data_dir.mkdir(parents=True, exist_ok=True)
    bee_backend = data_dir / "bee_backend"
    bee_backend.write_bytes(b"\x7fELFfakebinarycontent")

    # First patch: should rename bee_backend to bee_backend_real and create wrapper script
    UnityManager.patch_bee_backend(editor_path)

    bee_real = data_dir / "bee_backend_real"
    assert bee_real.is_file()
    assert bee_real.read_bytes() == b"\x7fELFfakebinarycontent"
    assert bee_backend.is_file()
    content = bee_backend.read_text(encoding="utf-8")
    assert content.startswith("#!/bin/bash")
    assert "--stdin-canary" in content

    # Second patch: idempotent, should not re-wrap
    UnityManager.patch_bee_backend(editor_path)
    assert bee_real.read_bytes() == b"\x7fELFfakebinarycontent"


def test_clean_stale_locks(tmp_path: Path):
    from uaporter.android.builder import _clean_stale_locks
    temp_dir = tmp_path / "Temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    lock_file = temp_dir / "UnityLockfile"
    lock_file.touch()
    assert lock_file.is_file()

    _clean_stale_locks(tmp_path)
    assert not lock_file.exists()

