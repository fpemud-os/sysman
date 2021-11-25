

    @staticmethod
    def isInChroot():
        # This technique is used in a few maintenance scripts in Debian
        out1 = FmUtil.cmdCall("/usr/bin/stat", "-c", "%%d:%%i", "/")
        out2 = FmUtil.cmdCall("/usr/bin/stat", "-c", "%%d:%%i", "/proc/1/root/.")
        return out1 != out2

    @staticmethod
    def cmdListPtyExec(cmdList, envDict=None):
        proc = ptyprocess.PtyProcessUnicode.spawn(cmdList, env=envDict)
        Util._communicateWithPty(proc)

    @staticmethod
    def cmdListPtyExecWithStuckCheck(cmdList, envDict={}, bQuiet=False):
        proc = ptyprocess.PtyProcessUnicode.spawn(cmdList, env=envDict)
        Util._communicateWithPtyStuckCheck(proc, bQuiet)

    @staticmethod
    def shellPtyExec(cmd, envDict=None):
        proc = ptyprocess.PtyProcessUnicode.spawn(["/bin/sh", "-c", cmd], env=envDict)
        Util._communicateWithPty(proc)

    @staticmethod
    def shellPtyExecWithStuckCheck(cmd, envDict=None, bQuiet=False):
        proc = ptyprocess.PtyProcessUnicode.spawn(["/bin/sh", "-c", cmd], env=envDict)
        Util._communicateWithPtyStuckCheck(proc, bQuiet)

    @staticmethod
    def getMountDeviceForPath(pathname):
        buf = Util.cmdCall("/bin/mount")
        for line in buf.split("\n"):
            m = re.search("^(.*) on (.*) type ", line)
            if m is not None and m.group(2) == pathname:
                return m.group(1)
        return None



    @staticmethod
    def _communicateWithPty(ptyProc):
        if hasattr(selectors, 'PollSelector'):
            pselector = selectors.PollSelector
        else:
            pselector = selectors.SelectSelector

        # redirect proc.stdout/proc.stderr to stdout/stderr
        # make CalledProcessError contain stdout/stderr content
        sStdout = ""
        with pselector() as selector:
            selector.register(ptyProc, selectors.EVENT_READ)
            while selector.get_map():
                res = selector.select(TIMEOUT)
                for key, events in res:
                    try:
                        data = key.fileobj.read(1)
                    except EOFError:
                        selector.unregister(key.fileobj)
                        continue
                    sStdout += data
                    sys.stdout.write(data)
                    sys.stdout.flush()

        ptyProc.wait()
        if ptyProc.signalstatus is not None:
            time.sleep(PARENT_WAIT)
        if ptyProc.exitstatus:
            raise subprocess.CalledProcessError(ptyProc.exitstatus, ptyProc.argv, sStdout, "")

    @staticmethod
    def _communicateWithPtyStuckCheck(ptyProc, bQuiet):
        if hasattr(selectors, 'PollSelector'):
            pselector = selectors.PollSelector
        else:
            pselector = selectors.SelectSelector

        # redirect proc.stdout/proc.stderr to stdout/stderr
        # make CalledProcessError contain stdout/stderr content
        # terminate the process and raise exception if they stuck
        sStdout = ""
        bStuck = False
        with pselector() as selector:
            selector.register(ptyProc, selectors.EVENT_READ)
            while selector.get_map():
                res = selector.select(TIMEOUT)
                if res == []:
                    bStuck = True
                    if not bQuiet:
                        sys.stderr.write("Process stuck for %d second(s), terminated.\n" % (TIMEOUT))
                    ptyProc.terminate()
                    break
                for key, events in res:
                    try:
                        data = key.fileobj.read(1)
                    except EOFError:
                        selector.unregister(key.fileobj)
                        continue
                    sStdout += data
                    sys.stdout.write(data)
                    sys.stdout.flush()

        ptyProc.wait()
        if ptyProc.signalstatus is not None:
            time.sleep(PARENT_WAIT)
        if bStuck:
            raise ProcessStuckError(ptyProc.args, TIMEOUT)
        if ptyProc.exitstatus:
            raise subprocess.CalledProcessError(ptyProc.exitstatus, ptyProc.argv, sStdout, "")






