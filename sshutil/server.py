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
import errno
import logging
import os
import select
import socket
import threading
import traceback
import paramiko as ssh


logger = logging.getLogger(__name__)


class SSHUserPassController (ssh.ServerInterface):
    def __init__ (self, username=None, password=None):
        self.username = username
        self.password = password
        self.event = threading.Event()

    def get_allowed_auths (self, unused_username):
        return ["password"]

    def check_auth_none (self, unused_username):
        return ssh.AUTH_FAILED

    def check_auth_password (self, username, password):
        if self.username == username and self.password == password:
            return ssh.AUTH_SUCCESSFUL
        return ssh.AUTH_FAILED

    def check_channel_request (self, kind, unused_channel):
        if kind == "session":
            return ssh.OPEN_SUCCEEDED
        return ssh.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_subsystem_request (self, channel, name):
        self.event.set()
        return name == "netconf"


class SSHServerSession (object):
    def __init__ (self, stream, unused_server, unused_extra_args, debug):
        self.stream = stream
        self.debug = debug

        self.reader_thread = None
        self.lock = threading.Lock()

    def __del__ (self):
        if hasattr(self, "stream") and self.stream is not None:
            self.close()

    def __str__ (self):
        return "SSHServerSession(stream:{})".format(str(self.stream))

    def is_active (self):
        with self.lock:
            return self.stream and self.stream.is_active()

    def send (self, data):
        with self.lock:
            stream = self.stream
        return stream.send(data)

    def recv (self, rlen):
        with self.lock:
            if not self.reader_thread or not self.reader_thread.keep_running:
                return None
            stream = self.stream
        return stream.recv(rlen)

    def close (self):
        if self.debug:
            logger.debug("%s: Closing.", str(self))

        with self.lock:
            if self.reader_thread:
                self.reader_thread.keep_running = False

            if self.stream is None:
                return
            if self.debug:
                logger.debug("%s: Closing transport.", str(self))

            stream = self.stream
            self.stream = None
            try:
                # If we are blocked on reading this should unblock us
                stream.close()
            except EOFError:
                if self.debug:
                    logger.debug("%s: XXX close: channel's transport is closed",
                                 str(self))

    def reader_exits (self):
        # Called from reader thread when our reader thread exits
        if self.debug:
            logger.debug("%s: Reader thread exited.", str(self))

    def reader_handle_data (self, data):
        # Called from reader thread after receiving a framed message
        if self.debug:
            logger.debug("%s: Reader got data: \"%s\"", str(self), str(data))

    def reader_read_data (self):
        "Called by reader thread if a evaluate false value is returned thread exits"
        return self.recv(0xFFFFFF)

    def _read_message_thread (self):
        if self.debug:
            logger.debug("Starting reader thread.")

        reader_thread = self.reader_thread
        try:
            while self.stream:
                with self.lock:
                    stream = self.stream
                    if not reader_thread.keep_running:
                        break
                    assert stream is not None

                data = self.reader_read_data()
                if data:
                    self.reader_handle_data(data)
                    closed = False
                else:
                    # Client closed, never really see this 1/2 open case unfortunately.
                    if self.debug:
                        logger.debug("Client remote closed, exiting reader thread.")
                    closed = True

                with self.lock:
                    if closed:
                        reader_thread.keep_running = False
                    if not reader_thread.keep_running:
                        break

            if self.debug:
                logger.debug("Exiting reader thread")
        except socket.error as error:
            if self.debug:
                logger.debug("Socket error in reader thread [exiting]: %s", str(error))
            self.close()
        except Exception as error:
            with self.lock:
                keep_running = reader_thread.keep_running
            if keep_running:
                logger.error("Unexpected exception in reader thread [disconnecting+exiting]: %s: %s",
                             str(error),
                             traceback.format_exc())
                self.close()
            else:
                # XXX might want to catch errors due to disconnect and not re-raise
                logger.debug("Exception in reader thread [exiting]: %s: %s",
                             str(error),
                             traceback.format_exc())
        finally:
            # If we are exiting the read thread we close the session.
            self.reader_exits()


