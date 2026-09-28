"""Tests for Unity Hub Bridge."""

from pathlib import Path
from unittest.mock import patch
from uaporter.core.models import UnityVersion
from uaporter.toolchain.hub_bridge import UnityHubBridge


def test_hub_editor_matcher():
    mock_editors = [
        ("2019.2.6f1", Path("/opt/unity/2019.2.6f1/Editor/Unity")),
        ("2021.3.16f1", Path("/opt/unity/2021.3.16f1/Editor/Unity")),
    ]
    with patch.object(UnityHubBridge, "get_installed_editors", return_value=mock_editors):
        # Exact match
        res = UnityHubBridge.find_exact_editor(UnityVersion(2019, 2, 6, "f1"))
        assert res == Path("/opt/unity/2019.2.6f1/Editor/Unity")

        # Best installed match
        match = UnityHubBridge.find_best_installed_editor(UnityVersion(2019, 3, 0, "f1"))
        assert match is not None
        ver_str, path = match
        assert ver_str == "2019.2.6f1"
        assert path == Path("/opt/unity/2019.2.6f1/Editor/Unity")

