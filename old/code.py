

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
            #         fatFsckCmd = "fsck.vfat -a"
            #     else:
            #         fatFsckCmd = "fsck.vfat -n"

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





# def _standardMountList(rootfsDir):
#     mountList = []
#     if True:
#         tstr = os.path.join(rootfsDir, "proc")
#         mountList.append((tstr, "-t proc -o nosuid,noexec,nodev proc %s" % (tstr)))
#     if True:
#         tstr = os.path.join(rootfsDir, "sys")
#         mountList.append((tstr, "--rbind /sys %s" % (tstr), "--make-rslave %s" % (tstr)))
#     if True:
#         tstr = os.path.join(rootfsDir, "dev")
#         mountList.append((tstr, "--rbind /dev %s" % (tstr), "--make-rslave %s" % (tstr)))
#     if True:
#         tstr = os.path.join(rootfsDir, "run")
#         mountList.append((tstr, "--bind /run %s" % (tstr)))
#     if True:
#         tstr = os.path.join(rootfsDir, "tmp")
#         mountList.append((tstr, "-t tmpfs -o mode=1777,strictatime,nodev,nosuid tmpfs %s" % (tstr)))
#     return mountList






                # atop
                # b43-fwcutter
                # borg
                # chntpw
                # clonezilla
                # crda
                # darkhttpd
                # ddrescue
                # dhclient
                # dialog
                # dmraid
                # dnsmasq
                # dnsutils
                # elinks
                # ethtool
                # # featherpad
                # # firefox-esr-bin
                # fsarchiver
                # geany
                # gnu-netcat
                # gpm
                # grml-zsh-config
                # # growpart
                # grsync
                # iftop
                # iotop
                # irssi
                # iwd
                # # joe                       # this package disppears
                # keepassxc
                # lftp
                # lightdm
                # linux-atm
                # lzip
                # ncdu
                # ndisc6
                # network-manager-applet
                # networkmanager-openvpn
                # networkmanager-vpnc
                # # nwipe
                # openconnect
                # openssh
                # openvpn
                # partclone
                # partimage
                # ppp
                # pptpclient
                # pv
                # rdesktop
                # # refind-efi                    # this package disappears
                # rkhunter
                # rp-pppoe
                # sudo
                # sysstat
                # testdisk
                # tigervnc
                # ttf-dejavu
                # ttf-droid
                # usb_modeswitch
                # vim-minimal
                # vpnc
                # wipe
                # wireless-regdb
                # wireless_tools
                # wvdial
                # xarchiver
                # xfce4
                # xfce4-battery-plugin
                # xfce4-taskmanager
                # xkbsel
                # xkeyboard-config
                # xl2tpd
                # xorg-apps
                # xorg-drivers
                # xorg-server
                # xorg-xinit
                # yubikey-manager-qt
                # yubikey-personalization-gui
                # # zerofree
                # zile