class SSHServerSocket (object):
    """An SSH socket connection from a client"""
    def __init__ (self,
                  server_ctl,
                  session_class,
                  extra_args,
                  server,
                  newsocket,
                  addr,
                  debug):
        self.session_class = session_class
        self.extra_args = extra_args
        self.server = server
        self.client_socket = newsocket
        self.client_addr = addr
        self.debug = debug
        self.server_ctl = server_ctl
        self.sessions = []

        try:
            if self.debug:
                logger.debug("%s: Opening SSH connection", str(self))

            self.ssh = ssh.Transport(self.client_socket)
            self.ssh.add_server_key(self.server.host_key)
            self.ssh.start_server(server=self.server_ctl)
        except ssh.AuthenticationException as error:
            self.client_socket.close()
            self.client_socket = None
            logger.error("Authentication failed:  %s", str(error))
            raise

        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(None,
                                       self._accept_chan_thread,
                                       name="SSHAcceptThread")
        self.thread.daemon = True
        self.thread.start()

    def __str__ (self):
        return "SSHServerSocket(client: {})".format(self.client_addr)

    def close (self):

        with self.lock:
            logger.debug("%s: close socket", str(self))
            self.running = False

            sessions = self.sessions
            for session in sessions:
                session.close()
            self.sessions = []

            # Closing one of these should cause a blocking accept to exit
            if self.ssh:
                logger.debug("%s: close closing ssh conn %s", str(self), str(self.ssh))
                self.ssh.close()
                self.ssh = None

            if self.client_socket:
                logger.debug("%s: close closing client socket %s",
                             str(self),
                             str(self.client_socket))
                self.client_socket.close()
                self.client_socket = None

        # wait on the thread to quit?
        logger.debug("%s: close joining thread", str(self))

        self.thread.join()
        logger.debug("%s: close *** joined *** thread", str(self))

    def _accept_chan_thread (self):
        try:
            while True:
                with self.lock:
                    if not self.running:
                        logger.debug("%s: Exiting thread", str(self))
                        break

                    # grab this while we have the lock
                    ssh_conn = self.ssh

                if self.debug:
                    logger.debug("%s: Accepting channel connections", str(self))

                # accept with 1s timeout, this doesn't return when we close the connection for some
                # reason so we cannot just simply wait forever which would be preferable.
                channel = ssh_conn.accept(timeout=1)

                with self.lock:
                    if not self.running:
                        if channel:
                            logger.debug("%s: Closing channel after shutdown %s",
                                         str(self),
                                         str(channel))
                            channel.close()
                        logger.debug("%s: Exiting thread", str(self))
                        return

                    if channel is None:
                        if not self.ssh.is_active():
                            logger.info("%s: Got channel as None not active so exiting", str(self))
                            self.running = False
                            return

                        # We can't warn here if we are doing timeouts see above.
                        # logger.warn("%s: Got channel as None still active.", str(self))
                        if self.debug:
                            logger.debug("%s: Got channel as None must be timeout.", str(self))
                        continue

                session = self.session_class(channel, self.server, self.extra_args, self.debug)
                with self.lock:
                    self.sessions.append(session)

        except Exception as error:
            if self.debug:
                logger.error("%s: Unexpected exception: %s: %s",
                             str(self),
                             str(error),
                             traceback.format_exc())
            else:
                logger.error("%s: Unexpected exception: %s closing",
                             str(self),
                             str(error))

            self.client_socket.close()
            self.client_socket = None
            self.server.remove_socket(self)
        except:
            logger.error("%s: ********** Unexpected exception")
            raise


