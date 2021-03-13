#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import glob
import copy
import multiprocessing
from collections import OrderedDict
from fm_util import FmUtil
from fm_param import FmConst


class HwInfo:

    def __init__(self):
        self.arch = None                      # str
        self.hwDict = None                    # dict
        self.kernelCfgRules = None            # ordered-dict(section-name,section-content)
        self.useFlags = None                  # ordered-dict(section-name,section-content)
        self.grubExtraWaitTime = None         # int


class HwInfoPcBranded(HwInfo):

    def __init__(self):
        super().__init__()

        self.name = None
        self.hwSpec = None                    # dict
        self.serialNumber = None
        self.changeList = []


class HwInfoPcAssembled(HwInfo):

    def __init__(self):
        super().__init__()

        self.hwInfoFile = None
        self.lastUpdateTime = None


class FmHwInfoGetter:

    def current(self):
        ret = _UtilPcHp().info()
        if ret is not None:
            return ret

        ret = _UtilPcAsus().info()
        if ret is not None:
            return ret

        ret = _UtilPcAliyun().info()
        if ret is not None:
            return ret

        ret = _UtilPcDiy().info()
        if ret is not None:
            return ret

        return None


class _UtilHwDict:

    @staticmethod
    def get(hwSpec):
        if hwSpec is not None:
            ret = copy.deepcopy(hwSpec)
        else:
            ret = dict()

        ret["cpu"] = {
            "model": _UtilHwDict._getCpuModel(),
            "cores": _UtilHwDict._getCpuCoreNumber(),
        }
        ret["memory"] = {
            "size": _UtilHwDict._getPhysicalMemoryTotalSize(),
        }

        return ret

    @staticmethod
    def _getCpuModel():
        return "Unknown"

    @staticmethod
    def _getCpuCoreNumber():
        return multiprocessing.cpu_count()

    @staticmethod
    def _getPhysicalMemoryTotalSize():
        # memory size in GiB
        return FmUtil.getPhysicalMemorySize()


class _UtilPcHp:

    def info(self):
        self.manu = _Util.dmiDecodeWithCache("system-manufacturer")
        if self.manu not in ["Hewlett-Packard", "HP"]:
            return None

        self.model = _Util.dmiDecodeWithCache("system-product-name")
        self.sn = _Util.dmiDecodeWithCache("system-serial-number")

        ret = HwInfoPcBranded()
        ret.name = self._name()
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.hwDict = _UtilHwDict.get(ret.hwSpec)
        ret.changeList = self._changeList(ret.hwSpec, ret.hwDict)
        ret.kernelCfgRules = self._kernelCfgRules()
        ret.useFlags = self._useFlags()
        ret.grubExtraWaitTime = 0
        return ret

    def _name(self):
        if self.model == "HP EliteBook 820 G1":
            return self.model
        if self.model == "HP EliteBook 820 G3":
            return self.model
        if self.model == "HP EliteBook 840 G1":
            return self.model
        if self.model == "HP EliteBook 840 G3":
            return self.model
        if self.model == "HP EliteBook 850 G1":
            return self.model
        assert False

    def _hwSpec(self):
        ret = {
            "fan": {
                "only-fan": {
                    "model": "Embedded",
                    "power": "weak",
                },
            },
        }

        if self.model == "HP EliteBook 820 G1":
            return ret
        if self.model == "HP EliteBook 820 G3":
            return ret
        if self.model == "HP EliteBook 840 G1":
            return ret
        if self.model == "HP EliteBook 840 G3":
            return ret
        if self.model == "HP EliteBook 850 G1":
            return ret
        assert False

    def _changeList(self, origHwDict, hwDict):
        return []

    def _kernelCfgRules(self):
        ret = _Util.kernelCfgRules()
        if self.model == "HP EliteBook 820 G1":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        if self.model == "HP EliteBook 820 G3":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        if self.model == "HP EliteBook 840 G1":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        if self.model == "HP EliteBook 840 G3":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        if self.model == "HP EliteBook 850 G1":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        assert False

    def _useFlags(self):
        ret = _Util.getUseFlags("amd64")
        ret.update(_Util.getUseFlags2())
        return ret


