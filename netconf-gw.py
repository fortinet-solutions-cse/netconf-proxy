#!/usr/bin/sudo python
from __future__ import absolute_import, division, unicode_literals, print_function, nested_scopes

# **********************************
# Requires following modules
# TODO: use requirements.txt
# sudo pip install pysnmp
# sudo pip install netconf
# **********************************

import logging
import time
import sys

# **********************************
# SNMP imports
# **********************************
import threading
from pysnmp.carrier.asynsock.dispatch import AsynsockDispatcher
from pysnmp.carrier.asynsock.dgram import udp, udp6
from pyasn1.codec.ber import decoder
from pysnmp.proto import api


# **********************************
# Netconf imports
# **********************************

from netconf import server

try:
    from lxml import etree
except ImportError:
    from xml.etree import ElementTree as etree

# **********************************
# Global definitions
# **********************************

netconf_server = None
logger = logging.getLogger(__name__)
SERVER_DEBUG = True
NC_PORT = 830
USER="m"

# **********************************
# General functions
# **********************************


def snmpTrapReceiver(transportDispatcher, transportDomain, transportAddress, wholeMsg):
    while wholeMsg:
        msgVer = int(api.decodeMessageVersion(wholeMsg))
        if msgVer in api.protoModules:
            pMod = api.protoModules[msgVer]
        else:
            print('Unsupported SNMP version %s' % msgVer)
            return
        reqMsg, wholeMsg = decoder.decode(
            wholeMsg, asn1Spec=pMod.Message(),
            )
        print('Notification message from %s:%s: ' % (
            transportDomain, transportAddress
            )
        )
        reqPDU = pMod.apiMessage.getPDU(reqMsg)
        if reqPDU.isSameTypeWith(pMod.TrapPDU()):
            if msgVer == api.protoVersion1:
                print('Enterprise: %s' % (
                    pMod.apiTrapPDU.getEnterprise(reqPDU).prettyPrint()
                    )
                )
                print('Agent Address: %s' % (
                    pMod.apiTrapPDU.getAgentAddr(reqPDU).prettyPrint()
                    )
                )
                print('Generic Trap: %s' % (
                    pMod.apiTrapPDU.getGenericTrap(reqPDU).prettyPrint()
                    )
                )
                print('Specific Trap: %s' % (
                    pMod.apiTrapPDU.getSpecificTrap(reqPDU).prettyPrint()
                    )
                )
                print('Uptime: %s' % (
                    pMod.apiTrapPDU.getTimeStamp(reqPDU).prettyPrint()
                    )
                )
                varBinds = pMod.apiTrapPDU.getVarBindList(reqPDU)
            else:
                varBinds = pMod.apiPDU.getVarBindList(reqPDU)
            print('Var-binds:')
            for oid, val in varBinds:
                print('%s = %s' % (oid, val))
    return wholeMsg


send_now=False


class NetconfMethods (server.NetconfMethods):
    def nc_append_capabilities (self, capabilities):        # pylint: disable=W0613
        #capabilities.append(etree.Element("urn:ietf:params:netconf:base:1.0"));
        cap = etree.Element("capability")
        cap.text="urn:ietf:params:netconf:capability:notification:1.0"
        capabilities.append( cap )
        cap = etree.Element("capability")
        cap.text="urn:samsung:vnf-alarm-interface?module=vnf-alarm-interface&amp;revision=2016-07-08"
        capabilities.append( cap )
        print("hello************************************")
        return

    def rpc_get (self, unused_session, rpc, *unused_params):


        for x in unused_params:
            print(x)

        print("rpc_get")

        return etree.Element("ok1")

    def rpc_get_config (self, unused_session, rpc, *unused_params):
        return etree.Element("ok2")

    def rpc_edit_config (self, unused_session, rpc, *unused_params):
        return etree.Element("ok3")

    def rpc_rpc (self, unused_session, rpc, *unused_params):
        print("Session:{}".format(unused_session))
        print("RPC:{}".format(rpc))
        print(etree.tostring(rpc,pretty_print=True))
        for x in unused_params:
            print(x)
            print(etree.tostring(x,pretty_print=True))

        print("create_subscription")
        print("Sockets.len:{}".format(len(netconf_server.sockets)))


        global send_now
        send_now =True

        return etree.Element("Create_Subscription_Received")

    def rpc_namespaced (self, unused_session, rpc, *unused_params):
        return etree.Element("ok4")




def netconf_loop():

    print("nc")

    return


def setup_snmp():

    transportDispatcher = AsynsockDispatcher()

    transportDispatcher.registerRecvCbFun(snmpTrapReceiver)

    # UDP/IPv4
    transportDispatcher.registerTransport(
        udp.domainName, udp.UdpSocketTransport().openServerMode(('localhost', 162))
    )

    # UDP/IPv6
    transportDispatcher.registerTransport(
        udp6.domainName, udp6.Udp6SocketTransport().openServerMode(('::1', 162))
    )

    transportDispatcher.jobStarted(1)

    try:
        # Dispatcher will never finish as job#1 never reaches zero
        transportDispatcher.runDispatcher()
    except:
        transportDispatcher.closeDispatcher()
        raise


def setup_netconf():

    global netconf_server

    logging.basicConfig(level=logging.INFO)

    if netconf_server is not None:
        logger.error("Netconf Server is already up and running")
    else:
        server_ctl = server.SSHUserPassController(username=USER,
                                                  password="admin")
        netconf_server = server.NetconfSSHServer(server_ctl=server_ctl,
                                            server_methods=NetconfMethods(),
                                            port=NC_PORT,
                                            host_key="keys/host_key",
                                            debug=SERVER_DEBUG)

        print("Sockets.len:: {}".format(len(netconf_server.sockets)))

if __name__ == "__main__":

    global send_now

    setup_netconf()

    print("Listening Netconf")
    while True:
        time.sleep(5)
        sys.stdout.write(".")
        sys.stdout.flush()
        if send_now:
            netconf_server.trigger_notification()
            #send_now=False



