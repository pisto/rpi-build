# Memorycard initialization

This folder contains the Raspberry Pi SD card initialization. The image is based on [Arch Linux ARM](https://archlinuxarm.org/).

## Requirements

```
qemu-user-static-arm  # may be qemu-user-static in some distro
podman
sudo
wget
```

## Building the base image

The build script [`build-rpi`](./build-rpi) creates the image `localhost/archlinuxarm/rpi:latest` in podman. It requires the `RPI_ARCH` environment variable to be set to either `armv7` or `aarch64` (there is no default). The base of the image is the tarball of the Arch Linux ARM project for Raspberry Pi devices, which defaults to `http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-${RPI_ARCH}-latest.tar.gz`. You can control the address of the tarball with the `AARCH_URL` environment variable.

The build script tags the base import image and the build image with `import-$date` and `latest` for the final build. Arguments `--os linux` and `--arch` are set accordingly to `RPI_ARCH` with proper formatting (`arm/v7` and `arm64`), make sure you specify these arguments in pull or build commands.

The build is bound to a specific hash of the tarball. The build script will fail if the downloaded tarball md5 hash does not match [ArchLinuxARM-rpi-armv7-latest.tar.gz.md5](./ArchLinuxARM-rpi-armv7-latest.tar.gz.md5), which might happen if you run this script in the future. If you intend to run update the base tarball, first replace the md5 checksum file:
```bash
wget -O ArchLinuxARM-rpi-armv7-latest.tar.gz.md5 http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-armv7-latest.tar.gz.md5
# possibly commit it
```

The image runs the root filesystem under a writable in-memory overlay, so every change to `/` is discarded at reboot and none of it reaches the SD card — overlayfs never writes to its lower layer. This is systemd's own `systemd.volatile=overlay`, set up in the initramfs by `systemd-volatile-root` (mkinitcpio's `sd-volatile` hook).

The root partition is additionally mounted `ro`. That is not what protects your data — the overlay already does — but it stops ext4's own writes: mounted read-write, the driver updates the superblock on every boot and keeps its journal open, so an unclean power cut needs journal recovery on the next boot. It costs nothing, since `/` is the writable overlay either way.

The lower layer is mounted inside the initramfs, which is torn down at switch-root, so it does not appear in `/proc/mounts` at all — `mount` only shows `/` as `overlay`, with a `lowerdir=/sysroot` that no longer resolves. To check its state, read the first line of `/proc/fs/ext4/mmcblk0p2/options`, which reports `rw` or `ro`.

Anything that must survive a reboot goes on the third partition, mounted at `/mnt/mutable` — currently the journal (bind-mounted onto `/var/log`) and systemd-timesyncd's clock file. That mount is `nofail`, so a missing or unformatted mutable partition does not hold up or fail the boot.

That also means the overlay cannot be undone from the running system. To make persistent changes, run `boot-rw`: it strips `ro` and `systemd.volatile=overlay` from the kernel command line and reboots, so the system comes back up with `/` mounted read-write and no overlay. `/boot` is left alone — it stays `ro` in `/etc/fstab`, but vfat has no recovery state to corrupt and `mount -o remount,rw /boot` works at any time, so it never needed a reboot. `boot-rw revert` puts all of it back and reboots again. Both directions are idempotent, and either will repair a half-applied state.

Note that `mount -o remount,rw /` is *not* a substitute: `/` is the overlay and already writable, but its writes live in tmpfs and vanish at reboot. For the same reason, anything you install while the overlay is active — `boot-rw` itself included — is gone at the next boot unless written from a `boot-rw` session.

The script leaves in podman the imported base tarball. The import is deterministic, and so is the image hash. The image tag is `localhost/archlinuxarm/rpi:import-"${date}"`, where `${date}` is the timestamp (YYYY-MM-DD) contained in the gzip header of the tarball.

## Power

The stock image runs the CPU at its maximum clock permanently and leaves the onboard radios powered whether or not they are configured. On an idle Pi 4 that measured 100% of the cpufreq ticks at 1.5 GHz; with these changes the same idle board spends ~95% of its ticks at 600 MHz.

