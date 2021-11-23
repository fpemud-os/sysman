#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import gzip
import time
import glob
import shutil
import subprocess
import strict_hdds


class Main:

    def main(self):
        if os.getuid() != 0:
            print("You must run this command as root!")
            return 1

        # another instance is running?
        pass

        # /mnt/gentoo or /mnt/gentoo/boot is mounted
        if _Util.isMountPoint("/mnt/gentoo"):
            print("Error: /mnt/gentoo should not be mounted")
            return 1
        if _Util.isMountPoint("/mnt/gentoo/boot"):
            print("Error: /mnt/gentoo/boot should not be mounted")
            return 1

        # get storage layout for target system
        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Error: Invalid storage layout.")
            return 1

        if layout.name == "bios-ext4":
            bootDev = None
        elif layout.name in ["efi-ext4", "efi-bcache-lvm-ext4"]:
            bootDev = layout.get_esp()
        else:
            assert False

        # mount directories (layer 1)
        mountList = [
            ("/mnt/gentoo", "%s /mnt/gentoo" % (layout.dev_rootfs)),
        ]
        with _DirListMount(mountList):
            if not _Util.isGentooRootDir("/mnt/gentoo"):
                print("Error: Invalid content in root device %s" % (layout.dev_rootfs))
                return 1

            # mount directories (layer 2)
            mountList = [
                ("/mnt/gentoo/proc", "-t proc -o nosuid,noexec,nodev proc /mnt/gentoo/proc"),
                ("/mnt/gentoo/sys", "--rbind /sys /mnt/gentoo/sys", "--make-rslave /mnt/gentoo/sys"),
                ("/mnt/gentoo/dev", "--rbind /dev /mnt/gentoo/dev", "--make-rslave /mnt/gentoo/dev"),
                ("/mnt/gentoo/run", "--bind /run /mnt/gentoo/run"),
                ("/mnt/gentoo/tmp", "-t tmpfs -o mode=1777,strictatime,nodev,nosuid tmpfs /mnt/gentoo/tmp"),
            ]
            # if os.path.exists("/sys/firmware/efi/efivars"):
            #     mountList += [
            #         ("/mnt/gentoo/sys/firmware/efi/efivars", "-t efivarfs -o nosuid,noexec,nodev /mnt/gentoo/sys/firmware/efi/efivars"),
            #     ]
            if bootDev is not None:
                mountList += [
                    ("/mnt/gentoo/boot", "%s /mnt/gentoo/boot" % (bootDev)),
                ]
            with _DirListMount(mountList):
                os.makedirs("/mnt/gentoo/run/udev", exist_ok=True)

                # mount directories (layer 3)
                mountList = [
                    ("/mnt/gentoo/run/udev", "--rbind /run/udev /mnt/gentoo/run/udev", "--make-rslave /mnt/gentoo/run/udev"),
                ]
                with _DirListMount(mountList):
                    # do real work
                    with _FakeUsrSrcLinuxDirectory(prefix="/mnt/gentoo"):
                        with _CopyResolvConf("/etc/resolv.conf", "/mnt/gentoo"):
                            subprocess.run("FPEMUD_OS_SETUP=1 /usr/bin/chroot /mnt/gentoo /bin/sh", shell=True)

        return 0


class _DirListMount:

    def __init__(self, mountList):
        self.okList = []
        for item in mountList:      # mountList = (directory, mount-commad-1, mount-command-2, ...)
            dir = item[0]
            if not os.path.exists(dir):
                os.makedirs(dir)
            for i in range(1, len(item)):
                try:
                    _Util.shellCall("%s %s" % ("/bin/mount", item[i]))
                    self.okList.insert(0, dir)
                except subprocess.CalledProcessError:
                    for dir2 in self.okList:
                        _Util.cmdCallIgnoreResult("/bin/umount", "-l", dir2)
                    raise

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        for d in self.okList:
            _Util.cmdCallIgnoreResult("/bin/umount", "-l", d)


