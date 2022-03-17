#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from fm_util import FmUtil


class FmSwapManager:

    def __init__(self, param):
        self.param = param

    def enableSwap(self, layout):
        if layout.name in ["bios-ext4", "efi-ext4"]:
            if layout.dev_swap is None:
                layout.create_swap_file()
        elif layout.name in ["efi-bcache-btrfs", "efi-bcachefs"]:
            if layout.dev_swap is None:
                raise Exception("no swap partition")
        else:
            assert False

        serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
        self._createSwapService(layout.dev_swap, serviceName)
        self._enableSwapService(layout.dev_swap, serviceName)

    def disableSwap(self, layout):
        serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
        self._disableSwapService(layout.dev_swap, serviceName)
        self._removeSwapService(layout.dev_swap, serviceName)

        if layout.name in ["bios-ext4", "efi-ext4"]:
            layout.remove_swap_file()
        elif layout.name in ["efi-bcache-btrfs", "efi-bcachefs"]:
            pass
        else:
            assert False

    def _createSwapService(self, path, serviceName):
        fullf = os.path.join("/etc/systemd/system", serviceName)
        fileContent = self.__genSwapServFile(path)

        if os.path.exists(fullf):
            with open(fullf, "r") as f:
                if f.read() == fileContent:
                    return

        with open(fullf, "w") as f:
            f.write(fileContent)

    def _removeSwapService(self, path, serviceName):
        os.unlink(os.path.join("/etc/systemd/system", serviceName))

    def _enableSwapService(self, path, serviceName):
        FmUtil.cmdCall("systemctl", "enable", serviceName)
        if self.param.runMode == "normal":
            FmUtil.cmdCall("systemctl", "start", serviceName)
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("swapon", path)
        elif self.param.runMode == "prepare":
            assert False
        else:
            assert False

    def _disableSwapService(self, path, serviceName):
        if self.param.runMode == "normal":
            FmUtil.cmdCall("systemctl", "stop", serviceName)
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("swapoff", path)
        elif self.param.runMode == "prepare":
            assert False
        else:
            assert False
        FmUtil.cmdCall("systemctl", "disable", serviceName)

    def __genSwapServFile(self, swapfile):
        buf = ""
        buf += "[Unit]\n"
        if swapfile.startswith("/dev"):
            buf += "Description=Swap Partition\n"
        else:
            buf += "Description=Swap File\n"
        buf += "\n"
        buf += "[Swap]\n"
        buf += "What=%s\n" % (swapfile)
        buf += "\n"
        buf += "[Install]\n"
        buf += "WantedBy=swap.target\n"
        return buf


class FmLoggingManager:

    def __init__(self, param):
        self.param = param

    def getLogCfg(self):
        pass

    def setLogCfg(self):
        pass