class _UtilPcAsus:

    def info(self):
        manuStrList = [
            "ASUSTeK COMPUTER INC.",
        ]

        self.manu = _Util.dmiDecodeWithCache("system-manufacturer")
        if self.manu not in manuStrList:
            return None

        self.model = _Util.dmiDecodeWithCache("system-product-name")
        self.sn = _Util.dmiDecodeWithCache("system-serial-number")

        ret = HwInfoPcBranded()
        ret.name = "ASUS " + self.model
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.hwDict = _UtilHwDict.get(ret.hwSpec)
        ret.changeList = self._changeList(ret.hwSpec, ret.hwDict)
        ret.kernelCfgRules = self._kernelCfgRules()
        ret.useFlags = self._useFlags()
        ret.grubExtraWaitTime = 0
        return ret

    def _hwSpec(self):
        ret = {
        }

        if self.model == "T300CHI":
            return ret
        assert False

    def _changeList(self, origHwDict, hwDict):
        return []

    def _kernelCfgRules(self):
        ret = _Util.kernelCfgRules()
        if self.model == "T300CHI":
            ret = _Util.kernelCfgRulesForOnlyNewestIntelCpu(ret)
            return ret
        assert False

    def _useFlags(self):
        ret = _Util.getUseFlags("amd64")
        ret.update(_Util.getUseFlags2())
        return ret


class _UtilPcAliyun:

    def info(self):
        self.manu = _Util.dmiDecodeWithCache("system-manufacturer")
        if self.manu != "Alibaba Cloud":
            return None
        assert _Util.dmiDecodeWithCache("system-product-name") == "Alibaba Cloud ECS"

        self.sn = _Util.dmiDecodeWithCache("system-serial-number")

        self.model = FmUtil.getMachineInfo(FmConst.machineInfoFile)["ALIYUN-HWNAME"]
        assert self.model in [
            "ecs.t1.small",
        ]

        ret = HwInfoPcBranded()
        ret.name = "ALIYUN " + self.model
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.hwDict = _UtilHwDict.get(ret.hwSpec)
        ret.changeList = self._changeList(ret.hwSpec, ret.hwDict)
        ret.kernelCfgRules = self._kernelCfgRules()
        ret.useFlags = self._useFlags()
        ret.grubExtraWaitTime = 20
        return ret

    def _hwSpec(self):
        ret = {
        }

        if self.model == "ecs.t1.small":
            return ret
        assert False

    def _changeList(self, origHwDict, hwDict):
        return []

    def _kernelCfgRules(self):
        ret = _Util.kernelCfgRules()
        ret = _Util.kernelCfgRulesNoPowerSave(ret)
        if self.model == "ecs.t1.small":
            return ret
        assert False

    def _useFlags(self):
        ret = _Util.getUseFlags("amd64")
        ret.update(_Util.getUseFlags3())
        return ret


class _UtilPcDiy:

    def info(self):
        _tmpHwSpec = {
            "fan": {
                "only-fan": {
                    "model": "Embedded",
                    "power": "strong",
                },
            },
        }

        ret = HwInfoPcAssembled()
        ret.arch = "amd64"
        ret.hwDict = _UtilHwDict.get(_tmpHwSpec)
        ret.kernelCfgRules = _Util.kernelCfgRules()
        ret.useFlags = self._useFlags()
        ret.grubExtraWaitTime = 0
        return ret

    def _useFlags(self):
        ret = _Util.getUseFlags("amd64")
        ret.update(_Util.getUseFlags2())
        return ret

    def getCase(self, lastUpdateTimeToBeUpdated):
        return _Util.readHwInfoFile("CASE", lastUpdateTimeToBeUpdated)

    def getPower(self, lastUpdateTimeToBeUpdated):
        return _Util.readHwInfoFile("POWER", lastUpdateTimeToBeUpdated)

    def getMainBoard(self, lastUpdateTimeToBeUpdated):
        return None

    def getCpu(self, lastUpdateTimeToBeUpdated):
        buf = ""
        with open("/proc/cpuinfo", "r") as f:
            buf = f.read()
        m = re.search("^model name *: (.*)$", buf, re.M)
        if m is not None:
            return [m.group(1)]
        return _Util.readHwInfoFile("CPU", lastUpdateTimeToBeUpdated)


