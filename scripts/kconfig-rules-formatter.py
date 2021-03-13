#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import re

scriptDir = os.path.dirname(os.path.realpath(__file__))
dataFile = os.path.normpath(os.path.join(scriptDir, "../data/kconfig.rules"))

lineList = None
with open(dataFile, "r") as f:
    lineList = f.read().split("\n")

# remove trailing spaces
for i in range(0, len(lineList)):
    line = lineList[i]
    line = line.rstrip()
    lineList[i] = line

# ensure title is of length 80
for i in range(0, len(lineList)):
    line = lineList[i]
    if not line.startswith("##"):
        continue
    if re.fullmatch("## .* #+", line) is None:
        raise Exception("illegal title at line %d" % (i))
    if len(line) > 80:
        line = line[:80]
        if re.fullmatch("## .* #+", line) is None:
            raise Exception("illegal title at line %d" % (i))
    elif len(line) < 80:
        for j in range(len(line), 80):
            line += "#"
    lineList[i] = line

# ensure 3 empty lines before title
for i in range(0, len(lineList)):
    line = lineList[i]
    if not line.startswith("##"):
        continue
    if i == 0:
        continue
    c = 0
    while i - 1 - c >= 0 and lineList[i - 1 - c] == "":
        c = c + 1
    if c == i:
        lineList = lineList[i:]
        i = 1
    if c > 3:
        for j in range(0, c - 3):
            lineList.pop(i - 1)
            i = i - 1
    elif c < 3:
        for j in range(0, 3 - c):
            lineList.insert(i, "")
            i = i + 1

# ensure 1 empty line after title
for i in range(0, len(lineList)):
    line = lineList[i]
    if not line.startswith("##"):
        continue
    if i == len(lineList) - 1 or lineList[i + 1] != "":
        lineList.insert(i + 1, "")

# remove trailing empty lines
for i in range(len(lineList) - 1, 0, -1):
    if lineList[i] == "":
        lineList.pop(i)
    else:
        break

with open(dataFile, "w") as f:
    f.write("\n".join(lineList))
