#!/usr/bin/env bash


export UBUNTU_IMAGE_URL=https://cloud-images.ubuntu.com/releases/14.04/release/ubuntu-14.04-server-cloudimg-amd64-disk1.img
export UBUNTU_IMAGE_NAME=$(basename ${UBUNTU_IMAGE_URL})

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





# *******************************
# Test the VM
# *******************************

virt-install --connect qemu:///system --noautoconsole --filesystem ${PWD},shared_dir --import --name snmp_netconf.img --ram 2048 --vcpus 1 --disk ${CLASSIFIER1_NAME}.img,size=3 --disk ${CLASSIFIER1_NAME}-cidata.iso,device=cdrom --network bridge=virbr1,mac=${CLASSIFIER1_MAC}