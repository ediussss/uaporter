"""Test changeset resolution for known Unity versions."""

from uaporter.core.models import UnityVersion
from uaporter.toolchain.unity_manager import UnityManager


def test_resolve_2019_2_6f1():
    mgr = UnityManager()
    res = mgr.resolve_editor_download_url(UnityVersion(2019, 2, 6, "f1"))
    assert res is not None
    editor_url, android_url = res
    assert "fe82a0e88406" in editor_url
    assert "LinuxEditorInstaller/Unity.tar.xz" in editor_url


def test_resolve_2019_3_0f6():
    mgr = UnityManager()
    res = mgr.resolve_editor_download_url(UnityVersion(2019, 3, 0, "f6"))
    assert res is not None
    editor_url, android_url = res
    assert "27ab2135bccf" in editor_url
    assert "LinuxEditorInstaller/Unity.tar.xz" in editor_url
    assert "MacEditorTargetInstaller" in android_url


def test_dynamic_changeset_lookup():
    mgr = UnityManager()
    # 2018.4.36f1 is not in KNOWN_CHANGESETS, will be resolved dynamically
    res = mgr.resolve_editor_download_url(UnityVersion(2018, 4, 36, "f1"))
    assert res is not None
    editor_url, _ = res
    assert "LinuxEditorInstaller/Unity.tar.xz" in editor_url
