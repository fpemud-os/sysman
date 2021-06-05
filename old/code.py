
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
