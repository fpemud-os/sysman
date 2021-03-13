#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import sys
import pylkcutil


class DebugEventHandler:

    def progressChanged(self, stage):
        print("progress: " + stage)

    def symbolChanged(self, symbolName, symbolValue):
        print("symbol changed: " + symbolName + "=" + symbolValue)

    def choiceChanged(self, menuPath, choiceValue):
        print("choice change: " + menuPath + "=" + choiceValue)


if len(sys.argv) < 3:
    print("syntax: generate-dotconfig <kernel-source-directory> <rule-file>")
    sys.exit(1)

kSrcDir = sys.argv[1]
ruleFile = sys.argv[2]
bVerbose = (len(sys.argv) >= 4 and sys.argv[3] == "-v")

# bad, should move this operation into pylkcutil.generator.generate
kSrcDir = os.path.abspath(kSrcDir)
ruleFile = os.path.abspath(ruleFile)

if bVerbose:
    eventHandler = DebugEventHandler()
else:
    eventHandler = None
pylkcutil.generator.generate(kSrcDir, "allnoconfig+module", ruleFile,
                             output=os.path.join(kSrcDir, ".config"),
                             eventHandler=eventHandler)
