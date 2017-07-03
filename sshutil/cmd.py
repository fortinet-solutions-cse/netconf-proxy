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
import functools
import logging
import os
import subprocess
from sshutil import conn
from sshutil.cache import setup_travis

__author__ = 'Christian Hopps'
__version__ = '1.0'
__docformat__ = "restructuredtext en"

logger = logging.getLogger(__name__)


def setup_module (unused):
    setup_travis()


class CalledProcessError (subprocess.CalledProcessError):
    pass


def read_to_eof (recvmethod):
    buf = recvmethod(conn.MAXSSHBUF)
    while buf:
        yield buf
        buf = recvmethod(conn.MAXSSHBUF)


def terminal_size():
    import fcntl
    import termios
    import struct
    h, w, unused, unused = struct.unpack('HHHH', fcntl.ioctl(0,
                                                             termios.TIOCGWINSZ,
                                                             struct.pack('HHHH', 0, 0, 0, 0)))
    return w, h


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


class SSHCommand (conn.SSHConnection):
    def __init__ (self, command, host, port=22, username=None, password=None, debug=False):
        self.command = command
        self.exit_code = None
        self.output = ""
        self.error_output = ""

        super(SSHCommand, self).__init__(host, port, username, password, debug)

    def _get_pty (self):
        width, height = terminal_size()
        return self.chan.get_pty(term=os.environ['TERM'], width=width, height=height)

    def run_status_stderr (self):
        """
        Run a command over an ssh channel, return exit code, stdout and stderr.

        >>> status, output, error = SSHCommand("ls -d /etc", "localhost").run_status_stderr()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> status, output, error = SSHCommand("grep foobar doesnt-exist", "localhost").run_status_stderr()
        >>> status
        2
        >>> print(output, end="")
        >>>
        >>> print(error, end="")
        grep: doesnt-exist: No such file or directory
        """
        try:
            if isinstance(self, SSHPTYCommand):
                self._get_pty()
            self.chan.exec_command(self.command)
            self.exit_code = self.chan.recv_exit_status()

            self.output = "".join([x.decode('utf-8') for x in read_to_eof(self.chan.recv)])
            self.error_output = "".join([x.decode('utf-8')
                                         for x in read_to_eof(self.chan.recv_stderr)])

            return (self.exit_code, self.output, self.error_output)
        finally:
            self.close()

    def run_stderr (self):
        """
        Run a command over an ssh channel, return stdout and stderr,
        Raise CalledProcessError on failure

        >>> cmd = SSHCommand("ls -d /etc", "localhost")
        >>> output, error = cmd.run_stderr()
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> cmd = SSHCommand("grep foobar doesnt-exist", "localhost")
        >>> cmd.run_stderr()                                    # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        status, unused, unused = self.run_status_stderr()
        if status != 0:
            raise CalledProcessError(self.exit_code, self.command,
                                     self.error_output if self.error_output else self.output)
        return self.output, self.error_output

    def run_status (self):
        """
        Run a command over an ssh channel, return exitcode and stdout.

        >>> status, output = SSHCommand("ls -d /etc", "localhost").run_status()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> status, output = SSHCommand("grep foobar doesnt-exist", "localhost").run_status()
        >>> status
        2
        >>> print(output, end="")
        """
        return self.run_status_stderr()[0:2]

    def run (self):
        """
        Run a command over an ssh channel, return stdout.
        Raise CalledProcessError on failure.

        >>> cmd = SSHCommand("ls -d /etc", "localhost")
        >>> print(cmd.run(), end="")
        /etc
        >>> cmd = SSHCommand("grep foobar doesnt-exist", "localhost")
        >>> cmd.run()                                   # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        return self.run_stderr()[0]


class SSHPTYCommand (SSHCommand):
    """Instances of this class also obtain a PTY prior to executing the command"""

    def run_status_stderr (self):
        """
        Run a command over an ssh channel, return exit code, stdout and stderr.

        >>> status, output, error = SSHCommand("ls -d /etc", "localhost").run_status_stderr()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> status, output, error = SSHCommand("grep foobar doesnt-exist", "localhost").run_status_stderr()
        >>> status
        2
        >>> print(output, end="")
        >>>
        >>> print(error, end="")
        grep: doesnt-exist: No such file or directory
        """
        return super(SSHPTYCommand, self).run_status_stderr()

    def run_stderr (self):
        """
        Run a command over an ssh channel, return stdout and stderr,
        Raise CalledProcessError on failure

        >>> cmd = SSHCommand("ls -d /etc", "localhost")
        >>> output, error = cmd.run_stderr()
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> cmd = SSHCommand("grep foobar doesnt-exist", "localhost")
        >>> cmd.run_stderr()                                    # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        return super(SSHPTYCommand, self).run_stderr()

    def run_status (self):
        """
        Run a command over an ssh channel, return exitcode and stdout.

        >>> status, output = SSHCommand("ls -d /etc", "localhost").run_status()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> status, output = SSHCommand("grep foobar doesnt-exist", "localhost").run_status()
        >>> status
        2
        >>> print(output, end="")
        """
        return super(SSHPTYCommand, self).run_status()

    def run (self):
        """
        Run a command over an ssh channel, return stdout.
        Raise CalledProcessError on failure.

        >>> cmd = SSHCommand("ls -d /etc", "localhost")
        >>> print(cmd.run(), end="")
        /etc
        >>> cmd = SSHCommand("grep foobar doesnt-exist", "localhost")
        >>> cmd.run()                                   # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        return super(SSHPTYCommand, self).run()