The governor is set by [`cpu-governor.conf`](./context/cpu-governor.conf), installed into `/etc/tmpfiles.d`. It cannot be a modprobe option, because cpufreq is built into the kernel and `cpufreq.default_governor=` is a `__setup()` parameter rather than a module parameter — `/sys/module/cpufreq/parameters/default_governor` is read only. Going through `tmpfiles.d` keeps the kernel command line untouched. `systemd-tmpfiles` expands the glob in the path, so a single line covers every core.

The radios are handled in two parts, because they power down differently. Bluetooth needs nothing but an unbound driver: `hci_uart_bcm` owns `BT_REG_ON` through its `shutdown-gpios`, so keeping the module out — [`no-wireless.conf`](./context/no-wireless.conf) in `/etc/modprobe.d` — leaves the core powered down. WiFi does not work that way: unloading `brcmfmac` removes the interface but the SDIO card stays enumerated and the host controller keeps its 250 MHz clock running. Only tearing down the SDIO host runs the `mmc-pwrseq` power-off that deasserts `WL_REG_ON`, which is what [`rpi-wifi-poweroff`](./context/rpi-wifi-poweroff) does from a oneshot unit.

That script finds the host by asking which one enumerated a card of type `SDIO`, rather than by hardcoding an address. The address is board specific — `3f300000.mmc` on the Pi 3 and Zero 2 W, `fe300000.mmc` on the Pi 4 — and on the Pi 4 the SD card shares the `sdhci-iproc` driver with it. Matching on the card type doubles as the safety interlock, since an SD card enumerates as `SD` and eMMC as `MMC`, so the host holding the rootfs can never be selected. Boards with no onboard WiFi, the Pi 2 among them, match nothing and the unit exits having done nothing.

The two images differ in what `config.txt` can reach, which is why none of the above goes through it. On aarch64 `boot.txt` loads Arch's mainline DTB from `/dtbs` and discards the one the firmware fixed up, so `dtoverlay=` and `dtparam=` never reach the kernel — `dtoverlay=disable-wifi` and friends are inert, and `vcgencmd` cannot work either, the mainline kernel having no `vcio` device. The armv7 image boots the downstream `linux-rpi` kernel straight from the firmware and keeps its device tree, so both do work there, and `dtoverlay=disable-wifi`/`disable-bt` would be an alternative to the unit above. What `config.txt` reaches on either image — `core_freq`, `gpu_freq`, `over_voltage` — is the smaller half of the available savings, and needs a per-board section wherever the stock value differs. Everything that can be gated by mechanism instead is, which keeps one set of files correct for both.

The one `config.txt` change is `core_freq=250`, in a `[pi4]` section. The Pi 4 runs its VideoCore core at 500 MHz, and `enable_uart=1` normally pins it there so the mini-UART's baud divisor stays valid — but naming `core_freq` explicitly overrides that pin, and the firmware recomputes the divisor for the value given. Measured on an idle Pi 4B rev 1.1, 100 s quiet: 55.5 °C at 500 MHz against 53.6 °C at 250 MHz, with raw SD reads falling from 41.9 MB/s to about 40. Roughly 2 K for 5% of sequential SD throughput. The section gate matters because the stock value is not the same everywhere: the Pi 2 already runs its core at 250, and the Pi 3's 400 is untested here.

Nothing else in the clock tree moves with it, which is what makes this safe. The mini-UART is the only peripheral on the SoC whose divisor is computed once at boot from `core_freq` and then silently goes wrong when it changes: `serial@7e215040` takes its clock through `aux@7e215000` from `<&cprman 0x14>`, `BCM2835_CLOCK_VPU`. The SD host is on its own `BCM2711_CLOCK_EMMC2` divider, the SDIO host on `BCM2835_CLOCK_EMMC`, the OTG port on a fixed 480 MHz, and the VL805 USB3 controller has no `clocks` property at all — it runs off the PCIe reference. All four were confirmed unchanged across a 2:1 core change on real hardware. I²C, SPI and PWM *do* derive from the core clock, so their baud rates shift with it; that is only a concern if something is wired to the header.

Do not remove `enable_uart=1` to save the UART. Dropping it does not merely disable the console: U-Boot takes its own console from the firmware's `/chosen/stdout-path`, which is `serial0` — the mini-UART — and with the clock unpinned it hangs on its first write, before `boot.scr` runs at all. The board then does not boot, with nothing logged anywhere, and recovery means editing `config.txt` with the card in a reader. This was confirmed by instrumenting `boot.txt` with network beacons: with `enable_uart=1` all five fired within four seconds, with `enable_uart=0` none did, and the firmware device tree U-Boot dumps on the way past was left untouched.

