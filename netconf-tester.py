#!/usr/bin/python

from netconf import client
from pysnmp.hlapi import *
import time
import logging

def test_basic_get():
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=True)
    assert session

    query = "<get><filter><status/></filter></get>"
    print(session.capabilities)
    rval = session.send_rpc(query)
    print(rval)
    assert rval
    session.close()


def test_create_subscription():
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=True)
    assert session

    query = """<nc:rpc xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" nc:message-id="1">
  <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
    <ncn:filter ncn:type="subtree">
      <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
      <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
      <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
    </ncn:filter>
  </ncn:create-subscription>
</nc:rpc>"""

    rval = session.send_rpc(query)

    print(rval)
    assert rval


def test_create_subscription_and_wait_for_notif():
    session = client.NetconfSSHSession("127.0.0.1",
                                       username="m",
                                       password="admin",
                                       port=830,
                                       debug=True)
    assert session

    query = """<nc:rpc xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" nc:message-id="2">
      <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
        <ncn:filter ncn:type="subtree">
          <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>      
          <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
          <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>    
        </ncn:filter>
      </ncn:create-subscription>
    </nc:rpc>"""

    # print(session.capabilities)
    rval = session.send_rpc(query)

    print(rval)
    assert rval

    time.sleep(10)

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
        print(errorIndication)

    time.sleep(2)

    session.close()


if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)

    # test_basic_get()
    # test_create_subscription()
    test_create_subscription_and_wait_for_notif()
