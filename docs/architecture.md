# How Nitro Control is built

There are three small parts:

```text
Omarchy panel (your user)
        |
        | local JSON request
        v
nitro-control service (root)
        |
        | standard Linux files
        v
kernel driver -> Acer firmware
```

## 1. Omarchy panel

The panel displays temperatures, fan RPM, modes, and performance profiles. It
cannot write to hardware by itself.

Panel subprocesses have fixed deadlines and a cleared environment. `nitroctl`
caps daemon input and UI output at 32 KiB. Parsed status is copied into a closed,
size-bounded model rather than exposing arbitrary JSON properties, and all
dynamic strings are rendered as plain text.

## 2. Safety service

The root service accepts commands only from root or the exact Linux user ID
chosen during installation. The socket group lets that user connect, but group
membership alone does not authorize a command. The socket directory is owned
by root, so the desktop user cannot replace the socket.

The service checks that the machine is an Acer Nitro before every hardware
write, including emergency Automatic-mode recovery.

For manual mode it:

1. Moves both fans to Maximum.
2. Writes both requested speeds.
3. Enters Manual mode.
4. Reads everything back to verify it.

If any step fails, it returns to Automatic. Maximum is the last cooling-safe
fallback when Automatic cannot be confirmed.

## Privileged setup transaction

The installer treats the plugin checkout as untrusted after privilege is
granted. It opens the reviewed payload with no-follow directory descriptors,
checks the exact allowlist and immutable release digests, copies it to a
root-owned `/run` snapshot, and performs all privileged reads from there.

All replaced root files, service enablement/activity, and DKMS state are backed
up before mutation. A failure restores that state. Successful installation
rehashes every installed immutable artifact at its final destination. The
installed root-owned uninstaller performs fail-safe hardware restoration before
support is removed; an editable checkout cannot substitute privileged removal
logic.

## 3. Kernel interface

Nitro Control prefers the standard `acer_wmi` hwmon interface supplied by the
running kernel. It can read sensors from an already-installed driver using the
`acer_nitro_ec` hwmon name, but v1 deliberately treats that external raw-EC
provider as monitoring-only.

The bundled DKMS fallback is only selected by an exact entry in
`driver/verified-models.json`. In v1 that writable fallback requires the exact
Nitro ANV16-71 product name, Linux 7.1.9-arch1-2, and BIOS V1.09.

## Manual-mode lease

Manual control lasts only while the panel sends a heartbeat. If no heartbeat
arrives for 12 seconds, the service returns both fans to Automatic. Service
stop, module unload, suspend, and shutdown also restore Automatic.
