#!/usr/bin/python

from netconf import client
from pysnmp.hlapi import *
import time
import logging
import argparse
import re
import pytest
import subprocess

@pytest.fixture
def server_debug():
    return False

@pytest.fixture
def logger():
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)
    return logger


USER = "replace_with_user"
PASSWORD = "replace_with_password"
SUT_IP = "localhost"


def test_std_ssh_cmdline_and_auth_none():

    command = ["echo", """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
        <hello xmlns=\"urn:ietf:params:xml:ns:netconf:base:1.0\">
        <capabilities>
            <capability>urn:ietf:params:netconf:base:1.0</capability>
        </capabilities>
        </hello>
    ]]>]]>

    <nc:rpc xmlns:nc=\"urn:ietf:params:xml:ns:netconf:base:1.0\" nc:message-id=\"1\">
        <ncn:create-subscription xmlns:ncn=\"urn:ietf:params:xml:ns:netconf:notification:1.0\">
            <ncn:filter ncn:type=\"subtree\">
                <vnf-alarm xmlns=\"urn:samsung:vnf-alarm-interface\" xmlns:vaintf=\"urn:samsung:vnf-alarm-interface\"/>      
                <vnf-alarm-rebuild-request xmlns=\"urn:samsung:vnf-alarm-interface\" xmlns:vaintf=\"urn:samsung:vnf-alarm-interface\"/>
                <default-parameter-loss-notification xmlns=\"urn:samsung:vnf-deploy-interface\" 
                xmlns:vdintf=\"urn:samsung:vnf-deploy-interface\"/>
            </ncn:filter>
        </ncn:create-subscription>
    </nc:rpc>
    ]]>]]>

    <rpc message-id=\"2\" xmlns=\"urn:ietf:params:xml:ns:netconf:base:1.0\">
        <close-session/>
    </rpc>
    ]]>]]>"""]

    p1 = subprocess.Popen(command, stdout=subprocess.PIPE)
    p2 = subprocess.Popen(["sshpass", "-p", PASSWORD,
                           "ssh", USER+"@"+SUT_IP,"-p 830", "-s","netconf"],
                           stdin=p1.stdout, stdout=subprocess.PIPE)
    p1.stdout.close()
    output,err=p2.communicate()

    assert output is not None
    assert err is None

    m = re.search("<rpc-reply.*ok.*</rpc-reply", output, flags=re.MULTILINE|re.DOTALL)
    assert m is not None, "Rpc reply does not seem to be ok"


def test_get(server_debug, logger):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    query = "<get><filter><status/></filter></get>"
    logger.info("Capabilities received: " + str(session.capabilities))
    (_,_,answer) = session.send_rpc(query)

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    session.close()


