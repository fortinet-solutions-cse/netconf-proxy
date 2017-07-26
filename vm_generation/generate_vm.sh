#!/bin/bash
#************************************************
# Generate VM with Netconf Proxy
#
# Use: ./generate_vm
#
# Output will be:
#    delivery.img
#    delivery-cidata.img
#
# Miguel Angel Muñoz Gonzalez
# magonzalez(at)fortinet.com
#
#************************************************

set -x

export UBUNTU_IMAGE_URL=https://cloud-images.ubuntu.com/releases/16.04/release/ubuntu-16.04-server-cloudimg-amd64-disk1.img
export UBUNTU_IMAGE_NAME=$(basename ${UBUNTU_IMAGE_URL})

./clean.sh

#************************************************
# Get Ubuntu 16.04 as base image
#************************************************

if [ ! -e ${UBUNTU_IMAGE_NAME} ]; then

   wget ${UBUNTU_IMAGE_URL}
   qemu-img resize ${UBUNTU_IMAGE_NAME} +1Gb
   if [ $? -ne 0 ] ; then
      echo "Failed to resize ubuntu base image. Exiting..."
      exit -1
   fi
fi
cp ${UBUNTU_IMAGE_NAME} netconf_proxy.img

#************************************************
# Copy netconf server code to image
#************************************************

mkdir -p /tmp/guest_snmp/
sudo guestmount /tmp/guest_snmp/ -a netconf_proxy.img -m /dev/sda1

sudo rsync -r -v --max-size=32768 ../*  /tmp/guest_snmp/opt/
sudo rsync -r -v meta.js  /tmp/guest_snmp/

sudo guestunmount /tmp/guest_snmp/

#************************************************
# Generate Cloud Init for VM
#************************************************

cat >meta-data <<EOF
instance-id: netconf_proxy
local-hostname: netconf_proxy
EOF

#Note password hashed below is 'm'

cat >user-data <<EOF
#cloud-config
users:
  - name: ${USER}
    gecos: Host User Replicated
    passwd: \$1\$xyz\$Ilzr7fdQW.frxCgmgIgVL0
    ssh-authorized-keys:
      - $(cat ${HOME}/.ssh/id_rsa.pub)
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    inactive: false
    lock_passwd: false
  - name: netconf
    gecos: Netconf User
    passwd: \$1\$xyz\$Ilzr7fdQW.frxCgmgIgVL0
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    inactive: false
    lock_passwd: false
EOF


#************************************************
# Start VM and install additional stuff
#************************************************

rm -rf netconf_proxy-cidata.iso
genisoimage -output netconf_proxy-cidata.iso -volid cidata -joliet -rock user-data meta-data

cat >install_script << EOF

echo "** Updating system..."

sudo apt-get update
sudo apt-get install -y python-pip python-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev libjpeg8-dev zlib1g-dev

echo "** Installing pip..."

sudo pip install paramiko pysnmp lxml

echo "** Copying service file..."

cp /opt/service/netconf-proxy.service /lib/systemd/system/netconf-proxy.service

echo "** Enabling and starting service..."

systemctl enable netconf-proxy
systemctl start netconf-proxy

echo "** Removing Cloud Init Service..."

echo 'datasource_list: [ None ]' | sudo -s tee /etc/cloud/cloud.cfg.d/90_dpkg.cfg
sudo dpkg-reconfigure -f noninteractive cloud-init

echo "** Setting static ip..."
echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
sed -i 's/iface ens\([0-9]\) inet dhcp/iface ens\1 inet static\naddress 192.168.122.10\nnetmask 255.255.255.0/' /etc/network/interfaces.d/50-cloud-init.cfg
EOF

sleep 1

sudo virt-sysprep -a netconf_proxy.img --hostname netconf_proxy --root-password password:m --firstboot install_script

virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name netconf_proxy --ram 2048 --vcpus 1 --disk netconf_proxy.img,size=3 --disk netconf_proxy-cidata.iso,device=cdrom --network network=default,mac="08:00:27:4c:10:10"


host_ip=$(virsh net-dhcp-leases default|grep "08:00:27:4c:10:10" |egrep -Eo "([0-9]*\.[0-9]*\.[0-9]*\.[0-9]*)")
host_ip="192.168.122.11"

echo "Scanning port 830 on server:"
until ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $host_ip sudo netstat -puntax|grep ":::830"
do
  sleep 1
  echo -ne "."
done

echo "Server seems to have started properly. Generating final image"

sleep 100

virsh destroy netconf_proxy

sleep 20

cp netconf_proxy.img delivery_test.img

rm -rf delivery
mkdir ./delivery
cp delivery_test.img ./delivery/delivery.img
echo "Your image is ready on \"delivery/delivery.img\". You can play with .\delivery_test.img on this directory"

exit 0


#************************************************
# Bonus: Run this to test VM
#************************************************
virsh undefine netconf_proxy
virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name delivery --ram 2048 --vcpus 1  --disk delivery_test.img,size=3 --network network=default,mac="08:00:27:4c:10:10"



virsh destroy netconf_proxy

sleep 20

cp netconf_proxy.img delivery.img
genisoimage -output delivery-cidata.iso -volid cidata -joliet -rock user-data meta-data


cat >install_script_for_delivery <<EOF
useradd -m -p "" vagrant
chage -d 0 vagrant
ssh-keygen -A
rm -rf /var/lib/cloud/*
cloud-init init
EOF

sudo virt-sysprep -a delivery.img --root-password password:m \
    --delete /var/lib/cloud/* \
    --firstboot install_script_for_delivery

rm -rf delivery\
mkdir ./delivery\
cp delivery.img .\delivery\delivery.img
cp delivery-cidata.iso .\delivery\delivery-cidata.iso
echo "Your image is ready on \"delivery\" directory. You can play with delivery.img on this directory"



exit 0

#************************************************
# Bonus: Run this to test VM
# Note when you run it first time it will not
# be usable for other system/vim
#************************************************

virsh undefine netconf_proxy
virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name delivery --ram 2048 --vcpus 1  --disk delivery.img,size=3 --disk delivery-cidata.iso,device=cdrom --network network=default,mac="08:00:27:4c:10:10"





ssh $(arp -a|grep 122|cut -d"(" -f2|cut -d")" -f1)
