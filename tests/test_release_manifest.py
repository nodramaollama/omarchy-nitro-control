#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import os
import stat
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PAYLOAD = {
    "install",
    "uninstall",
    "backend/nitro_control.py",
    "bin/nitroctl",
    "driver/select_verified_driver.py",
    "driver/verified-models.json",
    "driver/acer-wmi-anv16-0.1.0/SHA256SUMS",
    "driver/acer-wmi-anv16-0.1.0/Makefile",
    "driver/acer-wmi-anv16-0.1.0/acer-wmi.c",
    "driver/acer-wmi-anv16-0.1.0/dkms.conf",
    "systemd/nitro-control.service",
}


class ReleaseManifestTests(unittest.TestCase):
    def manifest(self) -> dict[str, str]:
        entries: dict[str, str] = {}
        for line in (ROOT / "release-manifest.sha256").read_text(encoding="ascii").splitlines():
            digest, path = line.split("  ", 1)
            self.assertEqual(len(digest), 64)
            self.assertNotIn(path, entries)
            entries[path] = digest
        return entries

    def test_manifest_has_exact_privileged_payload_coverage(self) -> None:
        self.assertEqual(set(self.manifest()), EXPECTED_PAYLOAD)

    def test_every_payload_digest_matches_a_single_link_regular_file(self) -> None:
        for relative, expected in self.manifest().items():
            path = ROOT / relative
            metadata = path.lstat()
            self.assertTrue(stat.S_ISREG(metadata.st_mode), relative)
            self.assertEqual(metadata.st_nlink, 1, relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), expected, relative)

    def test_privileged_entry_points_are_executable(self) -> None:
        for relative in ("install", "uninstall", "bin/nitroctl", "backend/nitro_control.py"):
            self.assertTrue(os.access(ROOT / relative, os.X_OK), relative)

    def test_installer_has_no_automatic_package_manager(self) -> None:
        installer = (ROOT / "install").read_text(encoding="utf-8")
        self.assertNotIn("pacman -S", installer)
        self.assertIn("O_NOFOLLOW", installer)
        self.assertIn("nitro-control-rollback", installer)
        self.assertIn("verify_copy", installer)

    def test_root_bootstrap_is_frozen_before_consent(self) -> None:
        installer = (ROOT / "install").read_text(encoding="utf-8")
        self.assertIn('exec sudo -- /usr/bin/python3 -I -c "$root_stager"', installer)
        self.assertNotIn('exec sudo -- "$project_dir/install"', installer)
        self.assertIn('"NITRO_INSTALL_SNAPSHOT": "1"', installer)
        self.assertIn("source changed while staging", installer)

    def test_install_rollback_tracks_every_temporary_root_artifact(self) -> None:
        installer = (ROOT / "install").read_text(encoding="utf-8")
        self.assertIn("cleanup_temporary_artifacts", installer)
        self.assertIn("driver_touched=1", installer)
        for variable in ("library_new", "client_new", "service_new", "config_new"):
            self.assertIn(variable, installer)

    def test_uninstall_requires_confirmed_automatic_mode(self) -> None:
        uninstaller = (ROOT / "uninstall").read_text(encoding="utf-8")
        self.assertIn("restore_auto_confirmed ||", uninstaller)
        self.assertIn("system support was NOT removed", uninstaller)
        self.assertIn("Refusing privileged uninstall from a user-writable checkout", uninstaller)
        self.assertIn("found == 1 && failed == 0", uninstaller)


if __name__ == "__main__":
    unittest.main()
