#!/bin/bash

virsh destroy snmp_netconf
virsh undefine snmp_netconf
virsh destroy delivery
virsh undefine delivery

rm -f snmp_netconf.img
rm -f snmp_netconf-cidata.iso
rm -f user-data
rm -f meta-data
rm -f install_script
rm -f install_script_for_delivery
rm -f delivery.img
rm -f delivery-cidata.iso