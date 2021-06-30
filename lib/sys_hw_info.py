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

    CHASSIS_TYPE_COMPUTER = 1
    CHASSIS_TYPE_LAPTOP = 2
    CHASSIS_TYPE_TABLET = 3
    CHASSIS_TYPE_HANDSET = 4
    CHASSIS_TYPE_HEADLESS = 5

    def __init__(self):
        self.arch = None                      # str
        self.chassisType = None               # str
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


class FmMachineInfoGetter:

    def __init__(self, param):
        self._param = param
        self._obj = None

    def hwInfo(self):
        ret = None

        if ret is None:
            ret = _UtilPcHp().info()
        if ret is None:
            ret = _UtilPcAsus().info()
        if ret is None:
            ret = _UtilPcAliyun().info()
        if ret is None:
            ret = _UtilPcDiy().info()
        if ret is None:
            return ret

        r = FmUtil.getMachineInfo(FmConst.machineInfoFile)
        if "CHASSIS" in r:
            if r["CHASSIS"] == "computer":
                ret.chassisType = HwInfo.CHASSIS_TYPE_COMPUTER
            elif r["CHASSIS"] == "laptop":
                ret.chassisType = HwInfo.CHASSIS_TYPE_LAPTOP
            elif r["CHASSIS"] == "tablet":
                ret.chassisType = HwInfo.CHASSIS_TYPE_TABLET
            elif r["CHASSIS"] == "handset":
                ret.chassisType = HwInfo.CHASSIS_TYPE_HANDSET
            elif r["CHASSIS"] == "headless":
                ret.chassisType = HwInfo.CHASSIS_TYPE_HEADLESS
            else:
                assert False

        return ret


class _UtilHwDict:

    @staticmethod
    def get(hwSpec):
        if hwSpec is not None:
            ret = copy.deepcopy(hwSpec)
        else:
            ret = dict()

        ret["cpu"] = {
            "vendor": _UtilHwDict._getCpuVendor(),
            "model": _UtilHwDict._getCpuModelName(),
            "cores": _UtilHwDict._getCpuCoreNumber(),
        }
        ret["memory"] = {
            "size": _UtilHwDict._getPhysicalMemoryTotalSize(),
        }

        return ret

    @staticmethod
    def _getCpuVendor():
        vendor = ""
        with open("/proc/cpuinfo") as f:
            m = re.search(r'vendor_id\s*:\s*(\S+)', f.read(), re.M)
            if m is not None:
                vendor = m.group(1)

        if vendor == "GenuineIntel":
            return "Intel"
        elif vendor == "AuthenticAMD":
            return "AMD"
        else:
            return "Unknown"

    @staticmethod
    def _getCpuModelName():
        model = ""
        with open("/proc/cpuinfo") as f:
            m = re.search(r'model name\s*:\s*(.*)', f.read(), re.M)
            if m is not None:
                model = m.group(1)

        # intel models
        if "i7-4600U" in model:
            return "i7-4600U"

        # amd models
        if "Ryzen Threadripper 1920X" in model:
            return "1920X"

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
        self.manu = FmUtil.dmiDecodeWithCache("system-manufacturer")
        if self.manu not in ["Hewlett-Packard", "HP"]:
            return None

        self.model = FmUtil.dmiDecodeWithCache("system-product-name")
        self.sn = FmUtil.dmiDecodeWithCache("system-serial-number")

        ret = HwInfoPcBranded()
        ret.name = self._name()
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.chassisType = self._chassisType()
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
            ret.update({
                "cpu": {
                    "vendor": "Intel",
                    "model": "i7-4600U",
                    "cores": 4,
                }
            })
        if self.model == "HP EliteBook 840 G3":
            return ret
        if self.model == "HP EliteBook 850 G1":
            return ret
        assert False

    def _chassisType(self):
        if self.model == "HP EliteBook 820 G1":
            return HwInfo.CHASSIS_TYPE_LAPTOP
        if self.model == "HP EliteBook 820 G3":
            return HwInfo.CHASSIS_TYPE_LAPTOP
        if self.model == "HP EliteBook 840 G1":
            return HwInfo.CHASSIS_TYPE_LAPTOP
        if self.model == "HP EliteBook 840 G3":
            return HwInfo.CHASSIS_TYPE_LAPTOP
        if self.model == "HP EliteBook 850 G1":
            return HwInfo.CHASSIS_TYPE_LAPTOP
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

        self.manu = FmUtil.dmiDecodeWithCache("system-manufacturer")
        if self.manu not in manuStrList:
            return None

        self.model = FmUtil.dmiDecodeWithCache("system-product-name")
        self.sn = FmUtil.dmiDecodeWithCache("system-serial-number")

        ret = HwInfoPcBranded()
        ret.name = "ASUS " + self.model
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.chassisType = self._chassisType()
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

    def _chassisType(self):
        if self.model == "T300CHI":
            return HwInfo.CHASSIS_TYPE_TABLET
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

    MODELS = [
        "ecs.t1.small",
    ]

    def info(self):
        self.manu = FmUtil.dmiDecodeWithCache("system-manufacturer")
        if self.manu != "Alibaba Cloud":
            return None
        assert FmUtil.dmiDecodeWithCache("system-product-name") == "Alibaba Cloud ECS"

        self.sn = FmUtil.dmiDecodeWithCache("system-serial-number")

        self.model = FmUtil.getMachineInfo(FmConst.machineInfoFile)["ALIYUN-HWNAME"]
        assert self.model in self.MODELS

        ret = HwInfoPcBranded()
        ret.name = "ALIYUN " + self.model
        ret.hwSpec = self._hwSpec()
        ret.serialNumber = self.sn
        ret.arch = "amd64"
        ret.chassisType = HwInfo.CHASSIS_TYPE_COMPUTER
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
        ret.chassisType = HwInfo.CHASSIS_TYPE_COMPUTER              # FIXME
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
        for fullfn in sorted(glob.glob(os.path.join(FmConst.dataDir, "kernel-config-rules", "*.rules"))):
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
            rname = "hardware-management-and-monitor"

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
            rname = "hardware-management-and-monitor"

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
            buf += "*/* CPU_FLAGS_X86: -* aes avx avx2 avx512f f16c fma3 fma4 mmx mmxext popcnt sse sse2 sse3 sse4_1 sse4_2 sse4a ssse3\n"
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
