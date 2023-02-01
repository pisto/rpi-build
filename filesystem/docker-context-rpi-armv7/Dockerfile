ARG BASE_IMAGE=localhost/archlinuxarm/rpi-armv7-import:latest

FROM $BASE_IMAGE AS pacman-init
RUN pacman-key --init && pacman-key --populate archlinuxarm && pacman -Sy

FROM pacman-init AS raspi-overlayroot
RUN pacman -S --noconfirm binutils fakeroot
USER nobody
COPY --chown=nobody:nobody raspi-overlayroot /opt/raspi-overlayroot
RUN cd /opt/raspi-overlayroot && makepkg -d

FROM pacman-init
RUN sed -i 's/^ *HOOKS=(\(.*\)) *$/HOOKS=(\1 overlayroot)/;s/^ *MODULES=(\(.*\)) *$/MODULES=(\1 overlay)/' /etc/mkinitcpio.conf \
 && sed -i 's/ rw / ro /;s/$/ overlayroot/' /boot/cmdline.txt \
 && sed -i 's/ defaults / defaults,ro /' /etc/fstab
# 4     -> DHT11
# 12/13 -> MH-Z19 TX/RX
# 18    -> PWM0
RUN sed -i 's/[^ ]*=serial0[^ ]* *//g' /boot/cmdline.txt \
 && echo $'\n[all]\ndhtoverlay=dht11\ndhtoverlay=pwm' >> /boot/config.txt
RUN --mount=type=bind,from=raspi-overlayroot,source=/opt/raspi-overlayroot,destination=/opt/raspi-overlayroot pacman -U --noconfirm /opt/raspi-overlayroot/overlayroot-*.pkg.* && pacman -S --noconfirm podman

ENTRYPOINT [ "/bin/bash" ]
WORKDIR /root
