review : 0

VLAN is to separate different user group(cooperation)

Openstack was born to compete with big cloud platform

# Intro

Mac in local Lan(layer 2)

IP is to navigate btw network(layer 3)

> overlay vs underlay
> 

**Openstack**

focus on Infrastructure(IaaS)

manange VM, storage and networking

components: nova, neutron, cinder, glance, keystone

**Kubernetes**

focus con Container Orchestration(CaaS)

auto scale, ha, rolling update

components: kube-apiserver, Services, Deployment, Ingress,..Pods

OpenStack provide the infrastructure which K8s orchestrates containerized workloads on top of it.

> VMs in nodes are communicating with each other via a tunnel : VXLAN
> 

monitor via Granfana

# Nova - Compute Service

nova-api will orchestrate thing (just like k8s)

> all nova service will using message queue to communicate with each other
> 

(OVS Network)

# flow

1. store to nova db
2. send put request to nova-api 
3. store in db
4. request image metadata(glance-api)
5. call neutron-server to open vSwitch bridge
6. nova-scheduler select host
7. nova-conductorr sen build request
8. compute prepare instance on hypervisor
9. pull image from glance store
10. plug vNic into OVS net
11. libvirt launch VM

# Neutron = network service

> also using message queue
> 

# block storage service - Cinder

> AMQP : advanced message queuing protocol
> 

Octavia : support for load balancer(via octavia-api)

Manila: NFS

Designate: DNS Service