Ethernet is held at 100 Mbit in the `.link` files, where the existing driver match already gates it per board: the gigabit PHY is a large share of idle draw, and the two `Driver=` lines separate the Pi 4's `bcmgenet` from the USB `lan78xx`/`smsc95xx` of the older boards. It is a no-op on the 100 Mbit-only `smsc95xx` of the Pi 2 and Pi 3 B. On the Pi 4 it measured 2.5 K of idle temperature, about as much as halving `core_freq`, and it costs only bandwidth.

It has to be done with `Advertise=`, not `BitsPerSecond=`. Forcing a fixed speed asks the driver to turn autonegotiation off, which `bcmgenet` rejects — `eth0: Could not set speed to 100Mbps, ignoring: Invalid argument`, logged at warning level while the link quietly stays at 1 Gbit. Restricting what autonegotiation is allowed to offer gets there instead, and keeps EEE negotiated and active, which forcing the speed would have given up.

That still is not enough on its own. `bcmgenet` attaches its PHY in `ndo_open`, long after udev has run `net_setup_link` at device-add, so `Advertise=` fails there too — `Could not set advertise mode, ignoring: Invalid argument` — and the link comes up at 1 Gbit anyway. [`rpi-link-advertise.service`](./context/rpi-link-advertise.service) re-triggers the net subsystem once `network-online.target` is reached, at which point the setting takes and the link renegotiates to 100 Mbit. It matches no interface by name, so it is correct on every board; the `.link` files still decide what actually gets advertised. Drop both `Advertise=` lines to get the full link rate back.

Wake-on-LAN is not available and cannot be made so: `ethtool` reports `Supports Wake-on: d` for `bcmgenet`, the device exposes no `power/wakeup`, and `/sys/power/mem_sleep` offers only `s2idle` — there is no sleep state to wake from to begin with. Energy Efficient Ethernet needs no attention either; it negotiates itself and reports active on gigabit links.

## Minecraft servers

Each server account is provisioned live with `mc-provision-user <username>
<port>` (installed at `/usr/local/bin`), run against the running Pi rather
than from the `Containerfile` — it needs the external SSD (`/dev/sda4`,
mounted at `/srv/minecraft` via the `nofail` line this image adds to
`/etc/fstab`) actually attached, which a podman build doesn't have. It
creates the Linux account, a per-user systemd `--user` unit modelled on a
plain `java -jar server.jar` (G1GC, `-Xmx1024M`, no JMX, no RCON — the only
way to stop one account reaching another's admin interface over loopback,
since Linux has no per-UID ACL on `localhost`, is to not run one at all),
enables lingering so it starts at boot with no login required, and fetches
the current latest vanilla server jar. It's idempotent, so it doubles as the
way to add another account later.

