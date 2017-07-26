#!/usr/bin/sudo python

"""
#************************************************
# Netconf Servcer with SNMP listening capabilities
#
# Use: ./netconf-proxy.py
#
# Miguel Angel Munoz Gonzalez
# magonzalez(at)fortinet.com
#
#************************************************

# **********************************
# Requires following modules
# TODO: use requirements.txt
# sudo pip install pysnmp
# **********************************
"""

from __future__ import absolute_import, division, unicode_literals, print_function, nested_scopes
import logging
import os
import re
import subprocess
import shlex
import argparse


# **********************************
# SNMP imports
# **********************************
from pysnmp.carrier.asynsock.dispatch import AsynsockDispatcher
from pysnmp.carrier.asynsock.dgram import udp, udp6
from pysnmp.proto import api
from pyasn1.codec.ber import decoder


# **********************************
# Netconf imports
# **********************************

try:
    from lxml import etree
except ImportError:
    from xml.etree import ElementTree as etree

from netconf import server

# **********************************
# Global definitions
# **********************************

netconf_server = None # pylint: disable=C0103

logger = logging.getLogger(__name__) # pylint: disable=C0103

snmp_traps_store = [] # pylint: disable=C0103

NC_PORT = 830
USER = "m"
PASSWORD = "admin"
SERVER_DEBUG = False

# **********************************
# General SNMP functions
# **********************************


def snmp_trap_receiver(transport_dispatcher, transport_domain, transport_address, whole_msg):

    """ Receives SNMP traps sent to this host"""
    while whole_msg:
        msg_ver = int(api.decodeMessageVersion(whole_msg))
        if msg_ver in api.protoModules:
            p_mod = api.protoModules[msg_ver]
        else:
            logger.warning('Unsupported SNMP version %s', msg_ver)
            return
        req_msg, whole_msg = decoder.decode(whole_msg, asn1Spec=p_mod.Message(), )
        logger.info('Notification message from %s:%s: ', transport_domain, transport_address)
        req_pdu = p_mod.apiMessage.getPDU(req_msg)
        if req_pdu.isSameTypeWith(p_mod.TrapPDU()):
            if msg_ver == api.protoVersion1:
                logger.info('Enterprise: %s',
                            (p_mod.apiTrapPDU.getEnterprise(req_pdu).prettyPrint()))
                logger.info('Agent Address: %s',
                            (p_mod.apiTrapPDU.getAgentAddr(req_pdu).prettyPrint()))
                logger.info('Generic Trap: %s',
                            (p_mod.apiTrapPDU.getGenericTrap(req_pdu).prettyPrint()))
                logger.info('Specific Trap: %s',
                            (p_mod.apiTrapPDU.getSpecificTrap(req_pdu).prettyPrint()))
                logger.info('Uptime: %s',
                            (p_mod.apiTrapPDU.getTimeStamp(req_pdu).prettyPrint()))
                var_binds = p_mod.apiTrapPDU.getVarBindList(req_pdu)
            else:
                var_binds = p_mod.apiPDU.getVarBindList(req_pdu)
                logger.info('Var-binds:')
            for oid, val in var_binds:
                logger.info('%s = %s', oid, val)

            # TODO: Missing mapping from SNMP to Netconf Values

            values = {"time":"2016-12-13T22:32:58Z",\
                      "systemdn":"fd19:bcb8:3cb5:2000::c0a8:8201",\
                      "alarmgroup":"EQUIPMENT_ALARM",\
                      "alarmtype":"FF",\
                      "alarmseverity":"major",\
                      "alarminfo":"-",\
                      "alarmlocation":"FUPC0",\
                      "alarmcode":"1502",\
                      "objectid":"7401f9d7-2d5e-4cfe-8ae1-d2adebf085fb",\
                      "objecttype":"VNF Component",\
                      "sequencenumber":"0",\
                      "notificationtype":"NotifyClearedAlarm"}

            notif = """<notification xmlns="urn:ietf:params:xml:ns:netconf:notification:1.0">"""\
                    """<eventTime>%(time)s</eventTime>""" \
                    """<vnf-alarm xmlns="urn:samsung:vnf-alarm-interface">""" \
                    """<event-time>%(time)s</event-time>""" \
                    """<system-dn>%(systemdn)s</system-dn>""" \
                    """<alarm-group>%(alarmgroup)s</alarm-group>""" \
                    """<alarm-type>%(alarmtype)s</alarm-type>""" \
                    """<alarm-severity>%(alarmseverity)s</alarm-severity>""" \
                    """<alarm-info>%(alarminfo)s</alarm-info>""" \
                    """<alarm-location>%(alarmlocation)s</alarm-location>""" \
                    """<alarm-code>%(alarmcode)s</alarm-code>""" \
                    """<object-id>%(objectid)s</object-id>""" \
                    """<object-type>%(objecttype)s</object-type>""" \
                    """<sequence-number>%(sequencenumber)s</sequence-number>""" \
                    """<notification-type>%(notificationtype)s</notification-type>""" \
                    """</vnf-alarm>""" \
                    """</notification>""" % values

            snmp_traps_store.append(values)

            netconf_server.trigger_notification(notif)

    return whole_msg