class _FakeUsrSrcLinuxDirectory:

    def __init__(self, prefix=None):
        self.prefix = prefix if prefix is not None else ""

    def __enter__(self):
        if not self._checkUsrSrc():
            raise Exception("invalid /usr/src")

        bootDir = "%s/boot" % (self.prefix)
        dstDir = "%s/usr/src/linux" % (self.prefix)
        try:
            os.makedirs(dstDir, exist_ok=True)
            self._fillUsrSrcLinux(bootDir, dstDir)
            return self
        except Exception:
            self._close()
            raise

    def __exit__(self, type, value, traceback):
        assert self._checkUsrSrc()
        self._close()

    def _checkUsrSrc(self):
        if not os.path.exists("%s/usr/src" % (self.prefix)):
            return True
        else:
            for fn in os.listdir("%s/usr/src" % (self.prefix)):
                if fn != "linux":
                    return False
            return True

    def _fillUsrSrcLinux(self, bootDir, dstDir):
        flist = glob.glob(os.path.join(bootDir, "config-*"))
        flist = [x for x in flist if not x.endswith(".rules")]
        if flist != []:
            fn = flist[0]           # example: /mnt/gentoo/boot/config-x86_64-4.11.9
            shutil.copyfile(fn, os.path.join(dstDir, ".config"))
            ver = os.path.basename(fn).split("-")[2]
            version = ver.split(".")[0]
            patchlevel = ver.split(".")[1]
            sublevel = ver.split(".")[2]
        else:
            with gzip.open("/proc/config.gz", "rb") as f_in:
                with open(os.path.join(dstDir, ".config"), "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            version = _Util.shellCall("/usr/bin/uname -r | /usr/bin/cut -d '.' -f 1")
            patchlevel = _Util.shellCall("/usr/bin/uname -r | /usr/bin/cut -d '.' -f 2")
            sublevel = _Util.shellCall("/usr/bin/uname -r | /usr/bin/cut -d '.' -f 3")

        with open(os.path.join(dstDir, "Makefile"), "w") as f:
            f.write("# Faked by fpemud-refsystem to fool linux-info.eclass\n")
            f.write("\n")
            f.write("VERSION = %s\n" % (version))
            f.write("PATCHLEVEL = %s\n" % (patchlevel))
            f.write("SUBLEVEL = %s\n" % (sublevel))
            f.write("EXTRAVERSION = \n")

    def _close(self):
        if os.path.exists("%s/usr/src" % (self.prefix)):
            shutil.rmtree("%s/usr/src" % (self.prefix))


class _CopyResolvConf:

    def __init__(self, srcFile, dstDir):
        self.srcf = srcFile
        self.dstf = os.path.join(dstDir, "etc", "resolv.conf")
        self.exists = os.path.exists(self.dstf)
        shutil.copy2(self.srcf, self.dstf)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.exists:
            with open(self.dstf, "w") as f:
                f.truncate()
        else:
            os.unlink(self.dstf)


class _Util:

    @staticmethod
    def isGentooRootDir(dirname):
        dirset = set(["bin", "dev", "etc", "lib", "proc", "sbin", "sys", "tmp", "usr", "var"])
        return dirset <= set(os.listdir(dirname))

    @staticmethod
    def getMountDeviceForPath(pathname):
        for line in _Util.cmdCall("/bin/mount").split("\n"):
            m = re.search("^(.*) on (.*) type ", line)
            if m is not None and m.group(2) == pathname:
                return m.group(1)
        return None

    @staticmethod
    def isMountPoint(pathname):
        return _Util.getMountDeviceForPath(pathname) is not None

    @staticmethod
    def cmdCall(cmd, *kargs):
        # call command to execute backstage job
        #
        # scenario 1, process group receives SIGTERM, SIGINT and SIGHUP:
        #   * callee must auto-terminate, and cause no side-effect
        #   * caller must be terminated by signal, not by detecting child-process failure
        # scenario 2, caller receives SIGTERM, SIGINT, SIGHUP:
        #   * caller is terminated by signal, and NOT notify callee
        #   * callee must auto-terminate, and cause no side-effect, after caller is terminated
        # scenario 3, callee receives SIGTERM, SIGINT, SIGHUP:
        #   * caller detects child-process failure and do appopriate treatment

        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()

    @staticmethod
    def cmdCallIgnoreResult(cmd, *kargs):
        ret = subprocess.run([cmd] + list(kargs),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             universal_newlines=True)
        if ret.returncode > 128:
            time.sleep(1.0)

    @staticmethod
    def shellCall(cmd):
        # call command with shell to execute backstage job
        # scenarios are the same as _Util.cmdCall

        ret = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             shell=True, universal_newlines=True)
        if ret.returncode > 128:
            # for scenario 1, caller's signal handler has the oppotunity to get executed during sleep
            time.sleep(1.0)
        if ret.returncode != 0:
            print(ret.stdout)
            ret.check_returncode()
        return ret.stdout.rstrip()


###############################################################################


if __name__ == "__main__":
    ret = Main().main()
    sys.exit(ret)
