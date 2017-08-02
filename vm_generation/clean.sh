#!/bin/bash

virsh destroy netconf_proxy
virsh undefine netconf_proxy
virsh destroy delivery
virsh undefine delivery

rm -f netconf_proxy.img
rm -f netconf_proxy-cidata.iso
rm -f user-data
rm -f meta-data
rm -f install_script
rm -f install_script_for_delivery
rm -f delivery_test.img
rm -rf delivery
guestunmount /tmp/guest_netconf/
rm -rf /tmp/guest_netconf/
