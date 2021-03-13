#!/bin/bash

ROOTDIR=$(realpath $(dirname $(realpath "$0"))/..)
FILES="${ROOTDIR}/sysman"
FILES="${FILES} $(find ${ROOTDIR}/lib -name '*.py' | tr '\n' ' ')"
FILES="${FILES} $(find ${ROOTDIR}/libexec -name '*.py' | tr '\n' ' ')"
ERRFLAG=0

OUTPUT=`pyflakes ${FILES} 2>&1`
if [ -n "$OUTPUT" ] ; then
    echo "pyflake errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

OUTPUT=`pycodestyle ${FILES} | grep -Ev "E402|E501|E722"`
if [ -n "$OUTPUT" ] ; then
    echo "pep8 errors:"
    echo "$OUTPUT"
    echo ""
    ERRFLAG=1
fi

if [ "${ERRFLAG}" == 1 ] ; then
    exit 1
fi
