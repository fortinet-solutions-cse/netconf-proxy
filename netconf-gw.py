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
logging.basicConfig(level=logging.DEBUG)
SERVER_DEBUG = True
NC_PORT = 830
USER="m"
PASSWORD="admin"

# **********************************
# General SNMP functions
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

# **********************************
# General Netconf functions
# **********************************

send_now=False

class NetconfMethods (server.NetconfMethods):

    def nc_append_capabilities (self, capabilities_answered):        # pylint: disable=W0613

        capability_list = ["urn:ietf:params:netconf:capability:writable - running:1.0",
                "urn:ietf:params:netconf:capability:interleave:1.0",
                "urn:ietf:params:netconf:capability:notification:1.0",
                "urn:ietf:params:netconf:capability:validate:1.0",
                "urn:samsung:vnf-deploy-interface?module=vnf-deploy-interface&amp;revision=2016-05-15",
                "urn:samsung:vnf-alarm-interface?module=vnf-alarm-interface&amp;revision=2016-07-08",
                "urn:samsung:samsung-types?module=samsung-types&amp;revision=2016-05-15",
                "urn:cesnet:tmc:netopeer:1.0?module=netopeer-cfgnetopeer&amp;revision=2015-05-19&amp;features=ssh,dynamic-modules",
                "urn:ietf:params:xml:ns:yang:ietf-netconf-server?module=ietf-netconf-server&amp;revision=2014-01-24&amp;features=ssh,inbound-ssh,outbound-ssh",
                "urn:ietf:params:xml:ns:yang:ietf-x509-cert-to-name?module=ietf-x509-cert-to-name&amp;revision=2013-03-26",
                "urn:ietf:params:xml:ns:yang:ietf-netconf-acm?module=ietf-netconf-acm&amp;revision=2012-02-22",
                "urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults?module=ietf-netconf-with-defaults&amp;revision=2010-06-09",
                "urn:ietf:params:xml:ns:netconf:notification:1.0?module=notifications&amp;revision=2008-07-14",
                "urn:ietf:params:xml:ns:netmod:notification?module=nc-notifications&amp;revision=2008-07-14",
                "urn:ietf:params:xml:ns:yang:ietf-netconf-notifications?module=ietf-netconf-notifications&amp;revision=2012-02-06",
                "urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring?module=ietf-netconf-monitoring&amp;revision=2010-10-04",
                "urn:ietf:params:xml:ns:netconf:base:1.0?module=ietf-netconf&amp;revision=2011-03-08&amp;features=validate",
                "urn:ietf:params:xml:ns:yang:ietf-yang-types?module=ietf-yang-types&amp;revision=2013-07-15",
                "urn:ietf:params:xml:ns:yang:ietf-inet-types?module=ietf-inet-types&amp;revision=2013-07-15"]

        for cap in capability_list:
            elem=etree.Element("capability")
            elem.text=cap
            capabilities_answered.append(elem)
        return

    def rpc_get (self, unused_session, rpc, *unused_params):
        logger.info("rpc_get")
        return etree.Element("ok")

    def rpc_get_config (self, unused_session, rpc, *unused_params):
        logger.info("rpc_get_config")
        return etree.Element("ok")

    def rpc_edit_config (self, unused_session, rpc, *unused_params):
        logger.info("rpc_edit_config")
        return etree.Element("ok")

    def rpc_rpc (self, unused_session, rpc, *unused_params):

        logger.info("rpc_create-subscription")

        global send_now
        send_now =True

        logger.debug("Session:{}".format(unused_session))
        logger.debug("RPC received:{}".format(etree.tostring(rpc,pretty_print=True)))

        for x in unused_params:
            logger.debug(etree.tostring(x,pretty_print=True))

        return etree.Element("ok")

    def rpc_namespaced (self, unused_session, rpc, *unused_params):
        logger.info("rpc_namespaced")
        return etree.Element("ok")

def netconf_loop():
    logger.info("Netconf Loop")

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

    if netconf_server is not None:
        logger.error("Netconf Server is already up and running")
    else:
        server_ctl = server.SSHUserPassController(username=USER,
                                                  password=PASSWORD)
        netconf_server = server.NetconfSSHServer(server_ctl=server_ctl,
                                            server_methods=NetconfMethods(),
                                            port=NC_PORT,
                                            host_key="keys/host_key",
                                            debug=SERVER_DEBUG)

if __name__ == "__main__":

    global send_now
    global netconf_server

    setup_netconf()

    logger.info("Listening Netconf")
    while True:
        time.sleep(5)
        sys.stdout.write(".")
        sys.stdout.flush()
        if send_now:
            netconf_server.trigger_notification()



