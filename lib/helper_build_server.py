#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import json
import socket
import struct
import tempfile
import subprocess
from OpenSSL import SSL
from fm_util import FmUtil
from fm_util import AvahiServiceBrowser
from fm_param import FmConst


class BuildServerSelector:

    @staticmethod
    def hasBuildServerCfgFile():
        return os.path.exists(FmConst.buildServerConfFile)

    @staticmethod
    def selectBuildServer():
        bForce, bAutoDiscover, serverList = BuildServerSelector._getVariables()

        ret = BuildServerSelector._selectBuildServer(bForce, bAutoDiscover, serverList)
        if ret is None:
            ss = "No build server defined, fallback to normal process."
            if bAutoDiscover:
                ss = ss.replace("d,", "d or discovered,")
            print(ss)
            return None
        name, server, bForce = ret

        if ":" in server:
            ip = server.split(":")[0]
            ctrlPort = int(server.split(":")[1])
        else:
            ip = server
            ctrlPort = FmConst.buildServerDefaultPort

        buildServer = BuildServer(ip, ctrlPort)
        buildServer.checkCertKey()
        try:
            buildServer.connectAndInit()
            print("Use build server \"%s\"." % (name))
            return buildServer
        except:
            if not bForce:
                print("Failed to use build server \"%s\", fallback to normal process." % (name))
                return None                             # fail
            else:
                raise                                   # fail

    def _getVariables():
        # get variables
        bForce = False
        bAutoDiscover = False
        serverList = []
        with open(FmConst.buildServerConfFile, 'r') as f:
            lineList = f.read().split()
            for i in range(0, len(lineList)):
                line = lineList[i].strip()
                if line == "" or line.startswith("#"):
                    continue

                m = re.search("^FORCE=(.*)$", line)
                if m is not None and m.group(1).lower() in ["true", "1"]:
                    bForce = True
                    continue

                m = re.search("^AUTO_DISCOVER=(.*)$", line)
                if m is not None and m.group(1).lower() in ["true", "1"]:
                    bAutoDiscover = True
                    continue

                m = re.search("^BUILD_SERVER=(.*)$", line)
                if m is not None:
                    serverList = m.group(1).split()
                    continue

                raise Exception("invalid content at line %d in %s" % (i + 1, FmConst.buildServerConfFile))

        return (bForce, bAutoDiscover, serverList)

    def _selectBuildServer(bForce, bAutoDiscover, serverList):
        # we prefer static configured build servers
        if serverList != []:
            return (serverList[0], serverList[0], bForce)

        # discover build server
        if bAutoDiscover:
            browser = AvahiServiceBrowser("_syncup_gentoo._tcp")
            browser.run()
            for name, addr, port in browser.get_result_list():
                return (name, "%s:%d" % (addr, port), bForce)

        # no build server found
        if bForce:
            raise Exception("no build server available")
        return None


