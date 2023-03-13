ARG BASE_IMAGE=localhost/archlinuxarm/rpi-armv7-import:latest

FROM $BASE_IMAGE AS pacman-init
RUN --mount=type=cache,id=pacman,target=/var/cache/pacman/pkg pacman-key --init && pacman-key --populate archlinuxarm && pacman -Syu --noconfirm

FROM pacman-init AS raspi-overlayroot
RUN --mount=type=cache,id=pacman,target=/var/cache/pacman/pkg pacman -S --noconfirm binutils fakeroot
USER nobody
COPY --chown=nobody:nobody raspi-overlayroot /opt/raspi-overlayroot
RUN cd /opt/raspi-overlayroot && makepkg -d

FROM pacman-init
# install overlayroot
RUN sed -i 's/^ *HOOKS=(\(.*\)) *$/HOOKS=(\1 overlayroot)/;s/^ *MODULES=(\(.*\)) *$/MODULES=(\1 overlay)/' /etc/mkinitcpio.conf \
 && sed -i 's/ rw / ro /;s/$/ overlayroot/' /boot/cmdline.txt \
 && sed -i 's/ defaults / defaults,ro /' /etc/fstab
RUN --mount=type=cache,id=pacman,target=/var/cache/pacman/pkg \
    --mount=type=bind,from=raspi-overlayroot,source=/opt/raspi-overlayroot,destination=/opt/raspi-overlayroot \
  pacman -U --noconfirm /opt/raspi-overlayroot/overlayroot-*.pkg.*
# newer systemd renames eth0 into enu1u1.network
COPY enu1u1.network /etc/systemd/network/
# create mnt-mutable.mount
RUN echo '/dev/mmcblk0p3  /mnt/mutable f2fs defaults,noauto 0 0' >> /etc/fstab
# make systemd-timesync almost persistent across reboots
RUN mkdir /var/lib/systemd/timesync \
  && chown systemd-timesync:systemd-timesync /var/lib/systemd/timesync \
  && echo '/mnt/mutable/timesync /var/lib/systemd/timesync none x-systemd.requires=/mnt/mutable,noauto,bind 0 0' >> /etc/fstab
COPY systemd-timesyncd-override.conf /etc/systemd/system/systemd-timesyncd.service.d/override.conf

ENTRYPOINT [ "/bin/bash" ]
WORKDIR /root
