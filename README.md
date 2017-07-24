# netconf-snmp-gw

This proxy listens both netconf and snmp. It accepts netconf subscriptions and forwards snmp traps to netconf clients previously subscribed


To start the server run:
-  ./netconf-proxy.py 
   
To test the server run:
-   pytest -v ./netconf-tester.py
   
To generate a vm that runs this server as a systemd server run:

-   cd vm_generation/
-   ./generate_vm.sh