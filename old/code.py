
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
