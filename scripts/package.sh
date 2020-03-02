#!/bin/sh

CWD="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR=$CWD/..

cmd=$1

cd $ROOT_DIR
pkgName=${PWD##*/}
rm -rf dist/*
python setup.py sdist
cd dist
version=`ls -1 | sed -re 's/.*-([^-]*)\.tar\.gz/\1/g'`
mkdir -p ../build/distributions
zip "../build/distributions/$pkgName-$version.zip" *.tar.gz
