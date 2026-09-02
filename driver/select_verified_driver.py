#!/usr/bin/env python3
"""Select a bundled driver only for an exact tested environment."""

from __future__ import annotations

import json
import sys
from pathlib import Path


class EnvironmentNotVerified(RuntimeError):
    pass


def select_driver(
    registry_path: str | Path,
    vendor: str,
    product: str,
    kernel: str,
    bios: str,
) -> str:
    with Path(registry_path).open(encoding="utf-8") as handle:
        registry = json.load(handle)

    for entry in registry.get("models", []):
        if entry.get("vendor") != vendor or entry.get("product") != product:
            continue
        package = str(entry.get("driverPackage", ""))
        if not package:
            return ""
        if kernel not in entry.get("kernelsTested", []):
            raise EnvironmentNotVerified("kernel is not an exact tested match")
        if bios not in entry.get("biosTested", []):
            raise EnvironmentNotVerified("BIOS is not an exact tested match")
        return package
    return ""


def main() -> int:
    if len(sys.argv) != 6:
        print("usage: select_verified_driver.py REGISTRY VENDOR PRODUCT KERNEL BIOS", file=sys.stderr)
        return 2
    try:
        package = select_driver(*sys.argv[1:])
    except EnvironmentNotVerified as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if package:
        print(package)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
