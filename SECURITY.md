# Security

Please do not publish a vulnerability that could allow unauthorized hardware
writes or unsafe fan state.

Use GitHub's private vulnerability reporting for this repository. Include the
plugin version, Omarchy version, kernel version, laptop model, and clear steps
to reproduce. Do not include serial numbers or account details.

The trust boundary and fail-safe behavior are documented in
[docs/safety.md](docs/safety.md). Bundled kernel-source provenance is documented
in [driver/acer-wmi-anv16-0.1.0/PROVENANCE.md](driver/acer-wmi-anv16-0.1.0/PROVENANCE.md).

Privileged setup is manual and release-bound. The installer stages a
root-owned, no-follow snapshot and verifies the complete privileged allowlist
against `release-manifest.sha256` before changing the system. It backs up all
replaced root artifacts and rolls them back, together with service and DKMS
state, if any later step fails.

Uninstall refuses to remove the service or driver unless Automatic fan mode is
confirmed first. If Automatic cannot be confirmed, it requests Maximum as the
cooling-safe fallback and preserves the installed recovery path.

For ordinary hardware compatibility, use the public **Unsupported Nitro model**
issue form instead.