class ArchLinuxBasedOsBuilder:

    def __init__(self, mirrorList, cacheDir, tmpDir):
        self.mirrorList = mirrorList
        self.cacheDir = cacheDir
        self.pkgCacheDir = os.path.join(cacheDir, "pkg")
        self.tmpDir = tmpDir

    def bootstrapPrepare(self):
        try:
            # get cached file
            cachedDataFile = None
            if os.path.exists(self.cacheDir):
                for fn in sorted(os.listdir(self.cacheDir)):
                    if re.fullmatch("archlinux-bootstrap-(.*)-x86_64.tar.gz", fn) is None:
                        continue
                    if not os.path.exists(os.path.join(self.cacheDir, fn + ".sig")):
                        continue
                    cachedDataFile = fn

            # select mirror
            mr = None
            if len(self.mirrorList) == 0:
                if cachedDataFile is not None:
                    dataFile = cachedDataFile
                    signFile = cachedDataFile + ".sig"
                    return False
                else:
                    raise Exception("no Arch Linux mirror")
            else:
                mr = self.mirrorList[0]

            # get remote file
            dataFile = None
            signFile = None
            if True:
                url = "%s/iso/latest" % (mr)
                with urllib.request.urlopen(url, timeout=robust_layer.TIMEOUT) as resp:
                    root = lxml.html.parse(resp)
                    for link in root.xpath(".//a"):
                        fn = os.path.basename(link.get("href"))
                        if re.fullmatch("archlinux-bootstrap-(.*)-x86_64.tar.gz", fn) is not None:
                            dataFile = fn
                            signFile = fn + ".sig"

            # changed?
            return (cachedDataFile != dataFile)
        finally:
            self.dataFile = dataFile
            self.signFile = signFile
            self.bootstrapDir = os.path.join(self.tmpDir, "bootstrap")
            self.rootfsDir = os.path.join(self.tmpDir, "airootfs")

    def bootstrapDownload(self):
        os.makedirs(self.cacheDir, exist_ok=True)
        mr = self.mirrorList[0]
        FmUtil.wgetDownload("%s/iso/latest/%s" % (mr, self.dataFile), os.path.join(self.cacheDir, self.dataFile))
        FmUtil.wgetDownload("%s/iso/latest/%s" % (mr, self.signFile), os.path.join(self.cacheDir, self.signFile))

    def bootstrapExtract(self):
        os.makedirs(self.tmpDir, exist_ok=True)
        FmUtil.cmdCall("/bin/tar", "-xzf", os.path.join(self.cacheDir, self.dataFile), "-C", self.tmpDir)
        robust_layer.simple_fops.rm(self.bootstrapDir)
        os.rename(os.path.join(self.tmpDir, "root.x86_64"), self.bootstrapDir)

    def createRootfs(self, initcpioHooksDir=None, pkgList=[], localPkgFileList=[], fileList=[], cmdList=[]):
        robust_layer.simple_fops.rm(self.rootfsDir)
        os.mkdir(self.rootfsDir)

        os.makedirs(self.pkgCacheDir, exist_ok=True)

        # copy resolv.conf
        FmUtil.cmdCall("/bin/cp", "-L", "/etc/resolv.conf", os.path.join(self.bootstrapDir, "etc"))

        # modify mirror
        with open(os.path.join(self.bootstrapDir, "etc", "pacman.d", "mirrorlist"), "w") as f:
            for mr in self.mirrorList:
                f.write("Server = %s/$repo/os/$arch\n" % (mr))

        # initialize, add packages
        mountList = DirListMount.standardDirList(self.bootstrapDir)
        tstr = os.path.join(self.bootstrapDir, "var", "cache", "pacman", "pkg")
        mountList.append((tstr, "--bind %s %s" % (self.pkgCacheDir, tstr)))
        tstr = os.path.join(self.bootstrapDir, "mnt")
        mountList.append((tstr, "--bind %s %s" % (self.rootfsDir, tstr)))     # mount rootfs directory as /mnt
        with DirListMount(mountList):
            # prepare pacman
            FmUtil.cmdCall("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacman-key", "--init")
            FmUtil.cmdCall("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacman-key", "--populate", "archlinux")

            # install basic system files
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "base")
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "lvm2")

            # install mkinitcpio and modify it's configuration
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "mkinitcpio")
            if initcpioHooksDir is not None:
                # copy /etc/mkinitcpio/hooks files
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "hooks", "*")):
                    dstFn = os.path.join(self.rootfsDir, "etc", "initcpio", "hooks", os.path.basename(fullfn))
                    shutil.copy(fullfn, dstFn)
                    os.chmod(dstFn, 0o644)

                # record after information
                afterDict = dict()
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "install", "*.after")):
                    fn = os.path.basename(fullfn)
                    name = fn.split(".")[0]
                    afterDict[name] = pathlib.Path(fullfn).read_text().rstrip("\n")

                # copy /etc/mkinitcpio/install files
                # add hook to /etc/mkinitcpio.conf
                confFile = os.path.join(self.rootfsDir, "etc", "mkinitcpio.conf")
                self._removeMkInitcpioHook(confFile, "fsck")
                self._addMkInitcpioHook(confFile, "lvm2", "block")
                for fullfn in glob.glob(os.path.join(initcpioHooksDir, "install", "*")):
                    if fullfn.endswith(".after"):
                        continue
                    name = os.path.basename(fullfn)
                    dstFn = os.path.join(self.rootfsDir, "etc", "initcpio", "install", name)
                    shutil.copy(fullfn, dstFn)
                    os.chmod(dstFn, 0o644)
                    self._addMkInitcpioHook(confFile, name, afterDict.get(name))

            # install linux kernel
            FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", "linux-lts")

            # install packages
            for pkg in pkgList:
                FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "/mnt", pkg)

            # install packages from local repository
            for fullfn in localPkgFileList:
                fn = os.path.basename(fullfn)
                dstFn = os.path.join(self.bootstrapDir, "var", "cache", "pacman", "pkg", fn)
                shutil.copy(fullfn, dstFn)
                try:
                    fn2 = os.path.join("/var", "cache", "pacman", "pkg", fn)
                    FmUtil.cmdExec("/usr/bin/chroot", self.bootstrapDir,  "/sbin/pacstrap", "-c", "-U", "/mnt", fn2)
                finally:
                    os.remove(dstFn)

        # add files
        for fullfn, mode, dstDir in fileList:
            assert dstDir.startswith("/")
            dstDir = self.rootfsDir + dstDir
            dstFn = os.path.join(dstDir, os.path.basename(fullfn))
            os.makedirs(dstDir, exist_ok=True)
            shutil.copy(fullfn, dstFn)
            os.chmod(dstFn, mode)

        # exec custom script
        for cmd in cmdList:
            FmUtil.shellCall("/usr/bin/chroot %s %s" % (self.rootfsDir, cmd))

    def squashRootfs(self, rootfsDataFile, rootfsMd5File, kernelFile, initcpioFile):
        assert rootfsDataFile.startswith("/")
        assert rootfsMd5File.startswith("/")
        assert kernelFile.startswith("/")
        assert initcpioFile.startswith("/")

        FmUtil.cmdCall("/bin/mv", os.path.join(self.rootfsDir, "boot", "vmlinuz-linux-lts"), kernelFile)
        FmUtil.cmdCall("/bin/mv", os.path.join(self.rootfsDir, "boot", "initramfs-linux-lts-fallback.img"), initcpioFile)
        shutil.rmtree(os.path.join(self.rootfsDir, "boot"))

        FmUtil.cmdExec("/usr/bin/mksquashfs", self.rootfsDir, rootfsDataFile, "-no-progress", "-noappend", "-quiet")
        with TempChdir(os.path.dirname(rootfsDataFile)):
            FmUtil.shellExec("/usr/bin/sha512sum \"%s\" > \"%s\"" % (os.path.basename(rootfsDataFile), rootfsMd5File))

    def clean(self):
        robust_layer.simple_fops.rm(self.rootfsDir)
        robust_layer.simple_fops.rm(self.bootstrapDir)
        del self.rootfsDir
        del self.bootstrapDir
        del self.signFile
        del self.dataFile

    def _addMkInitcpioHook(self, confFile, name, after=None):
        buf = pathlib.Path(confFile).read_text()
        hookList = re.search("^HOOKS=\\((.*)\\)", buf, re.M).group(1).split(" ")
        assert name not in hookList
        if after is not None:
            try:
                i = hookList.index(after)
                hookList.insert(i + 1, name)
            except ValueError:
                hookList.append(name)
        else:
            hookList.append(name)
        with open(confFile, "w") as f:
            f.write(re.sub("^HOOKS=\\(.*\\)", "HOOKS=(%s)" % (" ".join(hookList)), buf, 0, re.M))

    def _removeMkInitcpioHook(self, confFile, name):
        buf = pathlib.Path(confFile).read_text()
        hookList = re.search("^HOOKS=\\((.*)\\)", buf, re.M).group(1).split(" ")
        if name in hookList:
            hookList.remove(name)
            with open(confFile, "w") as f:
                f.write(re.sub("^HOOKS=\\(.*\\)", "HOOKS=(%s)" % (" ".join(hookList)), buf, 0, re.M))



