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

That also means the overlay cannot be undone from the running system. To make persistent changes, run `boot-rw`: it strips `ro` and `systemd.volatile=overlay` from the kernel command line, drops the `ro` option from `/boot`'s `/etc/fstab` entry, and reboots, so the system comes back up with `/` and `/boot` both mounted read-write and no overlay. `boot-rw revert` puts all of it back and reboots again. Both directions are idempotent, and either will repair a half-applied state.

Note that `mount -o remount,rw /` is *not* a substitute: `/` is the overlay and already writable, but its writes live in tmpfs and vanish at reboot. For the same reason, anything you install while the overlay is active — `boot-rw` itself included — is gone at the next boot unless written from a `boot-rw` session.

The script leaves in podman the imported base tarball. The import is deterministic, and so is the image hash. The image tag is `localhost/archlinuxarm/rpi:import-"${date}"`, where `${date}` is the timestamp (YYYY-MM-DD) contained in the gzip header of the tarball.

## Power

The stock image runs the CPU at its maximum clock permanently and leaves the onboard radios powered whether or not they are configured. On an idle Pi 4 that measured 100% of the cpufreq ticks at 1.5 GHz; with these changes the same idle board spends ~95% of its ticks at 600 MHz.

The governor is set by [`cpu-governor.conf`](./context/cpu-governor.conf), installed into `/etc/tmpfiles.d`. It cannot be a modprobe option, because cpufreq is built into the kernel and `cpufreq.default_governor=` is a `__setup()` parameter rather than a module parameter — `/sys/module/cpufreq/parameters/default_governor` is read only. Going through `tmpfiles.d` keeps the kernel command line untouched. `systemd-tmpfiles` expands the glob in the path, so a single line covers every core.

The radios are handled in two parts, because they power down differently. Bluetooth needs nothing but an unbound driver: `hci_uart_bcm` owns `BT_REG_ON` through its `shutdown-gpios`, so keeping the module out — [`no-wireless.conf`](./context/no-wireless.conf) in `/etc/modprobe.d` — leaves the core powered down. WiFi does not work that way: unloading `brcmfmac` removes the interface but the SDIO card stays enumerated and the host controller keeps its 250 MHz clock running. Only tearing down the SDIO host runs the `mmc-pwrseq` power-off that deasserts `WL_REG_ON`, which is what [`rpi-wifi-poweroff`](./context/rpi-wifi-poweroff) does from a oneshot unit.

That script finds the host by asking which one enumerated a card of type `SDIO`, rather than by hardcoding an address. The address is board specific — `3f300000.mmc` on the Pi 3 and Zero 2 W, `fe300000.mmc` on the Pi 4 — and on the Pi 4 the SD card shares the `sdhci-iproc` driver with it. Matching on the card type doubles as the safety interlock, since an SD card enumerates as `SD` and eMMC as `MMC`, so the host holding the rootfs can never be selected. Boards with no onboard WiFi, the Pi 2 among them, match nothing and the unit exits having done nothing.

The two images differ in what `config.txt` can reach, which is why none of the above goes through it. On aarch64 `boot.txt` loads Arch's mainline DTB from `/dtbs` and discards the one the firmware fixed up, so `dtoverlay=` and `dtparam=` never reach the kernel — `dtoverlay=disable-wifi` and friends are inert, and `vcgencmd` cannot work either, the mainline kernel having no `vcio` device. The armv7 image boots the downstream `linux-rpi` kernel straight from the firmware and keeps its device tree, so both do work there, and `dtoverlay=disable-wifi`/`disable-bt` would be an alternative to the unit above. What `config.txt` reaches on either image — `core_freq`, `gpu_freq`, `over_voltage` — is the smaller half of the available savings and would need `[pi2]`/`[pi3]`/`[pi4]` sections per board. Gating by mechanism instead keeps one set of files correct for both.

The serial console is dropped alongside the other boot command line edits: `console=` is removed from `cmdline.txt` on armv7 and from `boot.txt`'s bootargs on aarch64, and `enable_uart` is deleted from `config.txt`. That last one also unpins `core_freq`, which the firmware holds fixed while the mini-UART is in use so its baud divisor stays valid. Note this leaves no recovery console.

Ethernet is held at 100 Mbit in the `.link` files, where the existing driver match already gates it per board: the gigabit PHY is a large share of idle draw, and the two `Driver=` lines separate the Pi 4's `bcmgenet` from the USB `lan78xx`/`smsc95xx` of the older boards. It is a no-op on the 100 Mbit-only `smsc95xx` of the Pi 2 and Pi 3 B, and a real saving on the Pi 4 and the gigabit `lan78xx` of the Pi 3 B+. Drop both `BitsPerSecond=` lines to get the full link rate back.

Wake-on-LAN is not available and cannot be made so: `ethtool` reports `Supports Wake-on: d` for `bcmgenet`, the device exposes no `power/wakeup`, and `/sys/power/mem_sleep` offers only `s2idle` — there is no sleep state to wake from to begin with. Energy Efficient Ethernet needs no attention either; it negotiates itself and reports active on gigabit links.

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
