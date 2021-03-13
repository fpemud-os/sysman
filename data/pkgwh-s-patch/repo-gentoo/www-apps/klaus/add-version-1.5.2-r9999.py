
#!/usr/bin/python3
# -*- coding: utf-8; tab-width: 4; indent-tabs-mode: t -*-

import os
import subprocess

if os.path.exists("klaus-1.5.2.ebuild"):
    with open("klaus-1.5.2-r9999.ebuild", "w") as f:
        f.write("""
# Copyright 1999-2020 Gentoo Authors
# Distributed under the terms of the GNU General Public License v2

# This ebuild is here because we need the not-released namespace feature
# This ebuild should be removed after klaus-1.5.3 is released

EAPI=7

PYTHON_COMPAT=( python3_{6,7,8,9} )

inherit distutils-r1 git-r3

DESCRIPTION="A simple, easy-to-set-up Git web viewer"
HOMEPAGE="https://github.com/jonashaag/klaus/"
EGIT_REPO_URI="https://github.com/jonashaag/klaus.git"

LICENSE="ISC"
SLOT="0"
KEYWORDS="~amd64 ~x86"
IUSE="ctags"

RDEPEND="
	>=dev-python/dulwich-0.19.3[${PYTHON_USEDEP}]
	dev-python/flask[${PYTHON_USEDEP}]
	dev-python/httpauth[${PYTHON_USEDEP}]
	dev-python/humanize[${PYTHON_USEDEP}]
	dev-python/pygments[${PYTHON_USEDEP}]
	dev-python/six[${PYTHON_USEDEP}]
	ctags? ( dev-python/python-ctags[${PYTHON_USEDEP}] )
"

# The tests can only be run from a git repository
# so they are not included in the source distributions

python_install_all() {
	distutils-r1_python_install_all
	doman ${PN}.1
}
""")
    subprocess.run(["ebuild", "klaus-1.5.2-r9999.ebuild", "manifest"], stdout=subprocess.DEVNULL)
else:
    print("outdated")