# **********************************
# General Netconf functions
# **********************************


class NetconfMethods(server.NetconfMethods):

    """ Class containing the methods that will be called upon reception of Netconf external calls"""
    def nc_append_capabilities(self, capabilities_answered):

        capability_list = ["urn:ietf:params:netconf:capability:writable - running:1.0",
                           "urn:ietf:params:netconf:capability:interleave:1.0",
                           "urn:ietf:params:netconf:capability:notification:1.0",
                           "urn:ietf:params:netconf:capability:validate:1.0",
                           "urn:samsung:vnf-deploy-interface?module=vnf-deploy-interface&amp;"\
                           "revision=2016-05-15",
                           "urn:samsung:vnf-alarm-interface?module=vnf-alarm-interface&amp;"\
                           "revision=2016-07-08",
                           "urn:samsung:samsung-types?module=samsung-types&amp;"\
                           "revision=2016-05-15",
                           "urn:cesnet:tmc:netopeer:1.0?module=netopeer-cfgnetopeer&amp;"\
                           "revision=2015-05-19&amp;features=ssh,dynamic-modules",
                           "urn:ietf:params:xml:ns:yang:ietf-netconf-server?module="\
                           "ietf-netconf-server&amp;revision=2014-01-24&amp;"\
                           "features=ssh,inbound-ssh,outbound-ssh",
                           "urn:ietf:params:xml:ns:yang:ietf-x509-cert-to-name?module="\
                           "ietf-x509-cert-to-name&amp;revision=2013-03-26",
                           "urn:ietf:params:xml:ns:yang:ietf-netconf-acm?module="\
                           "ietf-netconf-acm&amp;revision=2012-02-22",
                           "urn:ietf:params:xml:ns:yang:ietf-netconf-with-defaults?module="\
                           "ietf-netconf-with-defaults&amp;revision=2010-06-09",
                           "urn:ietf:params:xml:ns:netconf:notification:1.0?"\
                           "module=notifications&amp;revision=2008-07-14",
                           "urn:ietf:params:xml:ns:netmod:notification?"\
                           "module=nc-notifications&amp;revision=2008-07-14",
                           "urn:ietf:params:xml:ns:yang:ietf-netconf-notifications?module="\
                           "ietf-netconf-notifications&amp;revision=2012-02-06",
                           "urn:ietf:params:xml:ns:yang:ietf-netconf-monitoring?"\
                           "module=ietf-netconf-monitoring&amp;revision=2010-10-04",
                           "urn:ietf:params:xml:ns:netconf:base:1.0?module=ietf-netconf&amp;"\
                           "revision=2011-03-08&amp;features=validate",
                           "urn:ietf:params:xml:ns:yang:ietf-yang-types?module="\
                           "ietf-yang-types&amp;revision=2013-07-15",
                           "urn:ietf:params:xml:ns:yang:ietf-inet-types?module="\
                           "ietf-inet-types&amp;revision=2013-07-15"]

        for cap in capability_list:
            elem = etree.Element("capability")
            elem.text = cap
            capabilities_answered.append(elem)
        return

    def rpc_get(self, unused_session, rpc, *unused_params):
        logger.info("rpc_get %s %s %s", unused_session, rpc, unused_params)
        return etree.Element("ok")

    def rpc_get_config(self, unused_session, rpc, *unused_params):

        data = etree.Element("data")
        vnfi = etree.Element("vnfi")
        vnfi.set("xmlns","urn:samsung:vnf-alarm-interface")

        data.append(vnfi)

        for trap in snmp_traps_store:

            notif = """<vnf-alarm xmlns="urn:samsung:vnf-alarm-interface">""" \
                    """<event-time>%(time)s</event-time>""" \
                    """<system-dn>%(systemdn)s</system-dn>""" \
                    """<alarm-group>%(alarmgroup)s</alarm-group>""" \
                    """<alarm-type>%(alarmtype)s</alarm-type>""" \
                    """<alarm-severity>%(alarmseverity)s</alarm-severity>""" \
                    """<alarm-info>%(alarminfo)s</alarm-info>""" \
                    """<alarm-location>%(alarmlocation)s</alarm-location>""" \
                    """<alarm-code>%(alarmcode)s</alarm-code>""" \
                    """<object-id>%(objectid)s</object-id>""" \
                    """<object-type>%(objecttype)s</object-type>""" \
                    """<sequence-number>%(sequencenumber)s</sequence-number>""" \
                    """<notification-type>%(notificationtype)s</notification-type>""" \
                    """</vnf-alarm>""" % trap

            trap = etree.fromstring(notif)

            vnfi.append(trap)

        logger.info("rpc_get_config")
        return data

    def rpc_edit_config(self, unused_session, rpc, *unused_params):
        logger.info("rpc_edit_config")
        return etree.Element("ok")

    def rpc_create_subscription(self, unused_session, rpc, *unused_params):

        logger.info("rpc_create-subscription")

        logger.debug("Session:%s", format(unused_session))
        logger.debug("RPC received:%s", format(etree.tostring(rpc)))

        for param in unused_params:
            logger.debug("Param:" + etree.tostring(param))

        return etree.Element("ok")

