"""Test CLI Unity version prompt and uninstall flow."""

from unittest.mock import patch
from pathlib import Path
import pytest
import click
from uaporter.core.models import UnityVersion
from uaporter.cli import ensure_unity_editor


def test_ensure_unity_editor_exact_found():
    with patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_exact_editor", return_value=Path("/opt/unity/Editor/Unity")):
        res = ensure_unity_editor(UnityVersion(2019, 3, 0, "f6"), "test")
        assert res == Path("/opt/unity/Editor/Unity")


def test_ensure_unity_editor_prompt_uninstall_and_install():
    installed_path = Path("/home/edi/.uaporter/unity/2019.2.6f1/Editor/Unity")
    with patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_exact_editor", return_value=None), \
         patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_best_installed_editor", return_value=("2019.2.6f1", installed_path)), \
         patch("click.confirm", side_effect=[True, True]) as mock_confirm, \
         patch("uaporter.toolchain.unity_manager.UnityManager.uninstall_editor") as mock_uninstall, \
         patch("uaporter.toolchain.unity_manager.UnityManager.install_editor", return_value=Path("/home/edi/.uaporter/unity/2019.3.0f6/Editor/Unity")) as mock_install:

        res = ensure_unity_editor(UnityVersion(2019, 3, 0, "f6"), "test")
        assert res == Path("/home/edi/.uaporter/unity/2019.3.0f6/Editor/Unity")
        mock_uninstall.assert_called_once_with("2019.2.6f1")
        mock_install.assert_called_once_with(UnityVersion(2019, 3, 0, "f6"), include_android=False)
        assert mock_confirm.call_count == 2


def test_ensure_unity_editor_keep_old_and_proceed():
    installed_path = Path("/home/edi/.uaporter/unity/2019.2.6f1/Editor/Unity")
    with patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_exact_editor", return_value=None), \
         patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_best_installed_editor", return_value=("2019.2.6f1", installed_path)), \
         patch("click.confirm", side_effect=[False, False]), \
         patch("uaporter.toolchain.unity_manager.UnityManager.uninstall_editor") as mock_uninstall, \
         patch("uaporter.toolchain.unity_manager.UnityManager.install_editor") as mock_install:

        res = ensure_unity_editor(UnityVersion(2019, 3, 0, "f6"), "test")
        assert res == installed_path
        mock_uninstall.assert_not_called()
        mock_install.assert_not_called()


def test_ensure_unity_editor_uninstall_and_abort():
    installed_path = Path("/home/edi/.uaporter/unity/2019.2.6f1/Editor/Unity")
    with patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_exact_editor", return_value=None), \
         patch("uaporter.toolchain.hub_bridge.UnityHubBridge.find_best_installed_editor", return_value=("2019.2.6f1", installed_path)), \
         patch("click.confirm", side_effect=[True, False]), \
         patch("uaporter.toolchain.unity_manager.UnityManager.uninstall_editor") as mock_uninstall:

        with pytest.raises(click.Abort):
            ensure_unity_editor(UnityVersion(2019, 3, 0, "f6"), "test")
        mock_uninstall.assert_called_once_with("2019.2.6f1")