def test_create_subscription(server_debug, logger):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """
    <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
            <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
            <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
            <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" 
            xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
    </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    session.close()

def test_create_subscription_and_wait_for_notif(server_debug, logger, caplog):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """
    <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
          <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
          <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
          <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface"
          xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
    </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    time.sleep(0.2)

    # You can also use:
    # snmptrap -v1 -c public 127.0.0.1 1.3.6.1.4.1.20408.4.1.1.2 127.0.0.1 1 1 123 1.3.6.1.2.1.1.1.0 s test

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    out = caplog.text

    m = re.search("<notification.*alarm-type.*alarm-info.*alarm-code.*</notification", out, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Notification has not been received"

    session.close()

def test_get_config(server_debug, logger):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    query = """
    <nc:get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" >
        <nc:source>
           <nc:running/>
        </nc:source>
        <nc:filter nc:type="subtree">
            <vnfi xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
        </nc:filter>
    </nc:get-config>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*<data.*<vnfi.*</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    session.close()

def test_get_config_after_multiple_traps(server_debug, logger):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    if errorIndication:
        logger.critical(errorIndication)
        assert 0, "Error sending SNMP trap"

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    query = """
    <nc:get-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" >
        <nc:source>
            <nc:running/>
        </nc:source>
        <nc:filter nc:type="subtree">
            <vnfi xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
        </nc:filter>
    </nc:get-config>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: "+str(answer))

    m = re.search("<rpc-reply.*<data.*<vnfi.*(<vnf-alarm.*){2}</rpc-reply", answer, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    session.close()


def test_notif_only_sent_after_create_subscription(server_debug, logger, caplog):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session


    time.sleep(0.2)

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    out = caplog.text

    m = re.search("<notification.*alarm-type.*alarm-info.*alarm-code.*</notification", out, flags=re.MULTILINE|re.DOTALL)

    assert m is None, "Notification has been received"

    query = """
    <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
            <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
            <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
            <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface"
            xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
    </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: " + str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE | re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    time.sleep(0.2)


    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    out = caplog.text

    m = re.search("<notification.*alarm-type.*alarm-info.*alarm-code.*</notification", out, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Notification has not been received"

    session.close()


def test_edit_config(server_debug, logger, caplog):

    session = client.NetconfSSHSession(SUT_IP,
                                       username=USER,
                                       password=PASSWORD,
                                       port=830,
                                       debug=server_debug)
    assert session

    time.sleep(0.2)

    # Create a subscription to receive notifications
    query = """
    <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
            <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
            <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
            <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface"
            xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
    </ncn:create-subscription>"""

    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: " + str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE | re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    time.sleep(0.2)

    # Send trap to generate notification

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    out = caplog.text

    m = re.search("<notification.*alarm-type.*alarm-info.*alarm-location.*FUPC0.*alarm-code.*object-id.*7401f9d7-2d5e-4cfe-8ae1-d2adebf085fb.*</notification", out, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Notification has been received with incorrect values"


    #Issue edit-config to change object-id and alarm-location values

    query = """
    <nc:edit-config xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0">
        <nc:target>
            <nc:running/>    
        </nc:target>
        <nc:config>
            <vnfi xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface">
                <object-id>25c53e93-8fd0-41ee-bbff-045b4db09cbe</object-id>
                <object-name>GONE</object-name>
                <object-type>VNF Instance</object-type>
                <vnfci>
                    <object-id>2b4850dc-6e2e-43e5-aa7e-f383e4851fc7</object-id>
                    <object-name>GONE-PRX-00</object-name>
                    <object-type>VNF Component</object-type>
                    <vnfc-type>PRX</vnfc-type>
                    <vnfc-unit-id>0</vnfc-unit-id>
                    <server-id>92746eb6-be38-4f4a-9c71-edfa92d3965d</server-id>
                    <host-name>nova9</host-name>
                    <requested-resource-state>using</requested-resource-state>
                    <redundancy-model>ActivePassive</redundancy-model>
                    <ha-type>1:0</ha-type>
                    <interface>
                        <name>GONE-PRX-00-physnet11-00</name>
                        <id>dbcd02c0-4f1d-4d9d-b05d-565fa273ecbe</id>
                        <mac-address>fa:16:3e:50:ae:cb</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.160.4</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                </vnfci>
                <vnfci>
                    <object-id>832c10dd-80de-4084-8393-f7cdc3b74040</object-id>
                    <object-name>GONE-GAT-00</object-name>
                     <object-type>VNF Component</object-type>
                     <vnfc-type>GAT</vnfc-type>
                     <vnfc-unit-id>0</vnfc-unit-id>
                     <server-id>d78c831f-bf0f-4259-9df1-5c5570be138d</server-id>
                     <host-name>nova9</host-name>
                     <requested-resource-state>using</requested-resource-state>
                     <redundancy-model>ActivePassive</redundancy-model>
                     <ha-type>1:0</ha-type>
                    <interface>
                        <name>GONE-GAT-00-physnet13-01</name>
                        <id>231803a6-bac5-4b15-b051-ef9c961bcc75</id>
                        <mac-address>fa:16:3e:a4:36:7c</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.165.3</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-00-physnet14-02</name>
                        <id>6484d1d1-266c-4c2a-8b3d-99c4cb2c9417</id>
                        <mac-address>fa:16:3e:0c:73:87</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.161.3</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-00-physnet15-03</name>
                        <id>f46f665f-75e7-460b-8c7e-87a407e8f6cf</id>
                        <mac-address>fa:16:3e:3d:25:3f</mac-address>
                        <ip-addresses>
                            <ip-address>32.4.1.121</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-00-physnet11-00</name>
                        <id>fa5b0f61-625e-487b-96a6-60fadfc2f7f1</id>
                        <mac-address>fa:16:3e:82:e6:36</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.160.5</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                </vnfci>
                <vnfci>
                    <object-id>8fc7c2a4-50ac-4df5-85cb-42adc31e7614</object-id>
                    <object-name>GONE-GAT-01</object-name>
                    <object-type>VNF Component</object-type>
                    <vnfc-type>GAT</vnfc-type>
                    <vnfc-unit-id>1</vnfc-unit-id>
                    <server-id>7e30de07-8884-480f-be54-bbdc896cf983</server-id>
                    <host-name>nova9</host-name>
                    <requested-resource-state>using</requested-resource-state>
                    <redundancy-model>ActivePassive</redundancy-model>
                    <ha-type>1:0</ha-type>
                    <interface>
                        <name>GONE-GAT-01-physnet13-01</name>
                        <id>75b41c95-0c03-4e89-9ce2-a3b1b1b60fbe</id>
                        <mac-address>fa:16:3e:92:b1:12</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.165.5</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-01-physnet11-00</name>
                        <id>8994399b-f650-4800-93db-392bb8f0e1a9</id>
                        <mac-address>fa:16:3e:3a:94:a2</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.160.8</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-01-physnet14-02</name>
                        <id>94c5a0df-83c2-48bc-ba45-122e30e95fdf</id>
                        <mac-address>fa:16:3e:55:61:2e</mac-address>
                        <ip-addresses>
                            <ip-address>128.0.161.5</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                    <interface>
                        <name>GONE-GAT-01-physnet15-03</name>
                        <id>d305308e-8b9d-4a9f-a504-be2a735e323e</id>
                        <mac-address>fa:16:3e:c6:1a:ed</mac-address>
                        <ip-addresses>
                            <ip-address>32.4.1.123</ip-address>
                            <ip-version>ipv4</ip-version>
                        </ip-addresses>
                    </interface>
                </vnfci>
            </vnfi>
        </nc:config>
    </nc:edit-config>"""


    (_, _, answer) = session.send_rpc(query)

    logger.info("Answer received: " + str(answer))

    m = re.search("<rpc-reply.*ok.*</rpc-reply", answer, flags=re.MULTILINE | re.DOTALL)

    assert m is not None, "Rpc reply does not seem to be ok"

    # Send trap to generate notification with new values

    errorIndication, errorStatus, errorIndex, varBinds = next(
        sendNotification(
            SnmpEngine(),
            CommunityData('public', mpModel=0),
            UdpTransportTarget((SUT_IP, 162)),
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

    time.sleep(0.2)

    out = caplog.text

    m = re.search("<notification.*alarm-type.*alarm-info.*alarm-location.*GONE.*alarm-code.*object-id.*25c53e93-8fd0-41ee-bbff-045b4db09cbe.*</notification", out, flags=re.MULTILINE|re.DOTALL)

    assert m is not None, "Notification has been received with incorrect values"

    session.close()


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

    test_std_ssh_cmdline_and_auth_none(True, logger)
    test_get()
    test_create_subscription()
    test_create_subscription_and_wait_for_notif()
    test_get_config()

