#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-


import bbki
from fm_param import FmConst


class FmBbkiWrapper:

    def __init__(self, param):
        self.param = param
        self._bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))

    def obj(self):
        return self._bbki

    def installInitramfs(self, layout):
        self._bbki.install_initramfs(self, self.getStorageInfo(layout))

    def installBootloader(self, layout):
        self._bbki.install_bootloader(bbki.util.get_boot_mode(), self.getStorageInfo(layout), self.getAuxOsInfo(), "")

    def updateBootloader(self):
        self._bbki.update_bootloader()

    def getStorageInfo(self, layout):
        pass

    def getAuxOsInfo(self):
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
                chain = 4
                ret.append(HostAuxOs(osDesc, osPart, FmUtil.getBlkDevUuid(osPart), chain))
                continue
            if True:
                ret.append(HostAuxOs(itemList[1], itemList[0], FmUtil.getBlkDevUuid(itemList[0]), 1)
                continue
        return ret
