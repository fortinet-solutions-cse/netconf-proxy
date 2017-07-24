#!/usr/bin/python

from netconf import client
from pysnmp.hlapi import *
import time
import logging
import argparse
import re
import pytest

@pytest.fixture
def server_debug():
    return False

@pytest.fixture
def logger():
    return logging.getLogger(__name__)

def test_get(server_debug, logger):
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=server_debug)
    assert session

    query = "<get><filter><status/></filter></get>"
    logger.info("Capabilities received: " + str(session.capabilities))
    (_,_,answer) = session.send_rpc(query)

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "rpc answer does not match expected result."

    session.close()


def test_create_subscription(server_debug, logger):
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """<ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
    <ncn:filter ncn:type="subtree">
      <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
      <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
      <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
    </ncn:filter>
  </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)
    assert m is not None, "rpc answer does not match expected result."


def test_create_subscription_and_wait_for_notif(server_debug, logger):
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """<ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
          <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
          <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
          <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
      </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "rpc answer does not match expected result."

    time.sleep(3)

    # You can also use:
    # snmptrap -v1 -c public 127.0.0.1 1.3.6.1.4.1.20408.4.1.1.2 127.0.0.1 1 1 123 1.3.6.1.2.1.1.1.0 s test

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget(('127.0.0.1', 162)),
            ContextData(),
            'trap',
            NotificationType(
                ObjectIdentity('1.3.6.1.6.3.1.1.5.2')
            ).addVarBinds(
                ('1.3.6.1.6.3.1.1.4.3.0', '1.3.6.1.4.1.20408.4.1.1.2'),
                ('1.3.6.1.2.1.1.1.0', OctetString('my system'))
            )
        )
    )

    if errorIndication:
        logger.critical(errorIndication)
        assert 0, "Error sending SNMP trap"

    #TODO: Wait for notif
    time.sleep(2)

    session.close()

def test_get_config(server_debug, logger):
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """<nc:get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" ><nc:source><nc:running/></nc:source><nc:filter nc:type="subtree"><vnfi xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/></nc:filter></nc:get-config>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*<data.*<vnfi.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "rpc answer does not match expected result."

def test_get_config_with_multiple_notifs(server_debug, logger):
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=server_debug)
    assert session

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget(('127.0.0.1', 162)),
            ContextData(),
            'trap',
            NotificationType(
                ObjectIdentity('1.3.6.1.6.3.1.1.5.2')
            ).addVarBinds(
                ('1.3.6.1.6.3.1.1.4.3.0', '1.3.6.1.4.1.20408.4.1.1.2'),
                ('1.3.6.1.2.1.1.1.0', OctetString('my system'))
            )
        )
    )

    time.sleep(1)

    if errorIndication:
        logger.critical(errorIndication)
        assert 0, "Error sending SNMP trap"

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget(('127.0.0.1', 162)),
            ContextData(),
            'trap',
            NotificationType(
                ObjectIdentity('1.3.6.1.6.3.1.1.5.2')
            ).addVarBinds(
                ('1.3.6.1.6.3.1.1.4.3.0', '1.3.6.1.4.1.20408.4.1.1.2'),
                ('1.3.6.1.2.1.1.1.0', OctetString('my system'))
            )
        )
    )

    if errorIndication:
        logger.critical(errorIndication)
        assert 0, "Error sending SNMP trap"

    time.sleep(1)
    query = """<nc:get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" ><nc:source><nc:running/></nc:source><nc:filter nc:type="subtree"><vnfi xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/></nc:filter></nc:get-config>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*<data.*<vnfi.*(<vnf-alarm.*){2}</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "rpc answer does not match expected result."


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Tester for Netconf-Proxy project")
    parser.add_argument("-d","--debug", action="store_true", help="Activate debug logs")
    args =  parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logger = logging.getLogger(__name__)  # pylint: disable=C0103

    server_debug = logger.getEffectiveLevel() == logging.DEBUG
    logger.info("SERVER_DEBUG:" + str(server_debug))

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)

    test_get()
    test_create_subscription()
    test_create_subscription_and_wait_for_notif()
    test_get_config()

