#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import strict_hdds
import robust_layer.simple_fops
from fm_util import FmUtil
from fm_param import FmConst
from helper_boot_kernel import FkmBuildTarget
from helper_boot_kernel import FkmBootEntry


class FkmBootDir:

    def __init__(self):
        self.historyDir = "/boot/history"

    def getMainOsStatus(self):
        ret = FkmBootEntry.findCurrent()
        if ret is not None:
            return "Linux (%s)" % (ret.buildTarget.postfix)
        else:
            return None

    def updateBootEntry(self, postfixCurrent):
        """require files already copied into /boot directory"""

        os.makedirs(self.historyDir, exist_ok=True)

        buildTarget = FkmBuildTarget.newFromPostfix(postfixCurrent)

        kernelFileList = [
            os.path.join("/boot", buildTarget.kernelFile),
        ]
        kernelCfgFileList = [
            os.path.join("/boot", buildTarget.kernelCfgFile),
            os.path.join("/boot", buildTarget.kernelCfgRuleFile),
        ]
        kernelMapFileList = [
            os.path.join("/boot", buildTarget.kernelMapFile),
        ]
        kernelSrcSignatureFileList = [
            os.path.join("/boot", buildTarget.kernelSrcSignatureFile),
        ]
        initrdFileList = [
            os.path.join("/boot", buildTarget.initrdFile),
            os.path.join("/boot", buildTarget.initrdTarFile),
        ]

        for fn in glob.glob("/boot/kernel-*"):
            if fn not in kernelFileList:
                os.rename(fn, os.path.join(self.historyDir, os.path.basename(fn)))
        for fn in glob.glob("/boot/config-*"):
            if fn not in kernelCfgFileList:
                os.rename(fn, os.path.join(self.historyDir, os.path.basename(fn)))
        for fn in glob.glob("/boot/System.map-*"):
            if fn not in kernelMapFileList:
                os.rename(fn, os.path.join(self.historyDir, os.path.basename(fn)))
        for fn in glob.glob("/boot/signature-*"):
            if fn not in kernelSrcSignatureFileList:
                os.rename(fn, os.path.join(self.historyDir, os.path.basename(fn)))
        for fn in glob.glob("/boot/initramfs-*"):
            if fn not in initrdFileList:
                os.rename(fn, os.path.join(self.historyDir, os.path.basename(fn)))

    def getHistoryKernelVersionList(self):
        if not os.path.exists(self.historyDir):
            return []
        ret = []
        for fn in glob.glob(os.path.join(self.historyDir, "kernel-*")):
            postfix = fn[len(os.path.join(self.historyDir, "kernel-")):]
            buildTarget = FkmBuildTarget.newFromPostfix(postfix)
            if not os.path.exists(os.path.join(self.historyDir, buildTarget.kernelCfgFile)):
                continue
            if not os.path.exists(os.path.join(self.historyDir, buildTarget.kernelCfgRuleFile)):
                continue
            if not os.path.exists(os.path.join(self.historyDir, buildTarget.kernelMapFile)):
                continue
            if not os.path.exists(os.path.join(self.historyDir, buildTarget.initrdFile)):
                continue
            if not os.path.exists(os.path.join(self.historyDir, buildTarget.initrdTarFile)):
                continue
            ret.append(buildTarget.ver)
        return ret

    def getHistoryFileList(self):
        if os.path.exists(self.historyDir):
            ret = []
            for fn in os.listdir(self.historyDir):
                ret.append(os.path.join(self.historyDir, fn))
            return ret
        else:
            return []

    def _escape(self, buf):
        return FmUtil.cmdCall("/bin/systemd-escape", buf)


class FkmMountBootDirRw:

    def __init__(self, storageLayout):
        self.storageLayout = storageLayout

        if self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI:
            FmUtil.cmdCall("/bin/mount", self.storageLayout.get_esp(), "/boot", "-o", "rw,remount")
        elif self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_BIOS:
            pass
        else:
            assert False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI:
            FmUtil.cmdCall("/bin/mount", self.storageLayout.get_esp(), "/boot", "-o", "ro,remount")
        elif self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_BIOS:
            pass
        else:
            assert False
