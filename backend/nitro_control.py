#!/usr/bin/env python3
"""Safe Acer Nitro hwmon/platform-profile access and control daemon."""

from __future__ import annotations

import argparse
import grp
import json
import os
import signal
import socket
import struct
import sys
import time
from pathlib import Path
from typing import Any

VERSION = "1.0.1"

MAX_SYSFS_TEXT_BYTES = 4096
MAX_ERROR_CHARS = 512


def bounded_plain_text(value: object, limit: int = MAX_ERROR_CHARS) -> str:
    """Return one bounded line without control or markup-significant characters."""
    text = "".join(
        " " if ord(character) < 32 or 127 <= ord(character) <= 159 else character
        for character in str(value)
    )
    return " ".join(text.split()).replace("<", "").replace(">", "").replace("&", "")[:limit]


class NitroError(RuntimeError):
    pass


class NitroHardware:
    MIN_MANUAL_PERCENT = 20
    MAX_MANUAL_PERCENT = 100
    MAX_MANUAL_TEMPERATURE_C = 85
    MODE_NAMES = {0: "maximum", 1: "manual", 2: "automatic"}
    HWMON_PROVIDERS = {
        "acer": "acer-wmi",
        "acer_nitro_ec": "acer-nitro-ec",
    }
    WRITABLE_HWMON_NAMES = {"acer"}

    def __init__(self, sys_root: str | Path | None = None) -> None:
        self.sys_root = Path(sys_root or os.environ.get("NITRO_SYS_ROOT", "/sys"))

    def _text(self, path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8") as stream:
                value = stream.read(MAX_SYSFS_TEXT_BYTES + 1)
            if len(value) > MAX_SYSFS_TEXT_BYTES:
                return ""
            return bounded_plain_text(value, MAX_SYSFS_TEXT_BYTES)
        except (OSError, UnicodeError):
            return ""

    def _integer(self, path: Path) -> int | None:
        try:
            return int(self._text(path))
        except ValueError:
            return None

    def _write(self, path: Path, value: int | str) -> None:
        try:
            path.write_text(f"{value}\n", encoding="utf-8")
        except OSError as exc:
            raise NitroError(f"could not write {path.name}: {exc.strerror or exc}") from exc

    @property
    def vendor(self) -> str:
        return self._text(self.sys_root / "class/dmi/id/sys_vendor")

    @property
    def model(self) -> str:
        return self._text(self.sys_root / "class/dmi/id/product_name")

    @property
    def bios_version(self) -> str:
        return self._text(self.sys_root / "class/dmi/id/bios_version")

    @property
    def is_nitro(self) -> bool:
        vendor = self.vendor.strip().casefold()
        model = self.model.strip().casefold()
        return vendor == "acer" and (model == "nitro" or model.startswith("nitro "))

    def hwmon_path(self) -> Path | None:
        root = self.sys_root / "class/hwmon"
        candidates: list[Path] = []
        for path in sorted(root.glob("hwmon*")):
            if self._text(path / "name") in self.HWMON_PROVIDERS:
                candidates.append(path)
        if not candidates:
            return None

        # Prefer an official complete writable interface over read-only sensors.
        required = ("pwm1", "pwm2", "pwm1_enable", "pwm2_enable")
        return next(
            (
                path
                for path in candidates
                if self._text(path / "name") in self.WRITABLE_HWMON_NAMES
                and all((path / name).exists() for name in required)
            ),
            next(
                (path for path in candidates if all((path / name).exists() for name in required)),
                candidates[0],
            ),
        )

    def hwmon_name(self, path: Path | None = None) -> str:
        candidate = path or self.hwmon_path()
        return self._text(candidate / "name") if candidate else ""

    def profile_path(self) -> Path | None:
        root = self.sys_root / "class/platform-profile"
        for path in sorted(root.glob("platform-profile-*")):
            if self._text(path / "name") == "acer-wmi":
                return path
        return None

    def _controls(self) -> tuple[Path, list[Path], list[Path]]:
        hwmon = self.hwmon_path()
        if hwmon is None:
            raise NitroError("the Acer hwmon interface is unavailable")
        if self.hwmon_name(hwmon) not in self.WRITABLE_HWMON_NAMES:
            raise NitroError("this hwmon provider is monitoring-only in v1")

        pwm = [hwmon / "pwm1", hwmon / "pwm2"]
        enables = [hwmon / "pwm1_enable", hwmon / "pwm2_enable"]
        if not all(path.exists() for path in pwm + enables):
            raise NitroError("fan RPM is available, but kernel PWM control is unavailable")
        return hwmon, pwm, enables

    @staticmethod
    def _percent_to_pwm(percent: int) -> int:
        return round(percent * 255 / 100)

    @staticmethod
    def _pwm_to_percent(value: int | None) -> int | None:
        return None if value is None else round(value * 100 / 255)

    def status(self) -> dict[str, Any]:
        hwmon = self.hwmon_path()
        profile_dir = self.profile_path()
        result: dict[str, Any] = {
            "version": VERSION,
            "vendor": self.vendor,
            "model": self.model,
            "biosVersion": self.bios_version,
            "isNitro": self.is_nitro,
            "sensorAvailable": hwmon is not None,
            "controlAvailable": False,
            "hwmonName": self.hwmon_name(hwmon),
            "controlProvider": self.HWMON_PROVIDERS.get(self.hwmon_name(hwmon), ""),
            "temperatures": {"cpu": None, "gpu": None, "system": None},
            "fans": {
                "cpu": {"rpm": None, "percent": None},
                "gpu": {"rpm": None, "percent": None},
            },
            "mode": "unavailable",
            "modeCode": None,
            "profile": "",
            "profileChoices": [],
        }

        if hwmon is not None:
            temperatures = [self._integer(hwmon / f"temp{i}_input") for i in range(1, 4)]
            result["temperatures"] = {
                "cpu": None if temperatures[0] is None else round(temperatures[0] / 1000),
                "gpu": None if temperatures[1] is None else round(temperatures[1] / 1000),
                "system": None if temperatures[2] is None else round(temperatures[2] / 1000),
            }
            result["fans"]["cpu"]["rpm"] = self._integer(hwmon / "fan1_input")
            result["fans"]["gpu"]["rpm"] = self._integer(hwmon / "fan2_input")

            required = [hwmon / name for name in ("pwm1", "pwm2", "pwm1_enable", "pwm2_enable")]
            result["controlAvailable"] = (
                self.hwmon_name(hwmon) in self.WRITABLE_HWMON_NAMES
                and all(path.exists() for path in required)
            )
            if result["controlAvailable"]:
                cpu_pwm = self._integer(hwmon / "pwm1")
                gpu_pwm = self._integer(hwmon / "pwm2")
                cpu_mode = self._integer(hwmon / "pwm1_enable")
                gpu_mode = self._integer(hwmon / "pwm2_enable")
                result["fans"]["cpu"]["percent"] = self._pwm_to_percent(cpu_pwm)
                result["fans"]["gpu"]["percent"] = self._pwm_to_percent(gpu_pwm)
                if cpu_mode == gpu_mode and cpu_mode in self.MODE_NAMES:
                    result["modeCode"] = cpu_mode
                    result["mode"] = self.MODE_NAMES[cpu_mode]
                else:
                    result["mode"] = "mixed"

        if profile_dir is not None:
            result["profile"] = self._text(profile_dir / "profile")
            result["profileChoices"] = self._text(profile_dir / "choices").split()

        return result

    def _require_safe_target(self) -> None:
        if not self.is_nitro:
            raise NitroError(
                f"refusing fan writes on unrecognized hardware: {self.vendor or 'unknown'} "
                f"{self.model or 'unknown'}"
            )

    def _write_mode(self, enables: list[Path], mode: int) -> None:
        for path in enables:
            self._write(path, mode)
        values = [self._integer(path) for path in enables]
        if values != [mode, mode]:
            raise NitroError(f"firmware did not accept fan mode {mode}: read back {values}")

    def restore_automatic(self, fallback_to_maximum: bool = True) -> bool:
        """Best-effort fail-safe. Returns True only if both fans confirm auto."""
        if not self.is_nitro:
            return False
        try:
            _, _, enables = self._controls()
        except NitroError:
            return False

        ok = True
        for path in enables:
            try:
                self._write(path, 2)
            except NitroError:
                ok = False
        ok = ok and [self._integer(path) for path in enables] == [2, 2]
        if ok or not fallback_to_maximum:
            return ok

        # Maximum cooling is the safest fallback if firmware auto cannot be restored.
        for path in enables:
            try:
                self._write(path, 0)
            except NitroError:
                pass
        return False

    def set_automatic(self) -> dict[str, Any]:
        self._require_safe_target()
        _, _, enables = self._controls()
        self._write_mode(enables, 2)
        return self.status()

    def set_maximum(self) -> dict[str, Any]:
        self._require_safe_target()
        _, _, enables = self._controls()
        self._write_mode(enables, 0)
        return self.status()

    def set_manual(self, cpu_percent: int, gpu_percent: int) -> dict[str, Any]:
        self._require_safe_target()
        for label, percent in (("CPU", cpu_percent), ("GPU", gpu_percent)):
            if not self.MIN_MANUAL_PERCENT <= percent <= self.MAX_MANUAL_PERCENT:
                raise NitroError(
                    f"{label} manual speed must be {self.MIN_MANUAL_PERCENT}–"
                    f"{self.MAX_MANUAL_PERCENT}%"
                )

        temperatures = self.status()["temperatures"]
        monitored = [
            value
            for value in (temperatures.get("cpu"), temperatures.get("gpu"))
            if isinstance(value, int)
        ]
        if not monitored:
            raise NitroError("manual control requires a working CPU or GPU temperature sensor")
        if max(monitored) >= self.MAX_MANUAL_TEMPERATURE_C:
            raise NitroError(
                f"manual control is blocked at {self.MAX_MANUAL_TEMPERATURE_C}°C or higher"
            )

        _, pwm, enables = self._controls()
        values = [self._percent_to_pwm(cpu_percent), self._percent_to_pwm(gpu_percent)]
        try:
            # Enter maximum first so a partial transition always fails toward cooling.
            self._write_mode(enables, 0)
            for path, value in zip(pwm, values, strict=True):
                self._write(path, value)
            self._write_mode(enables, 1)
            # Some Acer firmware only latches custom values after entering manual mode.
            for path, value in zip(pwm, values, strict=True):
                self._write(path, value)

            modes = [self._integer(path) for path in enables]
            speeds = [self._integer(path) for path in pwm]
            if modes != [1, 1] or speeds != values:
                raise NitroError(f"manual control verification failed: modes={modes}, pwm={speeds}")
        except Exception:
            self.restore_automatic(fallback_to_maximum=True)
            raise
        return self.status()

    def set_profile(self, profile: str) -> dict[str, Any]:
        self._require_safe_target()
        path = self.profile_path()
        if path is None:
            raise NitroError("platform profiles are unavailable")
        choices = self._text(path / "choices").split()
        if profile not in choices:
            raise NitroError(f"unsupported platform profile: {profile}")
        self._write(path / "profile", profile)
        if self._text(path / "profile") != profile:
            raise NitroError(f"firmware did not accept platform profile: {profile}")
        return self.status()


class NitroDaemon:
    MAX_REQUEST_BYTES = 8192
    MAX_RESPONSE_BYTES = 32768
    TOTAL_REQUEST_SECONDS = 3.0

    def __init__(
        self,
        hardware: NitroHardware,
        socket_path: Path,
        access_group: str,
        access_uid: int,
        manual_timeout: int,
    ) -> None:
        self.hardware = hardware
        self.socket_path = socket_path
        self.access_group = access_group
        self.access_uid = access_uid
        self.manual_timeout = max(5, manual_timeout)
        self.manual_deadline: float | None = None
        self.stop_requested = False
        self.server: socket.socket | None = None
        self.group_id = grp.getgrnam(access_group).gr_gid

    def request_stop(self, *_args: object) -> None:
        self.stop_requested = True

    def _peer_allowed(self, conn: socket.socket) -> bool:
        _pid, uid, _gid = struct.unpack(
            "3i", conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )
        return uid in {0, self.access_uid}

    @classmethod
    def _encoded_response(cls, response: dict[str, Any]) -> bytes:
        encoded = json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > cls.MAX_RESPONSE_BYTES:
            return b'{"ok":false,"error":"backend response exceeded safety limit"}\n'
        return encoded

    def _response(self, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request.get("action", "status"))
        if action == "status":
            status = self.hardware.status()
            if request.get("heartbeat") and status.get("mode") == "manual":
                self.manual_deadline = time.monotonic() + self.manual_timeout
        elif action == "automatic":
            status = self.hardware.set_automatic()
            self.manual_deadline = None
        elif action == "maximum":
            status = self.hardware.set_maximum()
            self.manual_deadline = None
        elif action == "manual":
            status = self.hardware.set_manual(int(request["cpu"]), int(request["gpu"]))
            self.manual_deadline = time.monotonic() + self.manual_timeout
        elif action == "profile":
            status = self.hardware.set_profile(str(request["profile"]))
        else:
            raise NitroError(f"unknown action: {action}")
        status.update(
            {
                "ok": True,
                "backend": "ready",
                "manualTimeoutSeconds": self.manual_timeout,
            }
        )
        return status

    def _serve_connection(self, conn: socket.socket) -> None:
        if not self._peer_allowed(conn):
            response = {"ok": False, "error": "permission denied"}
        else:
            try:
                raw = b""
                deadline = time.monotonic() + self.TOTAL_REQUEST_SECONDS
                while b"\n" not in raw and len(raw) <= self.MAX_REQUEST_BYTES:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("request deadline exceeded")
                    conn.settimeout(remaining)
                    chunk = conn.recv(min(2048, self.MAX_REQUEST_BYTES + 1 - len(raw)))
                    if not chunk:
                        break
                    raw += chunk
                if len(raw) > self.MAX_REQUEST_BYTES:
                    raise NitroError("request is too large")
                request = json.loads(raw.decode("utf-8"))
                if not isinstance(request, dict):
                    raise NitroError("request must be a JSON object")
                response = self._response(request)
            except (
                KeyError,
                TypeError,
                ValueError,
                TimeoutError,
                json.JSONDecodeError,
                NitroError,
            ) as exc:
                response = {"ok": False, "error": bounded_plain_text(exc)}
            except Exception as exc:  # keep the safety daemon alive on unexpected input
                print(f"nitro-control: unexpected request failure: {exc}", file=sys.stderr, flush=True)
                response = {"ok": False, "error": "internal backend error"}
        conn.sendall(self._encoded_response(response))

    def _check_watchdog(self) -> None:
        if self.manual_deadline is None:
            return
        status = self.hardware.status()
        if status.get("mode") != "manual":
            self.manual_deadline = None
            return

        temperatures = status.get("temperatures", {})
        monitored = [
            value
            for value in (temperatures.get("cpu"), temperatures.get("gpu"))
            if isinstance(value, int)
        ]
        if not monitored:
            print(
                "nitro-control: temperature sensors unavailable; restoring automatic control",
                flush=True,
            )
            self.hardware.restore_automatic(fallback_to_maximum=True)
            self.manual_deadline = None
            return
        if max(monitored) >= self.hardware.MAX_MANUAL_TEMPERATURE_C:
            print(
                "nitro-control: manual thermal limit reached; forcing maximum cooling",
                flush=True,
            )
            try:
                self.hardware.set_maximum()
            except NitroError:
                self.hardware.restore_automatic(fallback_to_maximum=True)
            self.manual_deadline = None
            return
        if time.monotonic() < self.manual_deadline:
            return
        print("nitro-control: manual heartbeat expired; restoring automatic control", flush=True)
        self.hardware.restore_automatic(fallback_to_maximum=True)
        self.manual_deadline = None

    def run(self) -> int:
        run_dir = self.socket_path.parent
        run_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        os.chown(run_dir, 0, 0)
        os.chmod(run_dir, 0o755)
        if self.socket_path.exists():
            self.socket_path.unlink()

        self.hardware.restore_automatic(fallback_to_maximum=True)
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.socket_path))
        os.chown(self.socket_path, 0, self.group_id)
        os.chmod(self.socket_path, 0o660)
        self.server.listen(8)
        self.server.settimeout(1.0)
        print(
            f"nitro-control: listening on {self.socket_path} for uid {self.access_uid}",
            flush=True,
        )

        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        try:
            while not self.stop_requested:
                self._check_watchdog()
                try:
                    conn, _ = self.server.accept()
                except TimeoutError:
                    continue
                with conn:
                    conn.settimeout(3.0)
                    self._serve_connection(conn)
        finally:
            self.hardware.restore_automatic(fallback_to_maximum=True)
            if self.server is not None:
                self.server.close()
            try:
                self.socket_path.unlink()
            except FileNotFoundError:
                pass
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Acer Nitro fan-control safety daemon")
    parser.add_argument("--socket", default="/run/nitro-control/control.sock")
    parser.add_argument("--group", default="wheel")
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--manual-timeout", type=int, default=12)
    parser.add_argument("--sys-root", default=os.environ.get("NITRO_SYS_ROOT", "/sys"))
    args = parser.parse_args()
    daemon = NitroDaemon(
        NitroHardware(args.sys_root),
        Path(args.socket),
        args.group,
        args.uid,
        args.manual_timeout,
    )
    return daemon.run()


if __name__ == "__main__":
    raise SystemExit(main())