# **********************************
# Setup SNMP
# **********************************


def setup_snmp():

    """Configure SNMP server listener"""

    transport_dispatcher = AsynsockDispatcher()

    transport_dispatcher.registerRecvCbFun(snmp_trap_receiver)

    # UDP/IPv4
    transport_dispatcher.registerTransport(
        udp.domainName, udp.UdpSocketTransport().openServerMode(('localhost', 162))
    )

    # UDP/IPv6
    transport_dispatcher.registerTransport(
        udp6.domainName, udp6.Udp6SocketTransport().openServerMode(('::1', 162))
    )

    transport_dispatcher.jobStarted(1)

    try:
        # Dispatcher will never finish as job#1 never reaches zero
        transport_dispatcher.runDispatcher()
    except:
        transport_dispatcher.closeDispatcher()
        raise


# **********************************
# Setup Netconf
# **********************************


def setup_netconf():

    "Configure Netconf server listener"

    global netconf_server # pylint: disable=C0103

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

def set_ip_from_metajs():

    """Sets ip according to content in /meta.js file"""

    f = open("/meta.js", "r")
    metajs = f.read()
    f.close()

    # get ip address
    matched = re.search(""""VNF_IP_ADDR": "([0-9\.]*)""""", metajs)
    ip_address = matched.group(1)

    # get ip device
    devices = os.listdir("/sys/class/net/")
    for dev in devices:
        match = re.search("ens?", dev)
        if match:
            device = dev

    logger.info("Changing ip: "+ip_address+" on device: "+device)

    # set ip
    subprocess.call(shlex.split("ifconfig " + device + " 0.0.0.0"))
    subprocess.call(shlex.split("ip addr add " + ip_address + "/24  dev " + device))
    subprocess.call(shlex.split("sed -i 's/address \\(.*\\)/address "+ip_address+"/' /etc/network/interfaces.d/50-cloud-init.cfg"))

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Netconf Server with SNMP trap listening capabilities")
    parser.add_argument("-s","--skip_ip_set", action="store_true", help="Do not set ip from /meta.js")
    parser.add_argument("-d","--debug", action="store_true", help="Activate debug logs")
    args =  parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if not args.skip_ip_set:
        logger.info("Changing ip address according to /meta.js")
        set_ip_from_metajs()
    else:
        logger.info("Ip address not changed")

    SERVER_DEBUG = logger.getEffectiveLevel() == logging.DEBUG
    logger.info("SERVER_DEBUG:" + str(SERVER_DEBUG))

    setup_netconf()

    # Start the loop for SNMP / Netconf
    logger.info("Listening Netconf - Snmp")
    setup_snmp()


