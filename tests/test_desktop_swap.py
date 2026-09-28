"""Tests for desktop player swap and Steam Deck wrappers."""

from pathlib import Path
from uaporter.core.models import Backend, ScanReport, UnityVersion
from uaporter.desktop.steamdeck import generate_gamescope_wrapper, generate_desktop_entry
from uaporter.desktop.swapper import swap_to_linux


def test_gamescope_wrapper_generation(tmp_path: Path):
    wrapper = generate_gamescope_wrapper(tmp_path, "Karlson.x86_64")
    assert wrapper.exists()
    content = wrapper.read_text()
    assert "gamescope -W 1280 -H 800" in content
    assert "-force-vulkan" in content
    assert "Karlson.x86_64" in content


def test_desktop_entry_generation(tmp_path: Path):
    exe_path = tmp_path / "Karlson.x86_64"
    exe_path.touch()
    desktop_file = generate_desktop_entry(tmp_path, "Karlson", exe_path)
    assert desktop_file.exists()
    content = desktop_file.read_text()
    assert "Name=Karlson" in content
    assert f"Exec=\"{exe_path.resolve()}\"" in content


def test_swap_to_linux(tmp_path: Path):
    game_dir = tmp_path / "src_game"
    game_dir.mkdir()
    (game_dir / "Karlson.exe").touch()
    data_dir = game_dir / "Karlson_Data"
    data_dir.mkdir()
    (data_dir / "data.unity3d").touch()

    out_dir = tmp_path / "linux_out"

    report = ScanReport(
        game_path=game_dir,
        game_name="Karlson",
        data_dir=data_dir,
        executable_path=game_dir / "Karlson.exe",
        unity_version=UnityVersion(2019, 3, 15, "f1"),
        backend=Backend.MONO,
    )

    swap_to_linux(report, out_dir)

    assert (out_dir / "Karlson_Data").is_dir()
    assert (out_dir / "Karlson_Data" / "data.unity3d").is_file()
    assert (out_dir / "Karlson.x86_64").is_file()
    assert (out_dir / "run_Karlson.x86_64.sh").is_file()
    assert (out_dir / "Karlson.desktop").is_file()
