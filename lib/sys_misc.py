#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
from fm_util import FmUtil


class FmSwapManager:

    def __init__(self, param):
        self.param = param

    def createSwapService(self, path, serviceName):
        fullf = os.path.join("/etc/systemd/system", serviceName)
        fileContent = self._genSwapServFile(path)

        if os.path.exists(fullf):
            with open(fullf, "r") as f:
                if f.read() == fileContent:
                    return

        with open(fullf, "w") as f:
            f.write(fileContent)

    def removeSwapService(self, path, serviceName):
        os.unlink(os.path.join("/etc/systemd/system", serviceName))

    def enableSwapService(self, path, serviceName):
        FmUtil.cmdCall("/bin/systemctl", "enable", serviceName)
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapon", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "start", serviceName)
        else:
            assert False

    def disableSwapService(self, path, serviceName):
        if self.param.runMode == "prepare":
            assert False
        elif self.param.runMode == "setup":
            FmUtil.cmdCall("/sbin/swapoff", path)
        elif self.param.runMode == "normal":
            FmUtil.cmdCall("/bin/systemctl", "stop", serviceName)
        else:
            assert False
        FmUtil.cmdCall("/bin/systemctl", "disable", serviceName)

    def _genSwapServFile(self, swapfile):
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