class BuildServer:

    def __init__(self, server, ctrlPort):
        self.hostname = server
        self.ctrlPort = ctrlPort

        self.sock = None
        self.sslSock = None

        self.wSshPort = None
        self.wSshKey = None
        self.wRsyncPort = None
        self.wCatFilePort = None

    def getHostname(self):
        return self.hostname

    def getCtrlPort(self):
        return self.ctrlPort

    def checkCertKey(self):
        if not os.path.exists(FmConst.myCertFile) or not os.path.exists(FmConst.myPrivKeyFile):
            raise Exception("%s or %s does not exist" % (FmConst.myCertFile, FmConst.myPrivKeyFile))

    def connectAndInit(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.hostname, self.ctrlPort))

            ctx = SSL.Context(SSL.TLSv1_2_METHOD)
            ctx.use_certificate_file(FmConst.myCertFile)
            ctx.use_privatekey_file(FmConst.myPrivKeyFile)
            self.sslSock = SSL.Connection(ctx, self.sock)
            self.sslSock.set_connect_state()

            self._sendRequestObj({
                "command": "init",
                "hostname": socket.gethostname(),
                "cpu-arch": FmUtil.getCpuArch(),
                "cpu-model": FmUtil.getCpuModel(),
                "plugin": "gentoo",
            })
            resp = self._recvReponseObj()
            if "error" in resp:
                raise Exception(resp["error"])
        except:
            self.dispose()
            raise

    def dispose(self):
        self.wSshPort = None
        self.wSshKey = None
        self.wRsyncPort = None
        self.wCatFilePort = None
        if self.sslSock is not None:
            self.sslSock.close()
            self.sslSock = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.ctrlPort = None
        self.hostname = None

    def syncUp(self):
        # enter stage
        self._sendRequestObj({
            "command": "stage-syncup",
        })
        resp = self._recvReponseObj()
        if "error" in resp:
            raise Exception(resp["error"])
        assert resp["return"]["stage"] == "syncup"

        # rsync
        stunnelCfgFile, newPort, proc = self._createStunnelProcess(resp["return"]["rsync-port"])
        try:
            cmd = ""
            cmd += "/usr/bin/rsync -a -z -hhh --delete --delete-excluded --partial --info=progress2 "
            for fn in self._ignoredPatternsWhenSyncUp():
                cmd += "-f '- %s' " % (fn)
            cmd += "-f '+ /bin' "                                       # /bin may be a symlink or directory
            cmd += "-f '+ /bin/***' "
            cmd += "-f '+ /boot/***' "
            cmd += "-f '+ /etc/***' "
            cmd += "-f '+ /lib' "                                       # /lib may be a symlink or directory
            cmd += "-f '+ /lib/***' "
            cmd += "-f '+ /lib32' "                                     # /lib32 may be a symlink or directory
            cmd += "-f '+ /lib32/***' "
            cmd += "-f '+ /lib64' "                                     # /lib64 may be a symlink or directory
            cmd += "-f '+ /lib64/***' "
            cmd += "-f '+ /opt/***' "
            cmd += "-f '+ /sbin' "                                      # /sbin may be a symlink or directory
            cmd += "-f '+ /sbin/***' "
            cmd += "-f '+ /usr/***' "
            cmd += "-f '+ /var' "
            cmd += "-f '+ /var/cache' "
            cmd += "-f '+ /var/cache/edb/***' "
            cmd += "-f '+ /var/cache/portage/***' "
            cmd += "-f '+ /var/db' "
            cmd += "-f '+ /var/db/pkg/***' "
            cmd += "-f '+ /var/lib' "
            cmd += "-f '+ /var/lib/portage/***' "
            cmd += "-f '- /**' "
            cmd += "/ rsync://127.0.0.1:%d/main" % (newPort)
            FmUtil.shellExec(cmd)
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def startWorking(self):
        self._sendRequestObj({
            "command": "stage-working",
        })
        resp = self._recvReponseObj()
        if "error" in resp:
            raise Exception(resp["error"])
        assert resp["return"]["stage"] == "working"

        self.wSshPort = resp["return"]["ssh-port"]
        self.wSshKey = resp["return"]["ssh-key"]
        self.wRsyncPort = resp["return"]["rsync-port"]
        self.wCatFilePort = resp["return"]["catfile-port"]

    def sshExec(self, cmd):
        assert self.wSshPort is not None

        identityFile = tempfile.mktemp()
        cfgFile = tempfile.mktemp()
        try:
            with open(identityFile, "w") as f:
                f.write(self.wSshKey)
            os.chmod(identityFile, 0o600)

            buf = ""
            buf += "LogLevel QUIET\n"
            buf += "\n"
            buf += "KbdInteractiveAuthentication no\n"
            buf += "PasswordAuthentication no\n"
            buf += "PubkeyAuthentication yes\n"
            buf += "PreferredAuthentications publickey\n"
            buf += "\n"
            buf += "IdentityFile %s\n" % (identityFile)
            buf += "UserKnownHostsFile /dev/null\n"
            buf += "StrictHostKeyChecking no\n"
            buf += "\n"
            buf += "SendEnv LANG LC_*\n"
            with open(cfgFile, "w") as f:
                f.write(buf)

            # "-t" can get Ctrl+C controls remote process
            # XXXXX so that we forward signal to remote process, FIXME
            cmd = "/usr/bin/ssh -t -e none -p %d -F %s %s %s" % (self.wSshPort, cfgFile, self.hostname, cmd)
            FmUtil.shellExec(cmd)
        finally:
            os.unlink(cfgFile)
            os.unlink(identityFile)

    def getFile(self, filename):
        assert self.wSshPort is not None

        stunnelCfgFile, newPort, proc = self._createStunnelProcess(self.wCatFilePort)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(("127.0.0.1", newPort))
                sock.sendall(struct.pack("!I", len(filename.encode("utf-8"))))
                sock.sendall(filename.encode("utf-8"))
                errCode = struct.unpack("!c", self._sockRecvAll(sock, 1))[0]
                dataLen = struct.unpack("!Q", self._sockRecvAll(sock, 8))[0]
                data = self._sockRecvAll(sock, dataLen)
                if errCode != b'\x00':
                    raise Exception(data.decode("utf-8"))
                return data
            finally:
                sock.close()
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def syncDownKernel(self):
        assert self.wSshPort is not None

        stunnelCfgFile, newPort, proc = self._createStunnelProcess(self.wRsyncPort)
        try:
            cmd = ""
            cmd += "/usr/bin/rsync -a -z -hhh --delete --info=progress2 "
            cmd += "-f '+ /boot' "
            cmd += "-f '+ /boot/config-*' "
            cmd += "-f '+ /boot/initramfs-*' "
            cmd += "-f '+ /boot/kernel-*' "
            cmd += "-f '+ /boot/System.map-*' "
            cmd += "-f '+ /boot/history/***' "
            cmd += "-f '+ /lib' "
            cmd += "-f '+ /lib/modules/***' "
            cmd += "-f '+ /lib/firmware/***' "
            cmd += "-f '- /**' "
            cmd += "rsync://127.0.0.1:%d/main /" % (newPort)
            FmUtil.shellExec(cmd)
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def syncDownSystem(self):
        assert self.wSshPort is not None

        stunnelCfgFile, newPort, proc = self._createStunnelProcess(self.wRsyncPort)
        try:
            cmd = ""
            cmd += "/usr/bin/rsync -a -z -hhh --delete --info=progress2 "
            for fn in self._ignoredPatternsWhenSyncDown():
                cmd += "-f '- %s' " % (fn)
            cmd += "-f '+ /bin' "                                       # /bin may be a symlink or directory
            cmd += "-f '+ /bin/***' "
            cmd += "-f '+ /etc/***' "
            cmd += "-f '+ /lib' "                                       # /lib may be a symlink or directory
            cmd += "-f '+ /lib/***' "
            cmd += "-f '+ /lib32' "                                     # /lib may be a symlink or directory
            cmd += "-f '+ /lib32/***' "
            cmd += "-f '+ /lib64' "                                     # /lib may be a symlink or directory
            cmd += "-f '+ /lib64/***' "
            cmd += "-f '+ /opt/***' "
            cmd += "-f '+ /sbin' "                                      # /sbin may be a symlink or directory
            cmd += "-f '+ /sbin/***' "
            cmd += "-f '+ /usr/***' "
            cmd += "-f '+ /var' "
            cmd += "-f '+ /var/cache' "
            cmd += "-f '+ /var/cache/edb/***' "
            cmd += "-f '+ /var/cache/portage/***' "
            cmd += "-f '+ /var/db' "
            cmd += "-f '+ /var/db/pkg/***' "
            cmd += "-f '+ /var/lib' "
            cmd += "-f '+ /var/lib/portage/***' "
            cmd += "-f '- /**' "
            cmd += "rsync://127.0.0.1:%d/main /" % (newPort)
            FmUtil.shellExec(cmd)
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def syncDownDirectory(self, dirname, quiet=False):
        assert self.wSshPort is not None
        assert dirname.startswith("/")

        dirname = os.path.realpath(dirname)
        stunnelCfgFile, newPort, proc = self._createStunnelProcess(self.wRsyncPort)
        try:
            cmd = ""
            cmd += "/usr/bin/rsync -a -z -hhh --delete %s " % ("--quiet" if quiet else "--info=progress2")
            for fn in self._ignoredPatternsWhenSyncDown():
                cmd += "-f '- %s' " % (fn)
            if True:
                buf = "-f '+ %s/***' " % (dirname)
                dirname = os.path.dirname(dirname)
                while dirname != "/":
                    buf = "-f '+ %s' " % (dirname) + buf
                    dirname = os.path.dirname(dirname)
                cmd += buf
            cmd += "-f '- /**' "
            cmd += "rsync://127.0.0.1:%d/main /" % (newPort)
            FmUtil.shellExec(cmd)
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def syncDownWildcardList(self, wildcardList, quiet=False):
        assert self.wSshPort is not None
        assert [x.startswith("/") for x in wildcardList]

        stunnelCfgFile, newPort, proc = self._createStunnelProcess(self.wRsyncPort)
        try:
            cmd = ""
            cmd += "/usr/bin/rsync -a -z -hhh --delete %s " % ("--quiet" if quiet else "--info=progress2")
            for fn in self._ignoredPatternsWhenSyncDown():
                cmd += "-f '- %s' " % (fn)
            for wildcard in wildcardList:
                buf = "-f '+ %s' " % (wildcard)
                dirname = os.path.dirname(wildcard)
                while dirname != "/":
                    buf = "-f '+ %s' " % (dirname) + buf
                    dirname = os.path.dirname(dirname)
                cmd += buf
            cmd += "-f '- /**' "
            cmd += "rsync://127.0.0.1:%d/main /" % (newPort)
            FmUtil.shellExec(cmd)
        finally:
            proc.terminate()
            proc.wait()
            os.unlink(stunnelCfgFile)

    def _ignoredPatternsWhenSyncUp(self):
        return [
            FmConst.buildServerConfFile,
            FmConst.myCertFile,
            FmConst.myPrivKeyFile,
        ]

    def _ignoredPatternsWhenSyncDown(self):
        return self._ignoredPatternsWhenSyncUp() + [
            FmConst.portageCfgMakeConf,
            FmConst.portageMirrorsFile,
            "/etc/resolv.conf",
        ]

    def _createStunnelProcess(self, port):
        stunnelCfgFile = tempfile.mktemp()
        newPort = FmUtil.getFreeTcpPort()
        try:
            buf = ""
            buf += "cert = %s\n" % (FmConst.myCertFile)
            buf += "key = %s\n" % (FmConst.myPrivKeyFile)
            buf += "\n"
            buf += "client = yes\n"
            buf += "foreground = yes\n"
            buf += "\n"
            buf += "[rsync]\n"
            buf += "accept = %d\n" % (newPort)
            buf += "connect = %s:%d\n" % (self.hostname, port)
            with open(stunnelCfgFile, "w") as f:
                f.write(buf)

            proc = subprocess.Popen("/usr/sbin/stunnel %s 2>/dev/null" % (stunnelCfgFile), shell=True)
            FmUtil.waitTcpService("0.0.0.0", newPort)

            return (stunnelCfgFile, newPort, proc)
        except:
            os.unlink(stunnelCfgFile)
            raise

    def _sendRequestObj(self, requestObj):
        s = json.dumps(requestObj) + "\n"
        self.sslSock.send(s.encode("iso8859-1"))

    def _recvReponseObj(self):
        buf = b''
        while True:
            buf += self.sslSock.recv(4096)
            i = buf.find(b'\n')
            if i >= 0:
                assert i == len(buf) - 1
                return json.loads(buf[:i].decode("iso8859-1"))

    def _sockRecvAll(self, sock, datasize):
        buf = b''
        while len(buf) < datasize:
            buf2 = sock.recv(datasize - len(buf))
            if len(buf2) == 0:
                raise EOFError()
            buf += buf2
        return buf
