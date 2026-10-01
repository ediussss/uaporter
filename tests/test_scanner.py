"""Tests for scanner module and version detection."""

import pytest
from pathlib import Path
from uaporter.core.models import Backend, PluginStatus, UnityVersion
from uaporter.scanner import (
    scan_game_directory,
    detect_unity_version,
    detect_backend,
    inspect_plugins,
    detect_structure,
)


def test_unity_version_parse():
    ver = UnityVersion.parse("2019.3.15f1")
    assert ver is not None
    assert ver.major == 2019
    assert ver.minor == 3
    assert ver.patch == 15
    assert ver.suffix == "f1"
    assert str(ver) == "2019.3.15f1"

    ver_b = UnityVersion.parse("2021.2.0b4")
    assert ver_b is not None
    assert ver_b.suffix == "b4"


def test_unity_version_comparison():
    v2018 = UnityVersion(2018, 4, 14, "f1")
    v2019_base = UnityVersion(2019, 3, 0)
    v2019_patch = UnityVersion(2019, 3, 15, "f1")
    v2021 = UnityVersion(2021, 1, 4, "f1")

    assert v2018 < v2019_base
    assert v2018 <= v2019_base
    assert not (v2018 >= v2019_base)
    assert not (v2018 > v2019_base)

    assert v2019_patch >= v2019_base
    assert v2019_patch > v2019_base
    assert v2021 >= v2019_base
    assert v2021 > v2019_patch
    assert v2019_base <= v2019_patch


def test_structure_detection(tmp_path: Path):
    game_dir = tmp_path / "KarlsonGame"
    game_dir.mkdir()
    (game_dir / "Karlson.exe").touch()
    data_dir = game_dir / "Karlson_Data"
    data_dir.mkdir()

    name, exe, data = detect_structure(game_dir)
    assert name == "Karlson"
    assert exe == game_dir / "Karlson.exe"
    assert data == data_dir


def test_version_detection_from_binary(tmp_path: Path):
    game_dir = tmp_path / "MyGame"
    game_dir.mkdir()
    data_dir = game_dir / "MyGame_Data"
    data_dir.mkdir()
    
    # Write a fake globalgamemanagers containing Unity version string
    ggm = data_dir / "globalgamemanagers"
    header_bytes = b"\x00\x00\x00\x00" + b"2019.3.15f1\x00" + b"\x00" * 50
    ggm.write_bytes(header_bytes)

    ver = detect_unity_version(game_dir, data_dir)
    assert ver is not None
    assert str(ver) == "2019.3.15f1"


def test_backend_mono(tmp_path: Path):
    game_dir = tmp_path / "MonoGame"
    game_dir.mkdir()
    data_dir = game_dir / "MonoGame_Data"
    data_dir.mkdir()
    managed_dir = data_dir / "Managed"
    managed_dir.mkdir()
    (managed_dir / "Assembly-CSharp.dll").touch()

    backend = detect_backend(game_dir, data_dir)
    assert backend == Backend.MONO


def test_backend_il2cpp(tmp_path: Path):
    game_dir = tmp_path / "IL2CPPGame"
    game_dir.mkdir()
    (game_dir / "GameAssembly.dll").touch()

    backend = detect_backend(game_dir)
    assert backend == Backend.IL2CPP


def test_plugin_inspection(tmp_path: Path):
    game_dir = tmp_path / "PluginGame"
    game_dir.mkdir()
    data_dir = game_dir / "PluginGame_Data"
    data_dir.mkdir()
    plugins_dir = data_dir / "Plugins" / "x86_64"
    plugins_dir.mkdir(parents=True)
    
    (plugins_dir / "steam_api64.dll").touch()
    (plugins_dir / "discord_rpc.dll").touch()
    (plugins_dir / "custom_native.dll").touch()

    plugins = inspect_plugins(game_dir, data_dir)
    plugin_names = {p.name for p in plugins}
    assert "steam_api64.dll" in plugin_names
    assert "discord_rpc.dll" in plugin_names
    assert "custom_native.dll" in plugin_names

    statuses = {p.name: p.status for p in plugins}
    assert statuses["steam_api64.dll"] == PluginStatus.STUB_SAFE
    assert statuses["custom_native.dll"] == PluginStatus.INFO


def test_full_scan_report(tmp_path: Path):
    game_dir = tmp_path / "Karlson"
    game_dir.mkdir()
    (game_dir / "Karlson.exe").touch()
    data_dir = game_dir / "Karlson_Data"
    data_dir.mkdir()
    managed = data_dir / "Managed"
    managed.mkdir()
    (managed / "Assembly-CSharp.dll").touch()
    (data_dir / "globalgamemanagers").write_bytes(b"2019.3.15f1\x00\x00")

    report = scan_game_directory(game_dir)
    assert report.game_name == "Karlson"
    assert report.unity_version is not None
    assert str(report.unity_version) == "2019.3.15f1"
    assert report.backend == Backend.MONO
    assert report.is_android_supported is True
    assert report.is_linux_supported is True


def test_game_maker_build_is_reported_as_unsupported(tmp_path: Path):
    game_dir = tmp_path / "MittensDescent"
    game_dir.mkdir()
    (game_dir / "Mittens Descent.exe").touch()
    (game_dir / "data.win").write_bytes(b"FORM")

    report = scan_game_directory(game_dir)

    assert not report.is_linux_supported
    assert any("GameMaker" in issue for issue in report.blocking_issues)
