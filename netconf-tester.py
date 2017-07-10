#!/usr/bin/python

from netconf import client
import time
import logging
import sys

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

    #print(session.capabilities)
    rval = session.send_rpc(query)

    print(rval)
    assert rval



def test_create_subscription_and_receive_notif():

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

    while True:
        time.sleep(1)
        sys.stdout.write(".")
        sys.stdout.flush()


    session.close()




if __name__ == "__main__":

    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)


    test_basic_get()
    test_create_subscription()
    test_create_subscription_and_receive_notif()