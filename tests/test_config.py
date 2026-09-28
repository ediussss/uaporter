"""Tests for user config and credential prompting."""

from pathlib import Path
from unittest.mock import patch
from uaporter.core.config import UserConfig


def test_config_load_and_save(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg = UserConfig.load(cfg_file)
    assert not cfg.is_configured

    cfg.unity_username = "tester@unity.com"
    cfg.save(cfg_file)

    loaded = UserConfig.load(cfg_file)
    assert loaded.is_configured
    assert loaded.unity_username == "tester@unity.com"


def test_prompt_credentials_if_needed(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg = UserConfig.load(cfg_file)
    assert not cfg.is_configured

    with patch("click.prompt", side_effect=["testuser@domain.com", ""]):
        with patch.object(cfg, "save"):
            cfg.prompt_credentials_if_needed()

    assert cfg.is_configured
    assert cfg.unity_username == "testuser@domain.com"
