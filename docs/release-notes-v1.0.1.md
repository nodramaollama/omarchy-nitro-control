# Nitro Control 1.0.1

This security-hardening release addresses the Omarchy marketplace review of
the original v1 submission.

## Security changes

- Privileged installation now operates only on a root-owned, no-follow snapshot
  whose exact allowlist is bound to reviewed SHA-256 digests.
- All installed immutable artifacts are verified at their final destinations.
- Installation backs up and transactionally restores all overwritten files,
  service state, and DKMS state after a late failure.
- Uninstall confirms Automatic fan mode before and after service stop. It
  preserves the recovery path and requests Maximum if Automatic cannot be
  confirmed.
- DKMS and kernel-header package installation is explicitly manual.
- UI commands have deadlines and bounded data; the model is closed and dynamic
  text is rendered as plain text.

The normal hardware safety limits, exact-user authorization, manual-mode lease,
thermal override, and exact hardware gating remain unchanged.
