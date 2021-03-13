#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import pwd
import grp
import getpass
import strict_pgs
from fm_util import FmUtil
from fm_param import FmConst
from helper_user_cfg import WinprSamFile
from helper_user_cfg import SambaPassdbFile


class FmUserManager:

    def __init__(self, param):
        self.param = param

    def addUser(self, username):
        winprSamFile = WinprSamFile()
        sambaPassdbFile = SambaPassdbFile()

        if FmUtil.unixHasUser(username):
            raise Exception("user already exists")
        if FmUtil.unixHasGroup(username):
            raise Exception("per-user group exists, please use \"sysman remove-user %s\" first" % (username))
        if winprSamFile.hasUser(username):
            raise Exception("duplicate user in %s, please use \"sysman remove-user %s\" first" % (winprSamFile, username))
        if sambaPassdbFile.hasUser(username):
            raise Exception("duplicate user in %s, please use \"sysman remove-user %s\" first" % (sambaPassdbFile, username))
        if os.path.exists("/home/%s" % (username)):
            raise Exception("home directory exists, please use \"sysman remove-user %s\" first" % (username))

        passwd = FmConst.userDefaultPassword

        with strict_pgs.PasswdGroupShadow(readOnly=False, msrc="fpemud-os") as pgs:
            pgs.addNormalUser(username, passwd)
            pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "users")
            if "games" in pgs.getSoftwareGroupList():
                pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "games")
            if "vboxusers" in pgs.getSoftwareGroupList():
                pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "vboxusers")

        winprSamFile.setUser(username, passwd)
        sambaPassdbFile.setUser(username, passwd)

        os.mkdir("/home/%s" % (username))
        os.chown("/home/%s" % (username), pwd.getpwnam(username).pw_uid, grp.getgrnam(username).gr_gid)

        print("User added. username: %s, password: %s" % (username, passwd))

    def removeUser(self, username):
        """do nothing if the user doesn't exist
           can remove half-created user"""

        winprSamFile = WinprSamFile()
        sambaPassdbFile = SambaPassdbFile()

#        os.rmtree("/home/%s"%(username), True)            dangerous, so comment it first

        sambaPassdbFile.removeUser(username)
        winprSamFile.removeUser(username)

        with strict_pgs.PasswdGroupShadow(readOnly=False, msrc="fpemud-os") as pgs:
            pgs.removeNormalUser(username)

    def resetUserPassword(self, username):
        if not FmUtil.unixHasUser(username):
            raise Exception("user does not exist")

        winprSamFile = WinprSamFile()
        sambaPassdbFile = SambaPassdbFile()
        passwd = FmConst.userDefaultPassword

        with strict_pgs.PasswdGroupShadow(readOnly=False, msrc="fpemud-os") as pgs:
            pgs.modifyNormalUser(username, strict_pgs.MUSER_SET_PASSWORD, passwd)

        winprSamFile.setUser(username, passwd)
        sambaPassdbFile.setUser(username, passwd)

        if os.path.exists("/home/%s" % (username)):
            if os.path.exists("/home/%s/.local/share/keyring/login.keyring" % (username)):
                os.remove("/home/%s/.local/share/keyring/login.keyring" % (username))

    def flushUser(self, username):
        if not FmUtil.unixHasUser(username):
            raise Exception("user does not exist")

        winprSamFile = WinprSamFile()
        sambaPassdbFile = SambaPassdbFile()

        passwd = getpass.getpass("Password for user %s: " % (username))
        if not FmUtil.unixVerifyUserPassword(username, passwd):
            raise Exception("incorrect password")

        with strict_pgs.PasswdGroupShadow(readOnly=False, msrc="fpemud-os") as pgs:
            pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "users")
            if "games" in pgs.getSoftwareGroupList():
                pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "games")
            if "vboxusers" in pgs.getSoftwareGroupList():
                pgs.modifyNormalUser(username, strict_pgs.MUSER_JOIN_GROUP, "vboxusers")

        winprSamFile.setUser(username, passwd)
        sambaPassdbFile.setUser(username, passwd)

        if not os.path.exists("/home/%s" % (username)):
            os.mkdir("/home/%s" % (username))
        os.chown("/home/%s" % (username), pwd.getpwnam(username).pw_uid, grp.getgrnam(username).gr_gid)
