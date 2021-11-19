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
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            if FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                self._disableSwapService(layout.dev_swap, serviceName)
                layout.remove_swap_file()
                layout.create_swap_file()
            self._createSwapService(layout.dev_swap, serviceName)
            self._enableSwapService(layout.dev_swap, serviceName)
            return

        if layout.name == "efi-lvm-ext4":
            if layout.dev_swap is None:
                layout.create_swap_lv()
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            if FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                self._disableSwapService(layout.dev_swap, serviceName)
                layout.remove_swap_lv()
                layout.create_swap_lv()
            self._createSwapService(layout.dev_swap, serviceName)
            self._enableSwapService(layout.dev_swap, serviceName)
            return

        if layout.name == "efi-bcache-lvm-ext4":
            if layout.dev_swap is None:
                raise Exception("no swap partition")
            if FmUtil.getBlkDevSize(layout.dev_swap) < layout.get_suggestted_swap_size():
                raise Exception("swap partition is too small")
            serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
            self._createSwapService(layout.dev_swap, serviceName)
            self._enableSwapService(layout.dev_swap, serviceName)
            return

        assert False

    def disableSwap(self, layout):
        serviceName = FmUtil.path2SwapServiceName(layout.dev_swap)
        self._disableSwapService(layout.dev_swap, serviceName)
        self._removeSwapService(layout.dev_swap, serviceName)

        if layout.name in ["bios-ext4", "efi-ext4"]:
            layout.remove_swap_file()
        elif layout.name == "efi-lvm-ext4":
            layout.remove_swap_lv()
        elif layout.name == "efi-bcache-lvm-ext4":
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
        FmUtil.cmdCall("/bin/systemctl", "enable", serviceName)
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapon", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "start", serviceName)
        else:
            assert False

    def _disableSwapService(self, path, serviceName):
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapoff", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "stop", serviceName)
        else:
            assert False
        FmUtil.cmdCall("/bin/systemctl", "disable", serviceName)

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
