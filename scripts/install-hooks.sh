#!/bin/bash

if [ -e "../.git" ] ; then
    echo "Installing Git hooks..."
    ln -sf "../../scripts/git-hook-pre-commit.sh" "../.git/hooks/pre-commit"
    echo "Done."
    exit 0
fi

if [ -e "../.svn" ] ; then
    echo "Error: Unimplemented yet!"
    exit 1
fi

echo "Error: No version control system (Git, Subversion) found!"
exit 1
