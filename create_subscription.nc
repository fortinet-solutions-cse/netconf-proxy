<?xml version="1.0" encoding="UTF-8"?>
<nc:rpc xmlns:nc="urn:ietf:params:xml:ns:netconf:base:1.0" nc:message-id="1">
  <ncn:create-subscription xmlns:ncn="urn:ietf:params:xml:ns:netconf:notification:1.0">
    <ncn:filter ncn:type="subtree">
      <vnf-alarm xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
      <vnf-alarm-rebuild-request xmlns="urn:samsung:vnf-alarm-interface" xmlns:vaintf="urn:samsung:vnf-alarm-interface"/>
      <default-parameter-loss-notification xmlns="urn:samsung:vnf-deploy-interface" xmlns:vdintf="urn:samsung:vnf-deploy-interface"/>
    </ncn:filter>
  </ncn:create-subscription>
</nc:rpc>