class SSHServer (object):
    """An ssh server"""
    def __del__ (self):
        logger.error("Deleting %s", str(self))

    def __init__ (self,
                  server_ctl=None,
                  server_socket_class=None,
                  server_session_class=None,
                  extra_args=None,
                  port=None,
                  host_key=None,
                  debug=False):

        if server_ctl is None:
            server_ctl = SSHUserPassController()
        self.server_ctl = server_ctl

        if server_socket_class is None:
            server_socket_class = SSHServerSocket
        self.server_socket_class = server_socket_class

        if server_session_class is None:
            server_session_class = SSHServerSession
        self.server_session_class = server_session_class

        self.extra_args = extra_args
        self.debug = debug
        if port is None:
            port = 0
        self.port = port
        self.host_key = None

        # Load the host key for our ssh server.
        if host_key:
            assert os.path.exists(host_key)
            self.host_key = ssh.RSAKey.from_private_key_file(host_key)
        else:
            for keypath in [ "/etc/ssh/ssh_host_rsa_key",
                             "/etc/ssh/ssh_host_dsa_key"]:
                # XXX check we have access
                if os.path.exists(keypath):
                    self.host_key = ssh.RSAKey.from_private_key_file(keypath)
                    break

        # Bind first to IPv6, if the OS supports binding per AF then the IPv4
        # will succeed, otherwise the IPv6 will support both AF.
        for pname, host, proto in [ ("IPv6", '::', socket.AF_INET6), ("IPv4", '', socket.AF_INET) ]:
            protosocket = socket.socket(proto, socket.SOCK_STREAM)
            protosocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if self.debug:
                logger.debug("Server binding to proto %s port %s", str(pname), str(port))
            if proto == socket.AF_INET:
                try:
                    protosocket.bind((host, port))
                except socket.error as error:
                    if error.errno == errno.EADDRINUSE:
                        break
                    else:
                        logger.debug("Server error binding to proto %s port %s error: %s",
                                     str(pname), str(port), str(error))
                        raise
                except Exception as error:
                    logger.debug("Server exception binding to proto %s port %s type %s: error: %s",
                                 str(pname), str(port), str(error.__class__), str(error))
                    raise
            else:
                protosocket.bind((host, port, 0, 0))

            if port == 0:
                assigned = protosocket.getsockname()
                self.port = assigned[1]

            if self.debug:
                logger.debug("Server listening on proto %s port %s", str(pname), str(port))
            protosocket.listen(100)

            # Create a socket to cause closure.
            self.close_wsocket, self.close_rsocket = socket.socketpair()

            self.lock = threading.Lock()
            self.sockets = []

            self.thread = threading.Thread(None,
                                           self._accept_socket_thread,
                                           name="SSHAcceptThread " + pname,
                                           args=[protosocket])
            self.thread.daemon = True
            self.thread.start()

    def close (self):
        with self.lock:
            logger.info("Sending close signal to accept socket")
            assert self.thread.is_alive()
            self.close_wsocket.send(b"!")

    def join (self):
        "Wait on server to terminate"
        assert self.thread
        self.thread.join()
        self.thread = None

    def remove_socket (self, serversocket):
        with self.lock:
            self.sockets.remove(serversocket)

    def _accept_socket_thread (self, proto_sock):
        """Call from within a thread to accept connections."""
        try:
            while True:
                if self.debug:
                    logger.debug("%s: Accepting connections", str(self))

                rfds, unused, unused = select.select([proto_sock, self.close_rsocket], [], [])
                if self.close_rsocket in rfds:
                    if self.debug:
                        logger.debug("%s: Got close notification closing down server", str(self))

                    # with self.lock:
                    #     sockets = list(self.sockets)
                    sockets = list(self.sockets)
                    logger.debug("%s: closing %d server socket[s]", str(self), len(sockets))

                    # These sockets are channels
                    for sock in sockets:
                        if sock in self.sockets:
                            if self.debug:
                                logger.debug("%s: closing server socket %s", str(self), str(sock))
                            sock.close()

                    # Not until we have a real shutdown
                    # assert not self.sockets

                    # Close our listening socket.
                    if self.debug:
                        logger.debug("%s: closing proto socket %s",
                                     str(self),
                                     str(proto_sock))
                    proto_sock.close()

                    # Close our closing socket.
                    if self.debug:
                        logger.debug("%s: closing close socket %s",
                                     str(self),
                                     str(self.close_rsocket))
                    self.close_rsocket.close()

                    logger.debug("%s: exiting accept thread", str(self))
                    return

                if proto_sock in rfds:
                    client, addr = proto_sock.accept()
                    logger.debug("%s: Client accepted: %s: %s", str(self), str(client), str(addr))
                    try:
                        sock = self.server_socket_class(self.server_ctl,
                                                        self.server_session_class,
                                                        self.extra_args,
                                                        self,
                                                        client,
                                                        addr,
                                                        self.debug)
                        with self.lock:
                            self.sockets.append(sock)
                    except ssh.AuthenticationException as error:
                        logger.debug("%s: Client auth failed: %s: %s: %s",
                                     str(self),
                                     str(client),
                                     str(addr),
                                     str(error))

        except Exception as error:
            if self.debug:
                logger.error("%s: Unexpected exception: %s: %s",
                             str(self),
                             str(error),
                             traceback.format_exc())
            else:
                logger.error("%s: Unexpected exception: %s closing",
                             str(self),
                             str(error))

    def __str__ (self):
        return "SSHServer(port={})".format(self.port)


__author__ = 'Christian Hopps'
__date__ = 'December 14 2016'
__version__ = '1.0'
__docformat__ = "restructuredtext en"
