# -*- coding: utf-8 -*-#
#
# December 14 2016, Christian Hopps <chopps@gmail.com>
#
# Copyright (c) 2016, Deutsche Telekom AG.
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
import logging
import os
import select
import socket
import threading
import traceback
import paramiko as ssh

logger = logging.getLogger(__name__)

# Used by travis-ci testing
private_key = None


def socket_is_remote_closed (sock):
    rfds, unused, unused = select.select([sock], [], [], 0)
    try:
        if sock in rfds:
            buf = sock.recv(1, socket.MSG_PEEK)
            if len(buf) == 0:
                logger.debug("****** read 0 on peek assuming closed")
                return True
        return False
    except Exception as error:
        logger.debug("***** GOT EXCEPTION on read(PEEK) must be closed: %s", str(error))
        return True


class _SSHConnectionCache (object):
    ssh_config = None

    @classmethod
    def init_class_config (cls):
        # XXX do we want to initialize this elsewhere?
        if cls.ssh_config is None:
            cls.ssh_config = ssh.config.SSHConfig()
            configname = os.path.expanduser("~/.ssh/config")
            if os.path.exists(configname):
                with open(configname) as f:
                    cls.ssh_config.parse(f)

    @classmethod
    def open_os_socket (cls, host, port, use_config=True, debug=False, proxycmd=None):
        if use_config:
            cls.init_class_config()
            config = cls.ssh_config.lookup(host)

            # If we have a proxy command use that.
            if proxycmd or 'proxycommand' in config:
                if proxycmd:
                    proxy = proxycmd
                else:
                    proxy = config['proxycommand']
                proxy = proxy.replace('%h', host)
                proxy = proxy.replace('%p', str(port))
                logger.debug("Using proxy command for host %s port %s: %s",
                             host,
                             str(port),
                             proxy)
                return ssh.ProxyCommand(proxy)

            if 'port' in config:
                newport = config['port']
            else:
                newport = port

            if 'host' in config:
                host = config['host']

            if 'port' in config:
                if port != 22 and port != newport:
                    # XXX should we just never do this?
                    logger.warning("Remaping non-std ssh port %d using config to port %d",
                                   port,
                                   newport)
                port = newport

        # Otherwise try and resolve host and open an OS socket.
        if debug:
            logger.debug("Opening os socket to %s on port %s", str(host), str(port))

        attempt = 0
        try:
            error = None
            for addrinfo in socket.getaddrinfo(host,
                                               port,
                                               socket.AF_UNSPEC,
                                               socket.SOCK_STREAM):
                af, socktype, proto, unused_name, sa = addrinfo
                try:
                    ossock = socket.socket(af, socktype, proto)
                    ossock.connect(sa)
                    if attempt:
                        logger.debug("Succeeded after %s attempts to : %s", str(attempt), str(addrinfo))
                    return ossock
                except socket.error as ex:
                    logger.debug("Got socket error connecting to: %s: %s", str(addrinfo), str(ex))
                    attempt += 1
                    error = ex
                    continue
            if error is not None:
                logger.debug("Got error connecting to: %s: %s (no addr)",
                             str(addrinfo),                 # pylint: disable=W0631
                             str(error))
                raise error                                 # pylint: disable=E0702
            raise Exception("Couldn't connect to any resolution for {}:{}".format(host, port))
        except Exception as ex:
            logger.error("Got unexpected socket error connecting to: %s:%s: %s",
                         str(host),
                         str(port),
                         str(ex))
            raise

    @classmethod
    def _open_ssh_socket (cls, host, port, username, password, use_config, debug, proxy):
        ossock = cls.open_os_socket(host, port, use_config, debug, proxy)
        try:
            if debug:
                logger.debug("Opening SSH socket to %s:%s", str(host), str(port))

            sshsock = ssh.Transport(ossock)
            # self.ssh.set_missing_host_key_policy(ssh.AutoAddPolicy())

            # XXX this takes an event so we could yield here to wait for event.
            event = None
            sshsock.start_client(event)

            # XXX save this if we actually need it.
            sshsock.get_remote_server_key()

            try:
                password.get_name
            except AttributeError:
                password = password
                passkey = None
            else:
                passkey = password
                password = None

            # try:
            #     sshsock.auth_none(username)
            # except (ssh.AuthenticationException, ssh.BadAuthenticationType):
            #     pass

            logger.debug("Trying to authenticate with username: %s", str(username))
            if not sshsock.is_authenticated() and password is not None:
                try:
                    sshsock.auth_password(username, password, event, False)
                except (ssh.AuthenticationException, ssh.BadAuthenticationType) as error:
                    logger.debug("Password auth failed (cont): %s: %s", str(username), str(error))
                else:
                    if not sshsock.is_authenticated():
                        logger.warning("Password auth failed no error (cont) for %s",
                                       str(username))

            if not sshsock.is_authenticated() and passkey is not None:
                try:
                    sshsock.auth_publickey(username, passkey, event)
                except ssh.AuthenticationException as error:
                    logger.debug("Pubkey auth failed (cont): %s", str(error))
                else:
                    if not sshsock.is_authenticated():
                        logger.warning("Pubkey auth failed no error (cont)")

            if not sshsock.is_authenticated():
                ssh_keys = ssh.Agent().get_keys()
                if private_key:
                    # Used by travis-ci
                    ssh_keys += ( private_key, )
                lastkey = len(ssh_keys) - 1
                for idx, ssh_key in enumerate(ssh_keys):
                    if sshsock.is_authenticated():
                        break
                    try:
                        sshsock.auth_publickey(username, ssh_key, event)
                    except ssh.AuthenticationException as error:
                        if idx == lastkey:
                            raise
                        logger.debug("Pubkey auth failed (cont): %s", str(error))
                        # Try next key
            assert sshsock.is_authenticated()

            # nextauth (rval from above) would be a secondary authentication e.g., google authenticator.

            # XXX using the below instead of the breakout above fails threaded.
            # sshsock.connect(hostkey=None,
            #                 username=self.username,
            #                 password=self.password)
            return ossock, sshsock
        except ssh.AuthenticationException as error:
            ossock.close()
            logger.error("Authentication failed: %s", str(error))
            raise

    def release_ssh_socket (self, ssh_socket, debug):
        raise NotImplementedError("release_ssh_socket")

    def get_ssh_socket (self, host, port, username, password, debug):
        raise NotImplementedError("get_ssh_socket")