class _Util:

    @staticmethod
    def readHwInfoFile(fn, lastUpdateTimeToBeUpdated):
        fn = os.path.join(self.param.hwInfoDir, fn)
        if os.path.exists(fn):
            with open(fn, "r") as f:
                ret = f.read().split("\n")[0]
        return None

    @staticmethod
    def kernelCfgRules():
        ret = OrderedDict()
        for fullfn in sorted(glob.glob(os.path.join(FmConst.dataKernelCfgRulesDir, "*.rules"))):
            fn = os.path.basename(fullfn)
            rname = fn[:len(".rules") * -1]
            m = re.fullmatch("[0-9]+-(.*)", rname)
            if m is not None:
                rname = m.group(1)
            with open(fullfn, "r") as f:
                ret[rname] = f.read()
        return ret

    @staticmethod
    def kernelCfgRulesNoPowerSave(kernelCfgRules):
        if True:
            rname = "power-management-and-acpi"

            buf = ""
            buf += "ACPI_PROCESSOR=n\n"
            buf += "[symbols:ACPI]=m,y\n"
            kernelCfgRules[rname] = kernelCfgRules[rname].replace("[symbols:ACPI]=m,y\n", buf)

            kernelCfgRules[rname] = kernelCfgRules[rname].replace("[symbols:/Power management and ACPI options/CPU Frequency scaling]=y\n", "")
            kernelCfgRules[rname] = kernelCfgRules[rname].replace("INTEL_IDLE=y\n", "")
            kernelCfgRules[rname] = kernelCfgRules[rname].replace("[symbols:/Power management and ACPI options/CPU Idle]=y\n", "")

        return kernelCfgRules

    @staticmethod
    def kernelCfgRulesForOnlyNewestIntelCpu(kernelCfgRules):
        if True:
            rname = "power-management-and-acpi"

            toBeReplaced = "[symbols:/Power management and ACPI options/CPU Frequency scaling]=y\n"
            buf = ""
            buf += "CPU_FREQ=y\n"
            buf += "CPU_FREQ_STAT=y\n"
            buf += "X86_INTEL_PSTATE=y\n"
            buf += "/Power management and ACPI options/CPU Frequency scaling/CPU Frequency scaling/Default CPUFreq governor=CPU_FREQ_DEFAULT_GOV_PERFORMANCE\n"
            buf += "[symbols:/Power management and ACPI options/CPU Frequency scaling]=n\n"
            kernelCfgRules[rname] = kernelCfgRules[rname].replace(toBeReplaced, buf)

        return kernelCfgRules

    @staticmethod
    def getUseFlags(arch):
        ret = OrderedDict()

        if arch == "amd64":
            buf = ""
            buf += "# ACPI must be used for x86 series architecture\n"
            buf += "*/* acpi\n"
            buf += "\n"
            buf += "# Position-Independent-Code is used for x86 series architecture\n"
            buf += "*/* pic\n"
            buf += "\n"
            buf += "# abi_x86_64 -> global support, abi_x86_32 -> per-package support, abi_x86_x32 -> disable\n"
            buf += "*/* ABI_X86: -* 64\n"
            buf += "\n"
            buf += "# support all the common x86 cpu flags\n"
            buf += "*/* CPU_FLAGS_X86: -* aes avx avx2 fma3 fma4 mmx mmxext popcnt sse sse2 sse3 sse4_1 sse4_2 sse4a ssse3\n"
            ret["general"] = buf
        else:
            assert False

        return ret

    @staticmethod
    def getUseFlags2():
        ret = OrderedDict()

        if True:
            buf = ""
            buf += "*/* bluetooth\n"
            ret["bluetooth"] = buf

        if True:
            buf = ""
            buf += "# support all the common video cards\n"
            buf += "*/* VIDEO_CARDS: -* intel iris nouveau radeon radeonsi\n"
            ret["graphics"] = buf

        return ret

    @staticmethod
    def getUseFlags3():
        ret = OrderedDict()

        if True:
            buf = ""
            buf += "# support only common video standard\n"
            buf += "*/* VIDEO_CARDS: -* vesa\n"
            ret["graphics"] = buf

        return ret

    _dmiDecodeCache = dict()

    @staticmethod
    def dmiDecodeWithCache(key):
        if key in _Util._dmiDecodeCache:
            return _Util._dmiDecodeCache[key]

        ret = FmUtil.cmdCall("/usr/sbin/dmidecode", "-s", key)
        _Util._dmiDecodeCache[key] = ret
        return ret


class DevHwInfoDb:

    @staticmethod
    def getDevHwInfo(vendorId, deviceId):
        ret = DevHwInfoDb._doGetDrm(vendorId, deviceId)
        if ret is not None:
            return ret

        return None

    @staticmethod
    def _doGetDrm(vendorId, deviceId):
        # returns: {
        #     "mem": 8,           # unit: GB
        #     "fp64": 760,        # unit: gflops
        #     "fp32": 13200,      # unit: gflops
        #     "fp16": 24500,      # unit: gflops
        # }

        if vendorId == 0x1002 and deviceId == 0x66af:
            # AMD Radeon VII, https://www.amd.com/en/products/graphics/amd-radeon-vii
            return {
                "mem": 16 * 1024 * 1024 * 1024,                # 16GiB
                "fp64": int(3.46 * 1024),                      # 3.46 TFLOPs
                "fp32": int(13.8 * 1024),                      # 13.8 TFLOPs
                "fp16": int(27.7 * 1024),                      # 27.7 TFLOPs
            }

        # unknown device
        return None
