# Changelog

## 1.0.1 - 2026-09-02

- Stage a root-owned, no-follow, digest-verified release snapshot before any
  privileged install reads.
- Verify the exact privileged payload and every installed immutable artifact.
- Add complete install rollback for files, service state, and DKMS state.
- Require confirmed Automatic fan mode before uninstall can remove recovery
  support; preserve support and request Maximum if confirmation fails.
- Remove automatic privileged package-manager invocation; DKMS prerequisites
  are now explicit manual setup.
- Add UI process deadlines, response/output caps, closed model parsing, and
  plain-text rendering.

## 1.0.0 - 2026-08-30

- First public release.
- Omarchy bar widget with live CPU/GPU temperature and fan RPM.
- Automatic, Maximum, and verified 20–100% Manual modes.
- 85°C thermal override that forces Maximum cooling from Manual mode.
- Linked or independent CPU/GPU sliders.
- Performance-profile selector.
- Human-readable settings page and plain-language public documentation.
- Root safety service with exact-UID checks and a 12-second manual watchdog.
- Writable official `acer_wmi` support; external `acer_nitro_ec` is monitoring-only.
- Exact kernel/BIOS-gated Nitro ANV16-71 DKMS fallback.
- Private-by-default compatibility report for new Nitro models.
