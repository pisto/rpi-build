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

The root partition itself is still mounted read-write, which the overlay makes harmless for your data. It does mean ext4 updates its superblock on each boot and keeps its journal open, so an unclean power cut needs journal recovery on the next boot; adding `ro` to the kernel command line avoids that, at no cost to writability since `/` is the overlay either way.

Anything that must survive a reboot goes on the third partition, mounted at `/mnt/mutable` — currently the journal (bind-mounted onto `/var/log`) and systemd-timesyncd's clock file. That mount is `nofail`, so a missing or unformatted mutable partition does not hold up or fail the boot.

To reach the real SD card from the running system, use `rwrootfs`, which mounts it read-write at `/mnt/root` (`rwrootfs close` when done). Note that `mount -o remount,rw /` does *not* work for this: `/` is the overlay and is already writable, but its writes live in tmpfs and vanish at reboot.

The script leaves in podman the imported base tarball. The import is deterministic, and so is the image hash. The image tag is `localhost/archlinuxarm/rpi:import-"${date}"`, where `${date}` is the timestamp (YYYY-MM-DD) contained in the gzip header of the tarball.

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
