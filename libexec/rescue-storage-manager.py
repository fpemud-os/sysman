#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import sys
import time
import argparse
import subprocess
import strict_hdds


class Main:

    def main(self):
        if os.getuid() != 0:
            print("You must run this command as root!")
            return 1

        self.args = self._getArgParser().parse_args()

        if not hasattr(self.args, "op") or self.args.op == "show":
            return self._cmdShow()

        if self.args.op == "create":
            return self._cmdCreate()

        if self.args.op == "wipe":
            _Util.wipeHarddisk(self.args.harddisk)
            return 0

        if self.args.op == "wipe-all":
            _Util.cmdCall("/sbin/lvm", "vgchange", "-an")
            for devpath in _Util.getDevPathListForFixedHdd():
                print("Wipe harddisk %s" % (devpath))
                _Util.wipeHarddisk(devpath)
            return 0

        assert False

    def _getArgParser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()

        parser2 = subparsers.add_parser("show", help="Show target storage information")
        parser2.set_defaults(op="show")

        parser2 = subparsers.add_parser("create-layout", help="Create new target storage layout")
        parser2.set_defaults(op="create")
        parser2.add_argument("layout_name", metavar="layout-name")

        parser2 = subparsers.add_parser("wipe-harddisk", help="Wipe the specified harddisk")
        parser2.set_defaults(op="wipe")
        parser2.add_argument("harddisk")

        parser2 = subparsers.add_parser("wipe-all-harddisks", help="Wipe all the harddisks of target storage")
        parser2.set_defaults(op="wipe-all")

        return parser

    def _cmdShow(self):
        layout = strict_hdds.get_current_storage_layout()
        if layout is None:
            print("Storage layout: empty")
            return 1

        if layout.name == "efi-bcache-lvm-ext4":
            if layout.get_ssd() is not None:
                ssdStr = layout.get_ssd()
                if layout.get_ssd_swap_partition() is not None:
                    swapStr = "(with swap)"
                else:
                    swapStr = ""
                bootDiskStr = ""
            else:
                ssdStr = "None"
                swapStr = ""
                bootDiskStr = " (boot disk: %s)" % (layout.boot_disk)
            print("Storage layout: %s, SSD: %s%s, LVM PVs: %s%s" % (layout.name, ssdStr, swapStr, " ".join(layout.get_hdd_list()), bootDiskStr))
            return 0

        if layout.name == "efi-ext4":
            if layout.dev_swap is not None:
                swapStr = " (with swap)"
            else:
                swapStr = ""
            print("Storage layout: %s, HDD: %s%s" % (layout.name, layout.boot_disk, swapStr))
            return 0

        if layout.name == "bios-ext4":
            if layout.dev_swap is not None:
                swapStr = " (with swap)"
            else:
                swapStr = ""
            print("Storage layout: %s, HDD: %s%s" % (layout.name, layout.boot_disk, swapStr))
            return 0

        assert False

    def _cmdCreate(self):
        if self.args.layout_name not in strict_hdds.get_supported_storage_layouts():
            print("Invalid storage layout!")
            return 1

        layout = strict_hdds.create_and_mount_storage_layout(self.args.layout_name)
        if self.args.layout_name == "bios-ext4":
            print("Root device: %s" % (layout.dev_rootfs))
            print("Swap file: None")
        elif self.args.layout_name == "efi-ext4":
            print("Root device: %s" % (layout.dev_rootfs))
            print("Swap file: None")
        elif self.args.layout_name == "efi-bache-lvm":
            print("Root device: %s" % (layout.dev_rootfs))
            print("Swap device: %s" % (layout.dev_swap if layout.dev_swap is not None else "None"))
            print("Boot disk: %s" % (layout.get_esp()))
        else:
            assert False
        return 0


class _Util:

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
    def wipeHarddisk(devpath):
        with open(devpath, 'wb') as f:
            f.write(bytearray(1024))

    @staticmethod
    def getDevPathListForFixedHdd():
        ret = []
        for line in _Util.cmdCall("/bin/lsblk", "-o", "NAME,TYPE", "-n").split("\n"):
            m = re.fullmatch("(\\S+)\\s+(\\S+)", line)
            if m is None:
                continue
            if m.group(2) != "disk":
                continue
            if re.search("/usb[0-9]+/", os.path.realpath("/sys/block/%s/device" % (m.group(1)))) is not None:      # USB device
                continue
            ret.append("/dev/" + m.group(1))
        return ret


###############################################################################


if __name__ == "__main__":
    ret = Main().main()
    sys.exit(ret)
