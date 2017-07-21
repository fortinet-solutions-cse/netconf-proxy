#!/usr/bin/env bash
epydoc --html netconf sshutil paramiko netconf-proxy/* -o doc -v --graph classtree  --inheritance listed --graph all
