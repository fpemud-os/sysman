#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re
import hashlib
import binascii
# from gi.repository import Secret
from fm_util import FmUtil


class WinprSamFile:

    def __init__(self):
        self.filename = "/etc/winpr/SAM"
        self.lineList = []

    def hasUser(self, username):
        self._load()
        for line in self.lineList:
            if line.split(":")[0] == username:
                return True
        return False

    def setUser(self, username, password):
        """deal with both add and modify"""

        self._load()
        pwdhash = binascii.hexlify(hashlib.new('md4', password.encode('utf-16le')).digest()).decode('ascii')
        found = False
        for i in range(0, len(self.lineList)):
            line = self.lineList[i]
            if line.split(":")[0] == username:
                found = True
                break
        if found:
            clist = self.lineList[i].split(":")
            clist[3] = pwdhash
            self.lineList[i] = ":".join(clist)
        else:
            line = "%s:::%s:::" % (username, pwdhash)
            self.lineList.append(line)
        self._save()

    def removeUser(self, username):
        """do nothing if the user doesn't exist"""

        self._load()
        found = False
        for i in range(0, len(self.lineList)):
            line = self. lineList[i]
            if line.split(":")[0] == username:
                found = True
                break
        if found:
            del self.lineList[i]
            self._save()

    def _load(self):
        self.lineList = []
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                for line in f:
                    self.lineList.append(line[:-1])

    def _save(self):
        if not os.path.exists(self.filename) and len(self.lineList) == 0:
            return
        FmUtil.ensureAncesterDir(self.filename)
        with open(self.filename, "w") as f:
            for line in self.lineList:
                f.write(line + "\n")


class SambaPassdbFile:

    def __init__(self):
        self.filename = "/var/lib/samba/private/passdb.tdb"
        if not os.path.exists("/usr/bin/pdbedit") or not os.path.exists("/usr/bin/tdbtool"):
            self.filename = None              # samba is not installed
        if not os.path.exists("/etc/samba/smb.conf"):
            self.filename = None              # samba is not being used

    def hasUser(self, username):
        if self.filename is None:
            return False
        if not os.path.exists(self.filename):
            return False
        ret = FmUtil.cmdCall("/usr/bin/pdbedit", "-d", "0", "-b", "tdbsam:%s" % (self.filename), "-L")
        return re.search("^%s:[0-9]+:$" % (username), ret, re.M) is not None

    def setUser(self, username, password):
        """deal with both add and modify"""

        if self.filename is None:
            return

        if not os.path.exists(self.filename):
            self._tdbFileCreate()

        inStr = ""
        inStr += "%s\n" % (password)
        inStr += "%s\n" % (password)
        FmUtil.cmdCallWithInput("/usr/bin/pdbedit", inStr, "-d", "0", "-b", "tdbsam:%s" % (self.filename), "-a", username, "-t")

    def removeUser(self, username):
        """do nothing if the user doesn't exist"""

        if not self.hasUser(username):
            return
        FmUtil.cmdCall("/usr/bin/pdbedit", "-d", "0", "-b", "tdbsam:%s" % (self.filename), "-x", username)

    def _tdbFileCreate(self):
        FmUtil.ensureAncesterDir(self.filename)
        inStr = ""
        inStr += "create %s\n" % (self.filename)
        inStr += "quit\n"
        FmUtil.cmdCallWithInput("/usr/bin/tdbtool", inStr)


class FpemudVpnServerAccountFile:

    def __init__(self):
        if os.path.exists("/usr/sbin/fpemud-vpn-server"):
            self.filename = "/var/lib/fpemud-vpn-server/passdb.conf"
        else:
            self.filename = None              # fpemud-vpn-server is not installed
        self.lineList = []

    def hasUser(self, username):
        if self.filename is None:
            return False
        if not os.path.exists(self.filename):
            return False

        self._load()
        for line in self.lineList:
            if line.split(":")[0] == username:
                return True
        return False

    def setUser(self, username, password):
        """deal with both add and modify"""

        if self.filename is None:
            return

        self._load()
        found = False
        for i in range(0, len(self.lineList)):
            line = self.lineList[i]
            if line.split(":")[0] == username:
                found = True
                break
        if found:
            self.lineList[i] = username + ":" + password
        else:
            self.lineList.append(username + ":" + password)
        self._save()

    def removeUser(self, username):
        """do nothing if the user doesn't exist"""

        if not self.hasUser(username):
            return

        self._load()
        found = False
        for i in range(0, len(self.lineList)):
            line = self. lineList[i]
            if line.split(":")[0] == username:
                found = True
                break
        if found:
            del self.lineList[i]
            self._save()

    def _load(self):
        self.lineList = []
        if os.path.exists(self.filename):
            with open(self.filename, "r") as f:
                for line in f:
                    self.lineList.append(line[:-1])

    def _save(self):
        if not os.path.exists(self.filename) and len(self.lineList) == 0:
            return
        FmUtil.ensureAncesterDir(self.filename)
        with open(self.filename, "w") as f:
            for line in self.lineList:
                f.write(line + "\n")
