#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-


import bbki
from fm_param import FmConst


class FmBbkiWrapper:

    def __init__(self, param):
        self.param = param
        self.bbki = bbki.Bbki(bbki.EtcDirConfig(FmConst.portageCfgDir))