All accounts share one budget rather than each getting a fixed slice:
`minecraft.slice` caps their *combined* memory at 80% of the Pi's RAM
(`MemoryHigh=70%` as an earlier throttle point), and gives them low
`CPUWeight`/`IOWeight` against the rest of the system. `mc-provision-user`
reparents each account's `user@<uid>.service` into that slice with a
`Slice=` drop-in — that key is freely overridable on a *service* (only a
`.slice` unit's own name fixes its place in the hierarchy), so this moves
the account's whole session tree out of its default `user-<uid>.slice` and
into the shared one. `systemd-oomd` (enabled by this image, off by default)
is told to act on that slice under sustained memory pressure
(`ManagedOOMMemoryPressure=kill`), so a Minecraft process gets killed before
the kernel's own OOM killer would otherwise have to pick something on the
whole system. The slice does not cap swap usage — on a box with a swap
device this lets a JVM spike ride out a squeeze on swap rather than being
killed outright, at the cost of a GC/latency hit while it's happening.
`vm.swappiness` is turned down to `10` (from the kernel default of `60`) via
`99-swappiness.conf`, so the kernel reaches for page cache before swapping
out active memory — a no-op if a given board has no swap at all, so it's
part of the base image rather than something bolted on only where a swap
partition exists. Each server's home directory lives on the volatile overlay
root like the rest of `/home`; only `~/minecraft` (bind-mounted from
`/srv/minecraft/<user>` on the SSD) is exempt and actually persists, the
same pattern already used for `/var/log` above.

GC is G1, not the `ZGC` a hand-run desktop instance might use elsewhere:
at a 1G heap, ZGC's and Shenandoah's fixed per-region overhead is a much
bigger fraction of the heap than it would be at multi-GB sizes, and G1 is
the community-proven choice for small Minecraft heaps. It's still a
concurrent collector (only evacuation pauses are stop-the-world). There is
no live-adjustable "soft" heap target under G1 — `-XX:SoftMaxHeapSize` is
Generational-ZGC-only, and nothing in the kernel/cgroup/systemd stack pushes
memory pressure into a JVM that isn't explicitly polling for it — so the
heap doesn't shrink in response to system-wide pressure the way the slice
above does; it only uncommits unused regions back to the OS once live usage
drops well below capacity, which is usage- rather than pressure-driven. No
`-XX:+UseNUMA`: this board has no NUMA nodes, real or otherwise
(`/sys/devices/system/node/` doesn't exist), so the flag would be a silent
no-op.

The SSD's own power management was audited, not changed: it already has
USB/PCIe autosuspend disabled (`power/control=on`) at every level between
it and the VL805 controller, and PCIe ASPM is at the untouched firmware
default. Neither is a hand-set override — `60-autosuspend.rules` only
opts a device into autosuspend when the hwdb explicitly lists it as safe,
and forcing ASPM L1 states on the Pi 4's internal Broadcom-to-VL805 link is
a known source of USB3 instability — so both are already at the correct
setting for a drive holding live world-save data, and are left alone.

## Dynamic DNS

`ddclient` and `libnatpmp` (for `natpmpc`) are installed by the image, along
with `ddclient-natpmp-ip` at `/usr/local/bin` — everything else (the actual
`/etc/ddclient/ddclient.conf`, which account/hostname/password it updates,
and which LAN it's allowed to run on) is instance-specific and configured
live, not baked in here.

`ddclient-natpmp-ip` is what `ddclient.conf` points `usev4=cmdv4` at instead
of a web-based IP lookup: it runs `natpmpc` and extracts only its `Public IP
address : ...` line — `natpmpc`'s own stdout also has diagnostic lines like
`using gateway : 10.0.0.1` that contain IP-looking substrings that are *not*
the public address, so handing ddclient the raw output to parse itself would
risk it grabbing the wrong one. It also gates on the current default gateway
(`EXPECTED_GATEWAY`, and optionally its ARP MAC via `EXPECTED_GATEWAY_MAC` —
set through a `ddclient.service.d` drop-in) before ever calling `natpmpc`,
and prints nothing on any failure. That matters on a board that moves
between networks: a home router's default gateway IP (`192.168.1.1` and
similar) is common enough that IP alone doesn't prove which physical network
you're on, and there is deliberately no fallback IP source — if the gateway
doesn't match, or `natpmpc`'s target isn't actually NAT-PMP-capable, ddclient
gets no address and skips that update rather than registering a wrong one.

## Copying to a SD card

Your SD card device should be defined with the `MEMORY_CARD_DEVICE` environment variable:
```bash
export MEMORY_CARD_DEVICE=/dev/mmcblk0
```
The [`sd-format`](./sd-format), [`sd-mount`](./sd-mount), [`sd-umount`](./sd-umount) scripts make use of this variable to reference the memory card.

Use the `sd-format` script **ERASES ALL CONTENT** of your memory card and replaces it with the content of the image `localhost/archlinuxarm/rpi:latest`, with the proper 2-partitions layout for Raspberry Pi devices. It will delete and lock the password for the root and alarm user, and initialize the machine-id and ssh host keys. If you have the public part of your ssh key in the standard path (`~/.ssh/id_rsa.pub`), it will use it to allow you to login to the device.

Use the `sd-mount` script to mount your memory card in the `mounts/${device}` directory. Use the `sd-umount` script to unmount (and flush) the device.

## Modifying the SD card installation

Use the [`sd-exec`](./sd-exec) script to login as root inside the mounted SD partitions. You can perform for example updates in this way.