class SSHNoConnectionCache (_SSHConnectionCache):
    "Simple non-caching cache class"
    def release_ssh_socket (self, ssh_socket, debug=False):
        ossock = ssh_socket.os_socket
        ssh_socket.close()
        ossock.close()

    def get_ssh_socket (self, host, port, username, password, debug=False, proxycmd=None):
        # True below is to use users ssh config, should this be part of get_ssh_socket API?
        ossock, sshsock = _SSHConnectionCache._open_ssh_socket(host,
                                                               port,
                                                               username,
                                                               password,
                                                               True,
                                                               debug,
                                                               proxycmd)
        sshsock.os_socket = ossock
        return sshsock

    def flush (self, debug=False):          # pylint: disable=W0613
        return


class SSHConnectionCache (_SSHConnectionCache):
    def __init__ (self, desc="", close_timeout=1, max_channels=8):
        self.close_timeout = close_timeout
        self.max_channels = max_channels
        self.desc = desc
        self.ssh_sockets = {}
        self.ssh_socket_keys = {}
        self.ssh_socket_timeout = {}
        self.ssh_sockets_lock = threading.Lock()

    def flush (self, debug=False):
        "Flush entries waiting for timeout."
        # XXX change this when we create a class
        with self.ssh_sockets_lock:
            for key in self.ssh_sockets:
                for entry in self.ssh_sockets[key]:
                    ssh_socket = entry[1]
                    try:
                        timer = self.ssh_socket_timeout[ssh_socket]
                    except KeyError:
                        continue
                    if timer is None:
                        continue
                    if debug:
                        logger.debug("Flush: canceling and releasing ssh socket: %s",
                                     str(ssh_socket))
                    timer.cancel()
                    del self.ssh_socket_timeout[ssh_socket]
                    self._close_socket(ssh_socket, debug)

    def get_ssh_socket (self, host, port, username, password, debug, proxycmd=None):
        # Return an open ssh socket if we have one.
        key = "{}:{}@{}:{}".format(host, port, username, proxycmd)
        with self.ssh_sockets_lock:
            if debug:
                logger.debug("Searching for \"%s\" in open ssh socket cache", key)
            if key in self.ssh_sockets:
                for entry in self.ssh_sockets[key]:
                    # Check if we have too many open channels on this socket or if the socket is
                    if entry[2] >= self.max_channels:
                        continue

                    # Make sure the session is still active, the remote side may have closed.
                    # XXX Hard to tell if the OS socket is closed on us. I'm not sure if
                    # is_active() here covers this. If the remote side closes the socket
                    # (e.g., the server exits) we don't want to use it anymore, but I'm not
                    # sure how to handle this case.
                    if not entry[1].is_active():
                        logger.debug("entry is not active")
                        continue

                    if socket_is_remote_closed(entry[0]):
                        logger.debug("entry's socket is remote closed")
                        continue

                    sshsock = entry[1]
                    entry[2] += 1
                    if debug:
                        logger.debug("Incremented SSH socket use to %s", str(entry[2]))

                    # Cancel any timeout for closing, only really need to do this on count == 1.
                    self.cancel_close_socket_expire(sshsock, debug)

                    return sshsock

                # This means there are no entries with free channels
                if debug:
                    logger.debug("Entries for %s are maxed or closed", key)

            # True below is to use users ssh config, should this be part of get_ssh_socket
            # API?
            ossock, sshsock = _SSHConnectionCache._open_ssh_socket(host,
                                                                   port,
                                                                   username,
                                                                   password,
                                                                   True,
                                                                   debug,
                                                                   proxycmd)

            if key not in self.ssh_sockets:
                self.ssh_sockets[key] = []
            # Add this socket to the list of sockets for this key
            self.ssh_sockets[key].append([ossock, sshsock, 1])
            self.ssh_socket_keys[sshsock] = key
            return sshsock

    def cancel_close_socket_expire (self, ssh_socket, debug):
        """Must enter locked"""
        if not ssh_socket:
            return
        if ssh_socket not in self.ssh_socket_timeout:
            return
        if debug:
            logger.debug("Canceling timer to release ssh socket: %s", str(ssh_socket))
        timer = self.ssh_socket_timeout[ssh_socket]
        del self.ssh_socket_timeout[ssh_socket]
        timer.cancel()

    def _close_socket_expire (self, ssh_socket, debug):
        if not ssh_socket:
            return

        with self.ssh_sockets_lock:
            # If we aren't present anymore must have been canceled
            if ssh_socket not in self.ssh_socket_timeout:
                return

            if debug:
                logger.debug("Timer expired, releasing ssh socket: %s", str(ssh_socket))

            # Remove any timeout
            del self.ssh_socket_timeout[ssh_socket]
            self._close_socket(ssh_socket, debug)

    def release_ssh_socket (self, ssh_socket, debug):
        if not ssh_socket:
            return

        with self.ssh_sockets_lock:
            key = self.ssh_socket_keys[ssh_socket]

            assert key in self.ssh_sockets
            entry = None
            for entry in self.ssh_sockets[key]:
                if entry[1] == ssh_socket:
                    break
            else:
                raise KeyError("Can't find {} in list of entries".format(key))

            entry[2] -= 1
            if entry[2]:
                if debug:
                    logger.debug("Decremented SSH socket use to %s", str(entry[2]))
                return

            # We are all done with this socket
            # Setup a timer to actually close the socket.
            if ssh_socket not in self.ssh_socket_timeout:
                if debug:
                    logger.debug("Setting up timer to release ssh socket: %s", str(ssh_socket))
                self.ssh_socket_timeout[ssh_socket] = threading.Timer(1,
                                                                      self._close_socket_expire,
                                                                      [ssh_socket, debug])
                self.ssh_socket_timeout[ssh_socket].start()

    def _close_socket (self, ssh_socket, debug):
        entry = None
        try:
            key = self.ssh_socket_keys[ssh_socket]
            for entry in self.ssh_sockets[key]:
                if entry[1] == ssh_socket:
                    break
            else:
                assert False

            if debug:
                logger.debug("Closing SSH socket to %s", str(key))
            if entry[1]:
                entry[1].close()
                entry[1] = None

            if entry[0]:
                entry[0].close()
                entry[0] = None
        except Exception as error:
            logger.info("%s: Unexpected exception: %s: %s", str(self), str(error), traceback.format_exc())
            logger.error("%s: Unexpected error closing socket:  %s", str(self), str(error))
        finally:
            del self.ssh_socket_keys[ssh_socket]
            if entry:
                self.ssh_sockets[key].remove(entry)

    def __str__ (self):
        "Return a nice string for the cache object"
        return "SSHConnectionCache(\"{}\", close_timeout={}, max_channels={})".format(
            self.desc,
            self.close_timeout,
            self.max_channels)


