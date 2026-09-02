# Nitro Control for Omarchy

Fan control for Acer Nitro laptops, directly in the Omarchy bar.

Nitro Control shows CPU/GPU temperature and fan speed. When the laptop and
kernel support it, you can choose Automatic, Maximum, or a manual fan speed.

The safe default is **Automatic**.

## Will it work on my Nitro?

| What your laptop has | What Nitro Control does |
|---|---|
| Official kernel `acer_wmi` PWM controls | Full fan control |
| Tested ANV16-71 kernel/BIOS without PWM | Installs the tested v1 fallback |
| Temperatures and RPM, but no PWM | Shows information; does not write |
| Unknown hardware | Refuses fan writes |

The Nitro AN515-58 is supported by newer upstream Linux kernels. Other Nitro
models also work when their official kernel driver exposes the same standard
PWM interface.
See the [plain-English compatibility guide](docs/compatibility.md) for details.

## Install

1. Add the plugin:

   ```bash
   omarchy plugin add https://github.com/nodramaollama/omarchy-nitro-control.git --enable
   ```

2. Open the fan icon in the Omarchy bar.
3. Select **Install system support** and enter your password once.

No reboot or logout is normally needed.

The root installer first copies an exact, digest-verified release payload into
a root-owned, no-follow snapshot. Privileged installation reads only from that
snapshot. It installs the backend under `/usr/lib/nitro-control`, the
`nitroctl` client under `/usr/bin`, and one systemd service. On the exact tested
ANV16-71 kernel and BIOS only, it may also install the checksummed DKMS
fallback.

DKMS setup is an explicit manual prerequisite. If the installer reports that
DKMS or matching kernel headers are absent, install the named packages with
`omarchy pkg add`, then run **Install system support** again. The plugin never
runs a package manager as root.

## Use

- **Automatic** — Acer firmware controls the fans. Use this normally.
- **Maximum** — both fans run at full speed until you choose another mode.
- **Manual** — choose 20–100%. The linked-fans setting uses one slider.

Right-click the bar icon at any time to return to Automatic.

You can also run:

```bash
nitroctl status
nitroctl automatic
```

## Why it is safe

- The bar widget never runs as root.
- Fan writes go through a small system service.
- Only the exact desktop user chosen during installation may send commands.
- Users cannot replace the service's local socket.
- Manual values below 20% are rejected.
- Manual is blocked at 85°C; an active session reaching 85°C forces Maximum.
- Manual mode needs a heartbeat from the widget.
- If the widget or service stops, the fans return to Automatic.
- Unsupported models remain read-only.
- Every privileged release artifact is bound to `release-manifest.sha256`.
- Installation is transactional: a late failure restores the previous files,
  service state, and DKMS state.
- UI subprocesses have deadlines, bounded output, and plain-text display.

Read [Safety](docs/safety.md) for the full design.

The bundled kernel source has an exact upstream tag, checksums, and a complete
34-line patch in [driver/README.md](driver/README.md).

## Add another Nitro model

Create a private report first:

```bash
~/.config/omarchy/plugins/nitro.control/bin/nitro-report > nitro-report.json
```

The report excludes serial numbers, usernames, hostnames, and network data.
Read it before sharing it, then open an **Unsupported Nitro model** issue.

We only enable a new fallback after testing that exact model. We do not guess
embedded-controller registers from a similar laptop.

## Remove

```bash
~/.config/omarchy/plugins/nitro.control/uninstall
omarchy plugin remove nitro.control
```

The uninstaller returns the fans to Automatic and confirms the hardware state
before removing system support. If that cannot be confirmed, it leaves the
service and driver in place and stops with recovery instructions.

## Verify a release

Release tags are signed. After cloning, verify v1.0.1 and its privileged
payload with:

```bash
git -c gpg.ssh.allowedSignersFile=.github/release-signers verify-tag v1.0.1
sha256sum --check --strict release-manifest.sha256
./install --target-user "$USER" --verify-release
```

## Documentation

- [Compatibility](docs/compatibility.md)
- [Safety](docs/safety.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md)
- [Contributing](CONTRIBUTING.md)

## License

The plugin and backend are MIT licensed. Bundled Linux kernel driver source is
GPL-2.0-or-later. See [driver/README.md](driver/README.md).
