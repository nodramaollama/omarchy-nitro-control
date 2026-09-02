# Safety

Fan control can affect hardware cooling. Nitro Control uses several independent
guards so one UI mistake cannot leave a laptop at a low fixed speed.

## Safe defaults

- Startup mode is Automatic.
- Service stop restores Automatic.
- Manual speeds must be between 20% and 100%.
- Manual is blocked at 85°C; reaching 85°C in Manual forces Maximum cooling.
- Unsupported Acer models are read-only.
- Non-Acer and non-Nitro computers are rejected.

## Manual mode

Manual mode is a 12-second lease. The Omarchy widget renews it every four
seconds. If the widget freezes, closes unexpectedly, or loses the backend, the
lease expires and Acer firmware takes control again.

The service enters Manual mode in a cooling-safe order: Maximum first, then
both speed values, then Manual, followed by readback verification.

Manual control also requires a working CPU or GPU temperature sensor. If the
sensor disappears, the service restores Automatic. If CPU or GPU reaches 85°C,
the service leaves Manual and forces Maximum cooling.

## Permissions

The QML panel is unprivileged. A small root system service owns the hardware
writes. Its Unix socket is `root:<desktop-group>` with mode `0660`; its parent
directory is `root:root` with mode `0755`, so the user cannot replace it.

For every connection, Linux supplies the caller's real process credentials.
The backend accepts root or the exact numeric user ID recorded during install.
Being in the socket group is not enough to authorize a command.

## Privileged installation

The checkout belongs to the desktop user and is never a privileged execution
root. After consent, the installer opens an exact allowlist with no-follow
file-descriptor traversal, verifies every digest in `release-manifest.sha256`,
and copies it to a new root-owned directory under `/run`. Root installation is
re-executed from that immutable snapshot with a cleared environment.

Before replacing anything, installation records every root artifact plus the
service and DKMS state. A failure after that point removes new artifacts and
restores the complete previous state. Final verification hashes every installed
immutable file at its destination before the service is enabled.

Package installation is deliberately outside this transaction. Missing DKMS
or kernel headers are reported as manual prerequisites; the plugin does not run
a package manager.

## Driver fallback

The installer always prefers the running kernel. The v1 bundled driver is
installed only for the exact tested model, kernel, and BIOS in the verified
registry. Its files are checksum-verified before DKMS sees them. The complete
patch and upstream Linux source identity are included in the repository.

The fallback restores Automatic during unload, suspend, and shutdown. Unknown
models stay read-only; Nitro Control never guesses raw embedded-controller
addresses. An external `acer_nitro_ec` provider is accepted for readings only,
never fan writes.

Uninstall requests and directly reads back Automatic mode before stopping the
service, checks it again after stop, and does not remove the service or driver
if either check fails. Maximum is requested as the cooling-safe fallback while
the recovery path remains installed.

## UI data boundaries

Widget commands run with a fixed environment and short deadlines. The client
caps the complete daemon response and printed output at 32 KiB, accepts exactly
one JSON line, and reports control-free plain text. The model accepts only its
explicit schema with bounded strings, lists, and numbers; dynamic QML text is
rendered as plain text.

## Emergency recovery

First try:

```bash
nitroctl automatic
```

If the client is unavailable, stop the service:

```bash
sudo systemctl stop nitro-control
```

Stopping the service also requests Automatic mode.