class _InterProcessCounter:

    def __init__(self, name):
        self.name = name
        self.librt = ctypes.CDLL("librt.so", use_errno=True)

        # # https://github.com/erikhvatum/py_interprocess_shared_memory_blob
        # self.shm_open_argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_unit32]

        # self.pthread_rwlockattr_t = ctypes.c_byte * 8
        # self.pthread_rwlockattr_t_p = ctypes.POINTER(self.pthread_rwlockattr_t)

        # self.pthread_rwlock_t = ctypes.c_byte * 56
        # self.pthread_rwlock_t_p = ctypes.POINTER(self.pthread_rwlock_t)

        # API = [
        #     ('pthread_rwlock_destroy', [pthread_rwlock_t_p], 'pthread'),
        #     ('pthread_rwlock_init', [pthread_rwlock_t_p, pthread_rwlockattr_t_p], 'pthread'),
        #     ('pthread_rwlock_unlock', [pthread_rwlock_t_p], 'pthread'),
        #     ('pthread_rwlock_wrlock', [pthread_rwlock_t_p], 'pthread'),
        #     ('pthread_rwlockattr_destroy', [pthread_rwlockattr_t_p], 'pthread'),
        #     ('pthread_rwlockattr_init', [pthread_rwlockattr_t_p], 'pthread'),
        #     ('pthread_rwlockattr_setpshared', [pthread_rwlockattr_t_p, ctypes.c_int], 'pthread'),
        #     ('shm_open', shm_open_argtypes, 'os'),
        #     ('shm_unlink', [ctypes.c_char_p], 'os')
        # ]

    def incr(self):
        pass

    def decr(self):
        pass





# def findSwapFiles():
#     ret = []
#     for d in ["/var", "/"]:
#         for f in os.listdir(d):
#             fullf = os.path.join(d, f)
#             if fullf.endswith(".swap"):
#                 if FmUtil.cmdCallTestSuccess("/sbin/swaplabel", fullf):
#                     ret.append(fullf)
#     return ret

# def getSystemSwapInfo():
#     # return (swap-total, swap-free), unit: byte
#     buf = ""
#     with open("/proc/meminfo") as f:
#         buf = f.read()
#     m = re.search("^SwapTotal: +([0-9]+) kB$", buf, re.M)
#     if m is None:
#         raise Exception("get system \"SwapTotal\" from /proc/meminfo failed")
#     m2 = re.search("^SwapFree: +([0-9]+) kB$", buf, re.M)
#     if m is None:
#         raise Exception("get system \"SwapFree\" from /proc/meminfo failed")
#     return (int(m.group(1)) * 1024, int(m2.group(1)) * 1024)

# def systemdFindAllSwapServices():
#     # get all the swap service name
#     ret = []
#     for f in os.listdir("/etc/systemd/system"):
#         fullf = os.path.join("/etc/systemd/system", f)
#         if not os.path.isfile(fullf) or not fullf.endswith(".swap"):
#             continue
#         ret.append(f)
#     return ret





        with self.infoPrinter.printInfoAndIndent("- Checking file systems"):
            # if True:
            #     # what we can check is very limited:
            #     # 1. no way to fsck ext4 root partition when it's on-line
            #     # 2. fscking vfat partition when it's on-line always finds dirty-bit
            #     if self.bAutoFix:
            #         fatFsckCmd = "/usr/sbin/fsck.vfat -a"
            #     else:
            #         fatFsckCmd = "/usr/sbin/fsck.vfat -n"

            #     if isinstance(layout, FmStorageLayoutBiosSimple):
            #         pass
            #     elif isinstance(layout, FmStorageLayoutEfiSimple):
            #         FmUtil.shellExec("%s %s" % (fatFsckCmd, layout.hddEspParti))
            #     elif isinstance(layout, FmStorageLayoutEfiLvm):
            #         for hdd in layout.lvmPvHddList:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, FmUtil.devPathDiskToPartition(hdd, 1)))
            #     elif isinstance(layout, FmStorageLayoutEfiBcacheLvm):
            #         if layout.ssd is not None:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, layout.ssdEspParti))
            #         for hdd in layout.lvmPvHddDict:
            #             FmUtil.shellExec("%s %s" % (fatFsckCmd, FmUtil.devPathDiskToPartition(hdd, 1)))
            #     else:
            #         assert False
            pass



    @staticmethod
    def getBlkDevCapacity(devPath):
        ret = FmUtil.cmdCall("/bin/df", "-BM", devPath)
        m = re.search("%s +(\\d+)M +(\\d+)M +\\d+M", ret, re.M)
        total = int(m.group(1))
        used = int(m.group(2))
        return (total, used)        # unit: MB


    @staticmethod
    def getBlkDevLvmInfo(devPath):
        """Returns (vg-name, lv-name)
           Returns None if the device is not lvm"""

        rc, out = FmUtil.shellCallWithRetCode("/sbin/dmsetup info %s" % (devPath))
        if rc == 0:
            m = re.search("^Name: *(\\S+)$", out, re.M)
            assert m is not None
            ret = m.group(1).split(".")
            if len(ret) == 2:
                return ret
            ret = m.group(1).split("-")         # compatible with old lvm version
            if len(ret) == 2:
                return ret

        m = re.fullmatch("(/dev/mapper/\\S+)-(\\S+)", devPath)          # compatible with old lvm version
        if m is not None:
            return FmUtil.getBlkDevLvmInfo("%s-%s" % (m.group(1), m.group(2)))

        return None

