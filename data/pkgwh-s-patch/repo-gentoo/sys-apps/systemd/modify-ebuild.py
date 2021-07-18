#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import glob
import pathlib

try:
    # what to insert (with blank line in the beginning and the end)
    buf2 = """
## patched by fpemud-refsystem ####
# we don't have /etc/fstab so this is uneccessary
find "${D}" -name "*systemd-fstab-generator*" | xargs rm -rf

# we always mount /boot so this is uneccessary
find "${D}" -name "*systemd-efi-boot-generator*" | xargs rm -rf

# we use an "as simple as possible" mount scheme, and all the key mount point are established in initramfs, no automation needed
find "${D}" -name "*systemd-gpt-auto-generator*" | xargs rm -rf

# no automount
find "${D}" -name "*automount*" | xargs rm -rf
ln -sf "../proc-sys-fs-binfmt_misc.mount" "${D}/usr/lib/systemd/system/sysinit.target.wants/proc-sys-fs-binfmt_misc.mount"

# we have no /etc/rc.local
find "${D}" -name "*systemd-rc-local-generator*" | xargs rm -rf

# don't use debug facility of systemd
find "${D}" -name "*systemd-debug-generator*" | xargs rm -rf
find "${D}" -name "*debug-shell*" | xargs rm -rf

# don't use systemd in initrd
find "${D}" -name "*initrd*" | xargs rm -rf
find "${D}" -name "*volatile-root*" | xargs rm -rf
find "${D}" -name "*hibernate-resume*" | xargs rm -rf

# don't use VT console anymore
find "${D}" -name "*vconsole*" | xargs rm -rf
find "${D}" -name "*getty*" | xargs rm -rf
find "${D}" -name "*autovt*" | xargs rm -rf
find "${D}" -name "/etc/systemd/system/getty.target.wants" | xargs rm -rf

# don't use system-update functionality
find "${D}" -name "*system-update*" | xargs rm -rf
find "${D}" -name "*update-done*" | xargs rm -rf

# don't use system-boot functionality
find "${D}" -name "*bootctl*" | xargs rm -rf
find "${D}" -name "*/systemd-boot.7.bz2" | xargs rm -rf
find "${D}" -name "*systemd-boot-system-token*" | xargs rm -rf
find "${D}" -name "*kernel-install*" | xargs rm -rf
find "${D}" -path "/usr/lib/kernel*" | xargs rm -rf

# don't use systemd boot checking functionality
find "${D}" -name "*bless-boot*" | xargs rm -rf
find "${D}" -name "*boot-check-no-failures*" | xargs rm -rf

# don't use systemd-timedated, gentoo eselect is enough
find "${D}" -name "*timedate*" | xargs rm -rf

# don't use systemd-localed, gentoo eselect is enough
find "${D}" -name "*locale1*" | xargs rm -rf
find "${D}" -name "*localed*" | xargs rm -rf
find "${D}" -name "*localectl*" | xargs rm -rf

# don't use systemd-hostnamed, we don't change hostname dynamically
find "${D}" -name "*hostname1*" | xargs rm -rf
find "${D}" -name "*hostnamed*" | xargs rm -rf
find "${D}" -name "*hostnamectl*" | xargs rm -rf

# don't use systemd-networkd
find "${D}" -name "*network*" | xargs rm -rf
find "${D}" -path "/lib/systemd/network*" | xargs rm -rf
find "${D}" -name "/etc/systemd/network" | xargs rm -rf

# don't use systemd-resolvd
find "${D}" -name "*resolv*" | xargs rm -rf

# don't use systemd-machined
find "${D}" -name "*machine*" | xargs rm -rf
find "${D}" -name "*nspawn*" | xargs rm -rf
find "${D}" -name "*detect-virt*" | xargs rm -rf

# don't use systemd-portabled
find "${D}" -name "*portable*" | xargs rm -rf
find "${D}" -name "/lib/systemd/portable" | xargs rm -rf

# don't use systemd-timesyncd, chrony is better
find "${D}" -name "*timesync*" | xargs rm -rf
find "${D}" -name "*ntp*" | xargs rm -rf
find "${D}" -path "/lib/systemd/ntp-units.d*" | xargs rm -rf

# systemd-firstboot should only be executed manually
find "${D}" -name "*systemd-firstboot.service*" | xargs rm -rf

# sysvinit compliance is not needed
find "${D}" -name "*runlevel*" | xargs rm -rf

# install.d is not needed
find "${D}" -path "/usr/lib/kernel/install.d*" | xargs rm -rf

# don't use kexec functionality
find "${D}" -name "*kexec*" | xargs rm -rf

# don't use password framework, polkit is enough, and we don't need password when boot for encrypted HDD
find "${D}" -name "*ask-password*" | xargs rm -rf
find "${D}" -name "*reply-password*" | xargs rm -rf

# no target by default
find "${D}" -name "/etc/systemd/system/multi-user.target.wants" | xargs rm -rf

# it's strange that creation of /srv is in home.conf
sed -i "/\\/srv/d" "${D}/usr/lib/tmpfiles.d/home.conf"

# change 99-sysctl.conf from a symlink to an empty file
/bin/rm -f "${D}/etc/sysctl.d/99-sysctl.conf"
/bin/touch "${D}/etc/sysctl.d/99-sysctl.conf"

# make systemd record journal in memory only, to eliminate disk writes
rm -rf "${D}/var/log/journal"

# files in /var has already been created by /usr/lib/tmpfiles.d/*.conf
rm -rf "${D}/var"

# remove plymouth in emergency.service
sed -i "/plymouth/d" "${D}/lib/systemd/system/emergency.service"

# remove plymouth in rescue.service
sed -i "s/ *plymouth-start\\.service *//g" "${D}/lib/systemd/system/rescue.service"
sed -i "/plymouth/d"                       "${D}/lib/systemd/system/rescue.service"
## end ####"""
    buf2 = buf2.replace("\n", "\n\t")
    buf2 += "\n"

    for fn in glob.glob("*.ebuild"):
        buf = pathlib.Path(fn).read_text()

        # insert to the end of src_install()
        pos = buf.find("multilib_src_install_all() {")
        if pos == -1:
            raise ValueError()
        pos = buf.find("\n}\n", pos)
        if pos == -1:
            raise ValueError()
        pos += 1

        # do insert
        buf = buf[:pos] + buf2 + buf[pos:]
        with open(fn, "w") as f:
            f.write(buf)
except ValueError:
    print("outdated")
