#!/usr/bin/env bash
epydoc --html netconf sshutil paramiko netconf-gw/* -o doc -v --graph classtree  --inheritance listed --graph all