def setup_travis ():
    import getpass
    import sys
    global private_key                                      # pylint: disable=W0603

    logging.basicConfig(level=logging.DEBUG, stream=sys.stderr)
    print("Setup called.")
    if 'USER' in os.environ:
        if os.environ['USER'] != "travis":
            return
    else:
        if getpass.getuser() != "travis":
            return

    print("Executing under Travis-CI")
    ssh_dir = "{}/.ssh".format(os.environ['HOME'])
    priv_filename = os.path.join(ssh_dir, "id_rsa")
    if os.path.exists(priv_filename):
        logger.error("Found private keyfile")
        print("Found private keyfile")
        return
    else:
        logger.error("Creating ssh dir " + ssh_dir)
        print("Creating ssh dir " + ssh_dir)
        os.system("mkdir -p {}".format(ssh_dir))
        priv = ssh.RSAKey.generate(bits=1024)
        private_key = priv

        logger.error("Generating private keyfile " + priv_filename)
        print("Generating private keyfile " + priv_filename)
        priv.write_private_key_file(filename=priv_filename)

        pub = ssh.RSAKey(filename=priv_filename)
        auth_filename = os.path.join(ssh_dir, "authorized_keys")
        logger.error("Adding keys to authorized_keys file " + auth_filename)
        print("Adding keys to authorized_keys file " + auth_filename)
        with open(auth_filename, "a") as authfile:
            authfile.write("{} {}\n".format(pub.get_name(), pub.get_base64()))
        logger.error("Done generating keys")
        print("Done generating keys")


__author__ = 'Christian Hopps'
__date__ = 'December 14 2016'
__docformat__ = "restructuredtext en"