class ShellCommand (object):

    def __init__ (self, command, debug=False):
        self.command_list = ["/bin/sh", "-c", command]
        self.debug = debug
        self.exit_code = None
        self.output = ""
        self.error_output = ""

    def run_status_stderr (self):
        """
        Run a command over an ssh channel, return exit code, stdout and stderr.

        >>> cmd = ShellCommand("ls -d /etc")
        >>> status, output, error = cmd.run_status_stderr()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        """
        """
        >>> status, output, error = ShellCommand("grep foobar doesnt-exist").run_status_stderr()
        >>> status
        2
        >>> print(output, end="")
        >>>
        >>> print(error, end="")
        grep: doesnt-exist: No such file or directory
        """
        try:
            pipe = subprocess.Popen(self.command_list,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True)
            output, error_output = pipe.communicate()
            self.output = output.decode('utf-8')
            self.error_output = error_output.decode('utf-8')
            self.exit_code = pipe.returncode
        except OSError:
            self.exit_code = 1

        return (self.exit_code, self.output, self.error_output)

    def run_stderr (self):
        """
        Run a command over an ssh channel, return stdout and stderr,
        Raise CalledProcessError on failure

        >>> cmd = ShellCommand("ls -d /etc")
        >>> output, error = cmd.run_stderr()
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> cmd = ShellCommand("grep foobar doesnt-exist")
        >>> cmd.run_stderr()                                    # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        status, unused, unused = self.run_status_stderr()
        if status != 0:
            raise CalledProcessError(self.exit_code, self.command_list,
                                     self.error_output if self.error_output else self.output)
        return self.output, self.error_output

    def run_status (self):
        """
        Run a command over an ssh channel, return exitcode and stdout.

        >>> status, output = ShellCommand("ls -d /etc").run_status()
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> status, output = ShellCommand("grep foobar doesnt-exist").run_status()
        >>> status
        2
        >>> print(output, end="")
        """
        return self.run_status_stderr()[0:2]

    def run (self):
        """
        Run a command over an ssh channel, return stdout.
        Raise CalledProcessError on failure.

        >>> cmd = ShellCommand("ls -d /etc", False)
        >>> print(cmd.run(), end="")
        /etc
        >>> cmd = ShellCommand("grep foobar doesnt-exist", False)
        >>> cmd.run()                                   # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        CalledProcessError: Command 'grep foobar doesnt-exist' returned non-zero exit status 2
        """
        return self.run_stderr()[0]


class Host (object):
    def __init__ (self, server=None, port=22, cwd=None, username=None, password=None, debug=False):
        """
        A host object is either local or remote and provides easy access
        to the given local or remote host
        """
        self.cwd = cwd
        if server:
            self.cmd_class = functools.partial(SSHCommand,
                                               host=server,
                                               port=port,
                                               username=username,
                                               password=password,
                                               debug=debug)
        else:
            self.cmd_class = functools.partial(ShellCommand, debug=debug)

        if not self.cwd:
            self.cwd = self.cmd_class("pwd").run().strip()

    def get_cmd (self, command):
        return "bash -c 'cd {} && {}'".format(self.cwd, shell_escape_single_quote(command))

    def run_status_stderr (self, command):
        """
        Run a command return exit code, stdout and stderr.
        >>> host = Host()
        >>> status, output, error = host.run_status_stderr("ls -d /etc")
        >>> status
        0
        >>> print(output, end="")
        /etc
        >>> print(error, end="")
        >>> status, output, error = host.run_status_stderr("grep foobar doesnt-exist")
        >>> status
        2
        >>> print(output, end="")
        >>>
        >>> print(error, end="")
        grep: doesnt-exist: No such file or directory
        """
        return self.cmd_class(self.get_cmd(command)).run_status_stderr()

    def run_status (self, command):
        return self.cmd_class(self.get_cmd(command)).run_status()

    def run_stderr (self, command):
        return self.cmd_class(self.get_cmd(command)).run_stderr()

    def run (self, command):
        return self.cmd_class(self.get_cmd(command)).run()


if __name__ == "__main__":
    import time
    import gc

    cmd = SSHCommand("ls -d /etc", "localhost", debug=True)
    print(cmd.run())
    gc.collect()

    print(SSHCommand("ls -d /etc", "localhost", debug=True).run())
    gc.collect()

    print("Going to sleep for 2")
    time.sleep(2)
    gc.collect()

    print("Waking up")
    print(SSHCommand("ls -d /etc", "localhost", debug=True).run())
    gc.collect()
    print("Exiting")
