#!/usr/bin/env python3

from __future__ import annotations

import tempfile
import time
import unittest
import grp
import json
import os
import socket
import struct
from pathlib import Path
from unittest.mock import Mock, patch

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from nitro_control import NitroDaemon, NitroError, NitroHardware  # noqa: E402


class HardwareFixture:
    def __init__(
        self,
        root: Path,
        model: str = "Nitro ANV16-71",
        hwmon_name: str = "acer",
    ) -> None:
        self.root = root
        dmi = root / "class/dmi/id"
        hwmon = root / "class/hwmon/hwmon0"
        profile = root / "class/platform-profile/platform-profile-0"
        dmi.mkdir(parents=True)
        hwmon.mkdir(parents=True)
        profile.mkdir(parents=True)

        self.write(dmi / "sys_vendor", "Acer")
        self.write(dmi / "product_name", model)
        self.write(dmi / "bios_version", "V1.09")
        self.write(hwmon / "name", hwmon_name)
        self.write(hwmon / "temp1_input", "60000")
        self.write(hwmon / "temp2_input", "49000")
        self.write(hwmon / "temp3_input", "42000")
        self.write(hwmon / "fan1_input", "1800")
        self.write(hwmon / "fan2_input", "2400")
        self.write(hwmon / "pwm1", "0")
        self.write(hwmon / "pwm2", "0")
        self.write(hwmon / "pwm1_enable", "2")
        self.write(hwmon / "pwm2_enable", "2")
        self.write(profile / "name", "acer-wmi")
        self.write(profile / "profile", "balanced")
        self.write(profile / "choices", "quiet balanced performance")
        self.hwmon = hwmon
        self.profile = profile

    @staticmethod
    def write(path: Path, value: str) -> None:
        path.write_text(value + "\n", encoding="utf-8")


class NitroHardwareTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = HardwareFixture(self.root)
        self.hardware = NitroHardware(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_status_discovers_sensors_controls_and_profiles(self) -> None:
        status = self.hardware.status()
        self.assertTrue(status["isNitro"])
        self.assertTrue(status["controlAvailable"])
        self.assertEqual(status["temperatures"], {"cpu": 60, "gpu": 49, "system": 42})
        self.assertEqual(status["fans"]["cpu"]["rpm"], 1800)
        self.assertEqual(status["mode"], "automatic")
        self.assertEqual(status["controlProvider"], "acer-wmi")
        self.assertEqual(status["profileChoices"], ["quiet", "balanced", "performance"])

    def test_external_raw_ec_provider_is_monitoring_only(self) -> None:
        HardwareFixture.write(self.fixture.hwmon / "name", "acer_nitro_ec")
        status = self.hardware.status()
        self.assertTrue(status["sensorAvailable"])
        self.assertFalse(status["controlAvailable"])
        self.assertEqual(status["controlProvider"], "acer-nitro-ec")
        with self.assertRaisesRegex(NitroError, "monitoring-only"):
            self.hardware.set_maximum()

    def test_manual_transition_is_verified_and_auto_is_recoverable(self) -> None:
        status = self.hardware.set_manual(35, 55)
        self.assertEqual(status["mode"], "manual")
        self.assertEqual(status["fans"]["cpu"]["percent"], 35)
        self.assertEqual(status["fans"]["gpu"]["percent"], 55)
        status = self.hardware.set_automatic()
        self.assertEqual(status["mode"], "automatic")

    def test_manual_speed_below_safety_floor_is_rejected(self) -> None:
        with self.assertRaisesRegex(NitroError, "20–100%"):
            self.hardware.set_manual(10, 50)
        self.assertEqual(self.hardware.status()["mode"], "automatic")

    def test_manual_mode_is_rejected_at_thermal_limit(self) -> None:
        HardwareFixture.write(self.fixture.hwmon / "temp1_input", "85000")
        with self.assertRaisesRegex(NitroError, "85°C"):
            self.hardware.set_manual(40, 40)
        self.assertEqual(self.hardware.status()["mode"], "automatic")

    def test_writes_are_rejected_on_non_nitro_hardware(self) -> None:
        HardwareFixture.write(self.root / "class/dmi/id/product_name", "Aspire Test")
        with self.assertRaisesRegex(NitroError, "unrecognized hardware"):
            self.hardware.set_maximum()

    def test_lookalike_dmi_names_are_not_trusted(self) -> None:
        HardwareFixture.write(self.root / "class/dmi/id/sys_vendor", "NotAcer")
        self.assertFalse(self.hardware.is_nitro)
        HardwareFixture.write(self.root / "class/dmi/id/sys_vendor", "Acer")
        HardwareFixture.write(self.root / "class/dmi/id/product_name", "Nitrogen Test")
        self.assertFalse(self.hardware.is_nitro)

    def test_restore_automatic_never_writes_on_non_nitro_hardware(self) -> None:
        HardwareFixture.write(self.root / "class/dmi/id/product_name", "Aspire Test")
        HardwareFixture.write(self.fixture.hwmon / "pwm1_enable", "1")
        HardwareFixture.write(self.fixture.hwmon / "pwm2_enable", "1")
        self.assertFalse(self.hardware.restore_automatic())
        self.assertEqual((self.fixture.hwmon / "pwm1_enable").read_text().strip(), "1")
        self.assertEqual((self.fixture.hwmon / "pwm2_enable").read_text().strip(), "1")

    def test_profile_choice_is_validated(self) -> None:
        self.hardware.set_profile("quiet")
        self.assertEqual(self.hardware.status()["profile"], "quiet")
        with self.assertRaisesRegex(NitroError, "unsupported platform profile"):
            self.hardware.set_profile("turbo")


class NitroWatchdogTests(unittest.TestCase):
    def test_expired_manual_session_restores_automatic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            HardwareFixture(root)
            hardware = NitroHardware(root)
            group_name = grp.getgrgid(os.getgid()).gr_name
            daemon = NitroDaemon(hardware, root / "run/control.sock", group_name, 1000, 5)
            response = daemon._response({"action": "manual", "cpu": 40, "gpu": 40})
            self.assertTrue(response["ok"])
            daemon.manual_deadline = time.monotonic() - 1
            daemon._check_watchdog()
            self.assertEqual(hardware.status()["mode"], "automatic")
            self.assertIsNone(daemon.manual_deadline)

    def test_hot_manual_session_forces_maximum_cooling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = HardwareFixture(root)
            hardware = NitroHardware(root)
            group_name = grp.getgrgid(os.getgid()).gr_name
            daemon = NitroDaemon(hardware, root / "run/control.sock", group_name, 1000, 12)
            daemon._response({"action": "manual", "cpu": 40, "gpu": 40})
            HardwareFixture.write(fixture.hwmon / "temp1_input", "86000")
            daemon._check_watchdog()
            self.assertEqual(hardware.status()["mode"], "maximum")
            self.assertIsNone(daemon.manual_deadline)


class NitroPeerAuthenticationTests(unittest.TestCase):
    def test_only_root_and_the_configured_uid_are_accepted(self) -> None:
        access_uid = 4242
        group_name = grp.getgrgid(os.getgid()).gr_name
        daemon = NitroDaemon(
            Mock(), Path("/tmp/not-used.sock"), group_name, access_uid, 12
        )
        connection = Mock(spec=socket.socket)

        for uid, expected in ((0, True), (access_uid, True), (4243, False)):
            connection.getsockopt.return_value = struct.pack("3i", 123, uid, os.getgid())
            self.assertEqual(daemon._peer_allowed(connection), expected)


class NitroProtocolBoundsTests(unittest.TestCase):
    def test_response_is_capped_even_if_hardware_data_is_hostile(self) -> None:
        response = NitroDaemon._encoded_response(
            {"model": "x" * (NitroDaemon.MAX_RESPONSE_BYTES * 2)}
        )
        self.assertLessEqual(len(response), NitroDaemon.MAX_RESPONSE_BYTES)
        self.assertEqual(
            response,
            b'{"ok":false,"error":"backend response exceeded safety limit"}\n',
        )

    def test_incomplete_request_has_a_total_deadline(self) -> None:
        group_name = grp.getgrgid(os.getgid()).gr_name
        daemon = NitroDaemon(
            Mock(), Path("/tmp/not-used.sock"), group_name, os.getuid(), 12
        )
        daemon.TOTAL_REQUEST_SECONDS = 0.01
        daemon._peer_allowed = Mock(return_value=True)
        connection = Mock(spec=socket.socket)
        connection.recv.return_value = b"x"
        with patch("nitro_control.time.monotonic", side_effect=[0.0, 0.005, 0.02]):
            daemon._serve_connection(connection)
        response = json.loads(connection.sendall.call_args.args[0])
        self.assertFalse(response["ok"])
        self.assertIn("deadline", response["error"])


if __name__ == "__main__":
    unittest.main()