# class Stage4GentooSnapshot(gstage4.ManualSyncRepository):

#     """modify git-r3.eclass to use /usr/libexec/robust_layer/git"""

#     def __init__(self, filepath):
#         self._path = filepath

#     def get_name(self):
#         return "gentoo"

#     def get_datadir_path(self):
#         return "/var/db/repos/gentoo"

#     def sync(self, datadir_hostpath):
#         FmUtil.cmdCall("/usr/bin/unsquashfs", "-f", "-q", "-n", "-d", datadir_hostpath, self._path)
#         FmUtil.cmdCall("/bin/sed -i 's#git fetch#/usr/libexec/robust_layer/git fetch#' %s" % (os.path.join(datadir_hostpath, "eclass", "git-r3.eclass")))



            # scriptList = []
            # if True:
            #     hostp = "/var/cache/bbki/distfiles/git-src/git/bcachefs.git"
            #     if not os.path.isdir(hostp):
            #         raise Exception("directory \"%s\" does not exist in host system" % (hostp))
            #     s = gstage4.scripts.PlacingFilesScript("Install bcachefs kernel")
            #     s.append_dir("/usr")
            #     s.append_dir("/usr/src")
            #     s.append_host_dir("/usr/src/linux-%s-bcachefs" % (FmUtil.getKernelVerStr(hostp)), hostp, dmode=0o755, fmode=0o755)    # script files in kernel source needs to be executable, simply make all files rwxrwxrwx
            #     scriptList.append(s)
            # if True:
            #     buf = ""
            #     buf += TMP_DOT_CONFIG
            #     buf += "\n"
            #     buf += "CONFIG_BCACHEFS_FS=y\n"
            #     buf += "CONFIG_BCACHEFS_QUOTA=y\n"
            #     buf += "CONFIG_BCACHEFS_POSIX_ACL=y\n"
            #     s = gstage4.scripts.PlacingFilesScript("Install bcachefs kernel config file")
            #     s.append_dir("/usr")
            #     s.append_dir("/usr/src")
            #     s.append_file("/usr/src/dot-config", buf)
            #     scriptList.append(s)




    def get_stats(self, name):
        if name in ["cache_hit_ratio_five_minute", "cache_hit_ratio_hour", "cache_hit_ratio_day", "cache_hit_ratio_total"]:
            name = name.replace("cache_hit_ratio_", "")
            ret = 0
            for cacheDev in self._cacheDevSet:
                fullfn = os.path.join("/sys", "fs", "bcache", BcacheUtil.getSetUuid(cacheDev), "stats_%s" % (name), "cache_hit_ratio")
                ret += int(pathlib.Path(fullfn).read_text().rstrip("\n"))
            return ret / len(self._cacheDevSet) / 100
        else:
            assert False

