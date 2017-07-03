# -*- coding: utf-8 -*-#
#
# Copyright (c) 2015, Deutsche Telekom AG.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from __future__ import absolute_import, division, unicode_literals, print_function, nested_scopes
import getpass
import logging
from .cache import SSHConnectionCache, SSHNoConnectionCache

MAXSSHBUF = 16 * 1024
g_no_cache = SSHNoConnectionCache()
g_cmd_cache = SSHConnectionCache("SSH Command Cache")
logger = logging.getLogger(__name__)


def shell_escape_single_quote (command):
    """Escape single quotes for use in a shell single quoted string
    Explanation:

    (1) End first quotation which uses single quotes.
    (2) Start second quotation, using double-quotes.
    (3) Quoted character.
    (4) End second quotation, using double-quotes.
    (5) Start third quotation, using single quotes.

    If you do not place any whitespaces between (1) and (2), or between
    (4) and (5), the shell will interpret that string as a one long word
    """
    return command.replace("'", "'\"'\"'")


class SSHConnection (object):
    """A connection to an SSH server"""
    def __init__ (self, host, port=22, username=None, password=None, debug=False, cache=None, proxycmd=None):
        if cache is None:
            cache = g_no_cache

        self.host = host
        self.port = port
        self.debug = debug
        self.cache = cache
        self.host_key = None
        self.chan = None
        self.ssh = None

        if not username:
            username = getpass.getuser()

        self.username = username

        self.ssh = cache.get_ssh_socket(host, port, username, password, debug, proxycmd)

        # Open a session.
        try:
            if self.debug:
                logger.debug("Opening SSH channel on socket (%s:%s)", self.host, str(self.port))
            self.chan = self.ssh.open_session()
        except:
            self.close()
            raise

    def __del__ (self):
        # Make sure we get rid of the cached reference to the open ssh socket
        self.close()

    def close (self):
        if hasattr(self, "chan") and self.chan:
            if self.debug:
                logger.debug("Closing SSH channel on socket (%s:%s)", self.host, str(self.port))
            self.chan.close()
            self.chan = None
        if hasattr(self, "ssh") and self.ssh:
            tmp = self.ssh
            self.ssh = None
            self.cache.release_ssh_socket(tmp, self.debug)

    def is_active (self):
        return self.chan and self.ssh and self.ssh.is_active()


class SSHSession (SSHConnection):
    def send (self, chunk):
        assert self.chan is not None
        self.chan.send(chunk)

    def sendall (self, chunk):
        assert self.chan is not None
        self.chan.sendall(chunk)

    def recv (self, size=MAXSSHBUF):
        assert self.chan is not None
        return self.chan.recv(size)

    def recv_ready (self):
        assert self.chan is not None
        return self.chan.recv_ready()

    def recv_stderr (self, size=MAXSSHBUF):
        assert self.chan is not None
        return self.chan.recv_stderr(size)

    def recv_stderr_ready (self):
        assert self.chan is not None
        return self.chan.recv_stderr_ready()


class SSHClientSession (SSHSession):
    """A client session to a host using a subsystem"""
    def __init__ (self, host, port, subsystem, username=None, password=None, debug=False, cache=None, proxycmd=None):
        super(SSHClientSession, self).__init__(host, port, username, password, debug, cache, proxycmd)
        try:
            self.chan.invoke_subsystem(subsystem)
        except:
            self.close()
            raise


class SSHCommandSession (SSHSession):
    """A client session to a host using a command i.e., like a remote pipe"""
    def __init__ (self, host, port, command, username=None, password=None, debug=False, cache=None, proxycmd=None):
        if cache is None:
            cache = g_cmd_cache
        super(SSHCommandSession, self).__init__(host, port, username, password, debug, cache, proxycmd)
        try:
            self.chan.exec_command(command)
        except:
            self.close()
            raise


__author__ = 'Christian Hopps'
__version__ = '1.0'
__docformat__ = "restructuredtext en"
