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


class FkmBootLoader:

    def __init__(self):
        self.rescueOsDir = "/boot/rescue"
        self.historyDir = "/boot/history"

    def isStable(self):
        # we use grub environment variable to store stable status, our grub needs this status either
        if not os.path.exists("/boot/grub/grubenv"):
            return False
        out = FmUtil.cmdCall("/usr/bin/grub-editenv", "/boot/grub/grubenv", "list")
        return re.search("^stable=", out, re.M) is not None

    def setStable(self, bStable):
        if bStable:
            FmUtil.cmdCall("/usr/bin/grub-editenv", "/boot/grub/grubenv", "set", "stable=1")
        else:
            if not os.path.exists("/boot/grub/grubenv"):
                return
            FmUtil.cmdCall("/usr/bin/grub-editenv", "/boot/grub/grubenv", "unset", "stable")

    def getAuxOsInfo(self):
        """Returns (os-description, os-partition, os-boot-partition, chainloader-number)"""

        ret = []
        for line in FmUtil.cmdCall("/usr/bin/os-prober").split("\n"):
            itemList = line.split(":")
            if len(itemList) != 4:
                continue
            if itemList[3] == "linux":
                continue

            if itemList[1].endswith("(loader)"):               # for Microsoft Windows quirks
                m = re.fullmatch("(.*?)([0-9]+)", itemList[0])
                osDesc = itemList[1].replace("(loader)", "").strip()
                osPart = "%s%d" % (m.group(1), int(m.group(2)) + 1)
                osbPart = itemList[0]
                chain = 4
                ret.append((osDesc, osPart, osbPart, chain))
                continue
            if True:
                ret.append((itemList[1], itemList[0], itemList[0], 1))
                continue
        return ret

    def checkBootloader(self, hwInfo, storageLayout):
        if storageLayout.getType() == "efi":
            self._uefiGrubCheck(hwInfo, storageLayout)
        elif storageLayout.getType() == "bios":
            self._biosGrubCheck(hwInfo, storageLayout)
        else:
            assert False

    def updateBootloader(self, hwInfo, storageLayout, kernelInitCmd):
        if storageLayout.getType() == "efi":
            self._uefiGrubInstall(hwInfo, storageLayout, kernelInitCmd)
        elif storageLayout.getType() == "bios":
            self._biosGrubInstall(hwInfo, storageLayout, kernelInitCmd)
        else:
            assert False

    def removeBootloader(self, storageLayout):
        if storageLayout.getType() == "efi":
            self._uefiGrubRemove()
        elif storageLayout.getType() == "bios":
            self._biosGrubRemove(storageLayout)
        else:
            assert False

    def cleanBootloader(self):
        grubcfg = "/boot/grub/grub.cfg"

        lineList = []
        with open(grubcfg) as f:
            lineList = f.read().split("\n")

        lineList2 = []
        b = False
        for line in lineList:
            if not b and re.search("^\\s*menuentry\\s+\\\"History:", line, re.I) is not None:
                b = True
                continue
            if b and re.search("^\\s*}\\s*$", line, re.I) is not None:
                b = False
                continue
            if b:
                continue
            lineList2.append(line)

        with open(grubcfg, "w") as f:
            for line in lineList2:
                f.write(line + "\n")

    def _genGrubCfg(self, grubCfgFile, mode, layout, prefix, buildTarget, grubKernelOpt, extraTimeout, initCmdline):
        grubRootDev = layout.getBootDev() if layout.getBootDev() is not None else layout.getRootDev()
        buf = ''

        # deal with recordfail variable
        buf += 'load_env\n'
        buf += 'if [ "${recordfail}" ] ; then\n'
        buf += '  unset stable\n'
        buf += '  save_env stable\n'
        buf += '  unset recordfail\n'
        buf += '  save_env recordfail\n'
        buf += 'fi\n'
        buf += '\n'

        # specify default menuentry and timeout
        if mode == "bios":
            loadVideo = 'insmod vbe'
        elif mode == "efi":
            loadVideo = 'insmod efi_gop ; insmod efi_uga'
        else:
            assert False
        buf += '%s\n' % (loadVideo)
        buf += 'if [ "${stable}" ] ; then\n'
        buf += '  set default=0\n'
        buf += '  set timeout=%d\n' % (0 + extraTimeout)
        buf += 'else\n'
        buf += '  set default=1\n'
        buf += '  if sleep --verbose --interruptible %d ; then\n' % (3 + extraTimeout)
        buf += '    set timeout=0\n'
        buf += '  else\n'
        buf += '    set timeout=-1\n'
        buf += '  fi\n'
        buf += 'fi\n'
        buf += '\n'

        # write comments
        buf += '# These options are recorded in initramfs\n'
        buf += '#   rootfs=%s(UUID:%s)\n' % (layout.getRootDev(), self._getBlkDevUuid(layout.getRootDev()))
        if initCmdline != "":
            buf += '#   init=%s\n' % (initCmdline)
        buf += '\n'

        # write menu entry for stable main kernel
        buf += 'menuentry "Stable: Linux-%s" {\n' % (buildTarget.postfix)
        buf += '  set gfxpayload=keep\n'
        buf += '  set recordfail=1\n'
        buf += '  save_env recordfail\n'
        buf += '  %s\n' % (self._getGrubRootDevCmd(grubRootDev))
        buf += '  linux %s quiet %s\n' % (os.path.join(prefix, buildTarget.kernelFile), grubKernelOpt)
        buf += '  initrd %s\n' % (os.path.join(prefix, buildTarget.initrdFile))
        buf += '}\n'
        buf += '\n'

        # write menu entry for main kernel
        buf += self._grubGetMenuEntryList("Current", buildTarget, grubRootDev, prefix, grubKernelOpt)

        # write menu entry for rescue os
        if os.path.exists("/boot/rescue"):
            uuid = self._getBlkDevUuid(grubRootDev)
            kernelFile = os.path.join(prefix, "rescue", "x86_64", "vmlinuz")
            initrdFile = os.path.join(prefix, "rescue", "x86_64", "initcpio.img")
            myPrefix = os.path.join(prefix, "rescue")
            buf += self._grubGetMenuEntryList2("Rescue OS",
                                               grubRootDev,
                                               "%s dev_uuid=%s basedir=%s" % (kernelFile, uuid, myPrefix),
                                               initrdFile)

        # write menu entry for auxillary os
        for osDesc, osPart, osbPart, chain in self.getAuxOsInfo():
            buf += 'menuentry "Auxillary: %s" {\n' % (osDesc)
            buf += '  %s\n' % (self._getGrubRootDevCmd(osbPart))
            buf += '  chainloader +%d\n' % (chain)
            buf += '}\n'
            buf += '\n'

        # write menu entry for history kernels
        if os.path.exists(self.historyDir):
            for kernelFile in sorted(os.listdir(self.historyDir), reverse=True):
                if kernelFile.startswith("kernel-"):
                    buildTarget = FkmBuildTarget.newFromKernelFilename(kernelFile)
                    if os.path.exists(os.path.join(self.historyDir, buildTarget.initrdFile)):
                        buf += self._grubGetMenuEntryList("History", buildTarget, grubRootDev, os.path.join(prefix, "history"), grubKernelOpt)

        # write menu entry for restart
        buf += 'menuentry "Restart" {\n'
        buf += '    reboot\n'
        buf += '}\n'
        buf += '\n'

        # write menu entry for restarting to UEFI setup
        if mode == "efi":
            buf += 'menuentry "Restart to UEFI setup" {\n'
            buf += '  fwsetup\n'
            buf += '}\n'
            buf += '\n'

        # write menu entry for shutdown
        buf += 'menuentry "Power Off" {\n'
        buf += '    halt\n'
        buf += '}\n'
        buf += '\n'

        # write grub.cfg file
        with open(grubCfgFile, "w") as f:
            f.write(buf)

    def _grubGetMenuEntryList(self, title, buildTarget, grubRootDev, prefix, grubKernelOpt):
        return self._grubGetMenuEntryList2("%s: Linux-%s" % (title, buildTarget.postfix),
                                           grubRootDev,
                                           "%s %s" % (os.path.join(prefix, buildTarget.kernelFile), grubKernelOpt),
                                           os.path.join(prefix, buildTarget.initrdFile))

    def _grubGetMenuEntryList2(self, title, grubRootDev, kernelLine, initrdLine):
        buf = ''
        buf += 'menuentry "%s" {\n' % (title)
        buf += '  %s\n' % (self._getGrubRootDevCmd(grubRootDev))
        buf += '  echo "Loading Linux kernel ..."\n'
        buf += '  linux %s\n' % (kernelLine)
        buf += '  echo "Loading initial ramdisk ..."\n'
        buf += '  initrd %s\n' % (initrdLine)
        buf += '}\n'
        buf += '\n'
        return buf

    def _biosGrubCheck(self, hwInfo, storageLayout):
        if FmUtil.getBlkDevPartitionTableType(storageLayout.getBootHdd()) != "dos":
            raise Exception("/ must be in a disk with MBR partition table!")

    def _biosGrubInstall(self, hwInfo, storageLayout, kernelInitCmd):
        ret = FkmBootEntry.findCurrent()
        if ret is None:
            raise Exception("Invalid current boot item, strange?!")

        grubKernelOpt = "console=ttynull"       # only use console when debug boot process

        # backup old directory
        if os.path.exists("/boot/grub"):
            os.makedirs(self.historyDir, exist_ok=True)
            robust_layer.simple_fops.mv("/boot/grub", os.path.join(self.historyDir, "grub"))

        # install /boot/grub directory
        # install grub into disk MBR
        FmUtil.cmdCall("/usr/sbin/grub-install", "--target=i386-pc", storageLayout.getBootHdd())

        # generate grub.cfg
        self._genGrubCfg("/boot/grub/grub.cfg",
                         "bios",
                         storageLayout,
                         "/boot",
                         ret.buildTarget,
                         grubKernelOpt,
                         hwInfo.grubExtraWaitTime,
                         FmConst.kernelInitCmd)

    def _biosGrubRemove(self, storageLayout):
        # remove MBR
        with open(storageLayout.getBootHdd(), "wb+") as f:
            f.write(FmUtil.newBuffer(0, 440))

        # remove /boot/grub directory
        robust_layer.simple_fops.rm("/boot/grub")

    def _uefiGrubCheck(self, hwInfo, storageLayout):
        bootDev = storageLayout.getBootDev()
        if not FmUtil.gptIsEspPartition(bootDev):
            raise Exception("/boot must be mounted to ESP partition!")
        if FmUtil.getBlkDevFsType(bootDev) != "vfat":
            raise Exception("/boot must use vfat file system!")

    def _uefiGrubInstall(self, hwInfo, storageLayout, kernelInitCmd):
        # get variables
        ret = FkmBootEntry.findCurrent()
        if ret is None:
            raise Exception("invalid current boot item, strange?!")

        grubKernelOpt = "console=ttynull"       # only use console when debug boot process

        # backup old directory
        if os.path.exists("/boot/grub"):
            os.makedirs(self.historyDir, exist_ok=True)
            robust_layer.simple_fops.mv("/boot/grub", os.path.join(self.historyDir, "grub"))
        if os.path.exists("/boot/EFI"):
            os.makedirs(self.historyDir, exist_ok=True)
            robust_layer.simple_fops.mv("/boot/EFI", os.path.join(self.historyDir, "EFI"))

        # install /boot/grub and /boot/EFI directory
        # install grub into ESP
        # *NO* UEFI firmware variable is touched, so that we are portable
        FmUtil.cmdCall("/usr/sbin/grub-install", "--removable", "--target=x86_64-efi", "--efi-directory=/boot", "--no-nvram")

        # generate grub.cfg
        self._genGrubCfg("/boot/grub/grub.cfg",
                         "efi",
                         storageLayout,
                         "/",
                         ret.buildTarget,
                         grubKernelOpt,
                         hwInfo.grubExtraWaitTime,
                         FmConst.kernelInitCmd)

    def _uefiGrubRemove(self):
        robust_layer.simple_fops.rm("/boot/EFI")
        robust_layer.simple_fops.rm("/boot/grub")

    def _getGrubRootDevCmd(self, devPath):
        if os.path.dirname(devPath) == "/dev/mapper" or devPath.startswith("/dev/dm-"):
            lvmInfo = FmUtil.getBlkDevLvmInfo(devPath)
            if lvmInfo is not None:
                return "set root=(lvm/%s-%s)" % (lvmInfo[0], lvmInfo[1])

        return "search --fs-uuid --no-floppy --set %s" % (self._getBlkDevUuid(devPath))

    def _getBlkDevUuid(self, devPath):
        uuid = FmUtil.getBlkDevUuid(devPath)
        if uuid == "":
            raise Exception("device %s unsupported" % (devPath))
        return uuid

    def _getBackgroundFileInfo(self):
        for fn in glob.glob("/boot/background.*"):
            fn = fn.replace("/boot", "")
            if fn.endswith(".png"):
                return (fn, "png")
            elif fn.endswith(".jpg"):
                return (fn, "jpg")
        return None


class FkmMountBootDirRw:

    def __init__(self, storageLayout):
        self.storageLayout = storageLayout

        if self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI:
            FmUtil.cmdCall("/bin/mount", self.storageLayout.getBootDev(), "/boot", "-o", "rw,remount")
        elif self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_BIOS:
            pass
        else:
            assert False

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_EFI:
            FmUtil.cmdCall("/bin/mount", self.storageLayout.getBootDev(), "/boot", "-o", "ro,remount")
        elif self.storageLayout.boot_mode == strict_hdds.StorageLayout.BOOT_MODE_BIOS:
            pass
        else:
            assert False
