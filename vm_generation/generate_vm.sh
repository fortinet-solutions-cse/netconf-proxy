#!/usr/bin/env bash

set -x

export UBUNTU_IMAGE_URL=https://cloud-images.ubuntu.com/releases/16.04/release/ubuntu-16.04-server-cloudimg-amd64-disk1.img
export UBUNTU_IMAGE_NAME=$(basename ${UBUNTU_IMAGE_URL})

virsh destroy snmp_netconf
virsh undefine snmp_netconf
rm -f snmp_netconf.img
rm -f user-data
rm -f meta-data
rm -f snmp_netconf-cidata.iso

# *******************************
# Get Ubuntu 16.04 as base image
# *******************************

if [ ! -e ${UBUNTU_IMAGE_NAME} ]; then

   wget ${UBUNTU_IMAGE_URL}
   qemu-img resize ${UBUNTU_IMAGE_NAME} +1Gb
   if [ $? -ne 0 ] ; then
      echo "Failed to resize ubuntu base image. Exiting..."
      exit -1
   fi
fi
cp ${UBUNTU_IMAGE_NAME} snmp_netconf.img

# *******************************
# Install
# *******************************

#sudo guestfish -a snmp_netconf.img --rw -i upload ../init/snmp-netconf.conf /etc/init/snmp-netconf.conf
#sudo guestfish -a snmp_netconf.img --rw -i upload ../netconf-gw.py /opt/netconf-gw.py
#sudo guestfish -a snmp_netconf.img --rw -i upload ../netconf-gw.py /opt/netconf-gw.py


mkdir -p /tmp/guest_snmp/
sudo guestmount /tmp/guest_snmp/ -a snmp_netconf.img -m /dev/sda1


sudo rsync -r -v --max-size=32768 ../*  /tmp/guest_snmp/opt/



#sudo cp -r ../* /tmp/guest_snmp/opt/
sudo cp ../init/snmp-netconf.conf /tmp/guest_snmp/etc/init/
sudo guestunmount /tmp/guest_snmp/



# *******************************
# Test the VM
# *******************************

cat >meta-data <<EOF
instance-id: snmp_netconf
local-hostname: snmp_netconf
EOF

cat >user-data <<EOF
#cloud-config
users:
  - name: ${USER}
    gecos: Host User Replicated
    passwd: 4096$WZV/rmpx9X$M0ZfYfQookX7TXTBf64j31kvRZu3HNPESAVpv8B61qVW89oI86HB2Ihs9pAUrHTvnigdgvUJdBoAaLSG2L0Vi0
    ssh-authorized-keys:
      - $(cat ${HOME}/.ssh/id_rsa.pub)
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
EOF

rm -rf snmp_netconf-cidata.iso
genisoimage -output snmp_netconf-cidata.iso -volid cidata -joliet -rock user-data meta-data

sudo virt-sysprep -a snmp_netconf.img --hostname snmp_netconf --firstboot-command 'sudo apt-get update ; sudo apt-get install -y python-pip python-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev libjpeg8-dev zlib1g-dev ; sudo pip install paramiko pysnmp lxml '

#;sudo apt-get update --fix-missing;sudo apt-get install -y python-pip python-lxml python-paramiko;sudo pip install pysnmp'

virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name snmp_netconf --disk snmp_netconf-cidata.iso,device=cdrom --ram 2048 --vcpus 1 --disk snmp_netconf.img,size=3


sleep 180


virsh destroy snmp_netconf

sleep 45

cp snmp_netconf.img delivery.img
cp snmp_netconf-cidata.iso delivery-cidata.iso

sudo virt-sysprep -a delivery.img --root-password password:m \
    --delete /var/lib/cloud/* \
    --firstboot-command 'useradd -m -p "" vagrant ; chage -d 0 vagrant; ssh-keygen -A; rm -rf /var/lib/cloud/*; cloud-init init'


virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name delivery.img --ram 2048 --vcpus 1  --disk delivery.img,size=3 --disk delivery-cidata.iso,device=cdrom

exit 0






ssh $(arp -a|grep 122|cut -d"(" -f2|cut -d")" -f1)
