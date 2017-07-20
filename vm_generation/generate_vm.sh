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
cp ${UBUNTU_IMAGE_NAME} snmp_netconf.img

#************************************************
# Copy netconf server code to image
#************************************************

mkdir -p /tmp/guest_snmp/
sudo guestmount /tmp/guest_snmp/ -a snmp_netconf.img -m /dev/sda1

sudo rsync -r -v --max-size=32768 ../*  /tmp/guest_snmp/opt/

sudo guestunmount /tmp/guest_snmp/

#************************************************
# Generate Cloud Init for VM
#************************************************

cat >meta-data <<EOF
instance-id: snmp_netconf
local-hostname: snmp_netconf
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

rm -rf snmp_netconf-cidata.iso
genisoimage -output snmp_netconf-cidata.iso -volid cidata -joliet -rock user-data meta-data

cat >install_script << EOF
#!/bin/bash
sudo apt-get update
sudo apt-get install -y python-pip python-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev libjpeg8-dev zlib1g-dev
sudo pip install paramiko pysnmp lxml
cp /opt/service/snmp-netconf.service /lib/systemd/system/snmp-netconf.service
systemctl enable snmp-netconf
systemctl start snmp-netconf
EOF

sudo virt-sysprep -a snmp_netconf.img --hostname snmp_netconf --root-password password:m --firstboot install_script

virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name snmp_netconf --disk snmp_netconf-cidata.iso,device=cdrom --ram 2048 --vcpus 1 --disk snmp_netconf.img,size=3 --network network=default,mac="08:00:27:4c:10:10"


host_ip=$(virsh net-dhcp-leases default|grep "08:00:27:4c:10:10" |egrep -Eo "([0-9]*\.[0-9]*\.[0-9]*\.[0-9]*)")

echo "Scanning port 830 on server:"
until ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null $host_ip sudo netstat -puntax|grep ":::830"
do
  sleep 1
  echo -ne "."
done

echo "Server seems to have started properly. Generating final image"

sleep 180

virsh destroy snmp_netconf

sleep 20

cp snmp_netconf.img delivery.img
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

exit 0

#************************************************
# Bonus: Run this to test VM
# Note when you run it first time it will not
# be usable for other system/vim
#************************************************

virsh undefine snmp_netconf
virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name delivery --ram 2048 --vcpus 1  --disk delivery.img,size=3 --disk delivery-cidata.iso,device=cdrom --network network=default,mac="08:00:27:4c:10:10"





ssh $(arp -a|grep 122|cut -d"(" -f2|cut -d")" -f1)
