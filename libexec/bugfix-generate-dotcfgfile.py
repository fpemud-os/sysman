#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

# it pylkc seems conflicts with some package imported by fm_util.py
# so we put it in a stand-alone process
import sys
import pylkcutil

realSrcDir = sys.argv[1]
kcfgRulesTmpFile = sys.argv[2]
dotCfgFile = sys.argv[3]
pylkcutil.generator.generate(realSrcDir, "allnoconfig+module", kcfgRulesTmpFile, output=dotCfgFile)
