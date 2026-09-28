"""Android APK debug keystore generator and signer."""

from __future__ import annotations
from pathlib import Path
import subprocess
import shutil


def ensure_debug_keystore(keystore_path: Path) -> Path:
    """Generate a standard debug keystore if not already present."""
    if keystore_path.is_file():
        return keystore_path

    keystore_path.parent.mkdir(parents=True, exist_ok=True)
    
    keytool = shutil.which("keytool")
    if not keytool:
        raise RuntimeError("keytool (OpenJDK) is not installed or not in PATH.")

    cmd = [
        keytool,
        "-genkey", "-v",
        "-keystore", str(keystore_path),
        "-storepass", "android",
        "-alias", "androiddebugkey",
        "-keypass", "android",
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-dname", "CN=Android Debug,O=Android,C=US"
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return keystore_path


def sign_apk(apk_path: Path, keystore_path: Path) -> bool:
    """Sign an APK using apksigner or jarsigner."""
    if not apk_path.is_file():
        raise FileNotFoundError(f"Target APK does not exist: {apk_path}")

    apksigner = shutil.which("apksigner")
    if apksigner:
        cmd = [
            apksigner, "sign",
            "--ks", str(keystore_path),
            "--ks-pass", "pass:android",
            "--key-pass", "pass:android",
            "--ks-key-alias", "androiddebugkey",
            str(apk_path)
        ]
        subprocess.run(cmd, check=True)
        return True

    jarsigner = shutil.which("jarsigner")
    if jarsigner:
        cmd = [
            jarsigner,
            "-verbose",
            "-sigalg", "SHA256withRSA",
            "-digestalg", "SHA-256",
            "-keystore", str(keystore_path),
            "-storepass", "android",
            "-keypass", "android",
            str(apk_path),
            "androiddebugkey"
        ]
        subprocess.run(cmd, check=True)
        return True

    raise RuntimeError("Neither apksigner nor jarsigner found in PATH.")
