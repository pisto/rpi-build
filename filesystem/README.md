# Memorycard initialization

This folder contains the Raspberry Pi SD card initialization. The image is based on [Arch Linux ARM](https://archlinuxarm.org/), plus [raspi-overlayroot](https://github.com/nils-werner/raspi-overlayroot).

## Requirements

```
qemu-user-static-arm  # may be qemu-user-static in some distro
podman
sudo
wget
```

The image build script uses podman, but regular Docker versions may work.

Make sure to initialize ad update the raspi-overlay git submodule:
```bash
git submodule update --init
```

## Building the base image

The build script [`build-rpi-armv7`](./build-rpi-armv7) creates the image `localhost/archlinuxarm/rpi-armv7:latest` in podman. The base of the image is the tarball of the Arch Linux ARM project for Raspberry Pi devices, which defaults to [http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-armv7-latest.tar.gz](http://os.archlinuxarm.org/os/). You can control the address of the tarball with the `AARCH_URL` environment variable.

The build is bound to a specific hash of the tarball. The build script will fail if the downloaded tarball md5 hash does not match [ArchLinuxARM-rpi-armv7-latest.tar.gz.md5](./ArchLinuxARM-rpi-armv7-latest.tar.gz.md5), which might happen if you run this script in the future. If you intend to run update the base tarball, first replace the md5 checksum file:
```bash
wget -O ArchLinuxARM-rpi-armv7-latest.tar.gz.md5 http://os.archlinuxarm.org/os/ArchLinuxARM-rpi-armv7-latest.tar.gz.md5
# possibly commit it
```

The image runs with a read-only root filesystem, with a writable in-memory overlay (see project [raspi-overlayroot](https://github.com/nils-werner/raspi-overlayroot) for details).

The script leaves in podman the imported base tarball. The import is deterministic, and so is the image hash. The image tag is `localhost/archlinuxarm/rpi-armv7-import:"${date}"`, where `${date}` is the timestamp (YYYY-MM-DD) contained in the gzip header of the tarball.

## Copying to a SD card

Your SD card device should be defined with the `MEMORY_CARD_DEVICE` environment variable:
```bash
export MEMORY_CARD_DEVICE=/dev/mmcblk0
```
The [`sd-format`](./sd-format), [`sd-mount`](./sd-mount), [`sd-umount`](./sd-umount) scripts make use of this variable to reference the memory card.

Use the `sd-format` script **ERASES ALL CONTENT** of your memory card and replaces it with the content of the image `localhost/archlinuxarm/rpi-armv7:latest`, with the proper 2-partitions layout for Raspberry Pi devices. It will delete and lock the password for the root and alarm user, and initialize the machine-id and ssh host keys. If you have the public part of your ssh key in the standard path (`~/.ssh/id_rsa.pub`), it will use it to allow you to login to the device.

Use the `sd-mount` script to mount your memory card in the `mounts/${device}` directory. Use the `sd-umount` script to unmount (and flush) the device.

## Modifying the SD card installation

Use the [`sd-exec`](./sd-exec) script to login as root inside the mounted SD partitions. You can perform for example updates in this way.
