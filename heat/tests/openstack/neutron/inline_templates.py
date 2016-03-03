#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

SPOOL_TEMPLATE = '''
heat_template_version: 2015-04-30
description: Template to test subnetpool Neutron resource
resources:
  sub_pool:
    type: OS::Neutron::SubnetPool
    properties:
      name: the_sp
      prefixes:
        - 10.1.0.0/16
      address_scope: test
      default_quota: 2
      default_prefixlen: 28
      min_prefixlen: 8
      max_prefixlen: 32
      is_default: False
      tenant_id: c1210485b2424d48804aad5d39c61b8f
      shared: False
'''

SPOOL_MINIMAL_TEMPLATE = '''
heat_template_version: 2015-04-30
description: Template to test subnetpool Neutron resource
resources:
  sub_pool:
    type: OS::Neutron::SubnetPool
    properties:
      prefixes:
        - 10.0.0.0/16
        - 10.1.0.0/16
'''

RBAC_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Template to test rbac-policy Neutron resource
resources:
  rbac:
    type: OS::Neutron::RBACPolicy
    properties:
      object_type: network
      target_tenant: d1dbbed707e5469da9cd4fdd618e9706
      action: access_as_shared
      object_id: 9ba4c03a-dbd5-4836-b651-defa595796ba
'''

LB_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Create a loadbalancer
resources:
  lb:
    type: OS::Neutron::LBaaS::LoadBalancer
    properties:
      name: my_lb
      description: my loadbalancer
      vip_address: 10.0.0.4
      vip_subnet: sub123
      provider: octavia
      tenant_id: 1234
      admin_state_up: True
'''

LISTENER_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Create a listener
resources:
  listener:
    type: OS::Neutron::LBaaS::Listener
    properties:
      protocol_port: 80
      protocol: TCP
      loadbalancer: 123
      name: my_listener
      description: my listener
      admin_state_up: True
      default_tls_container_ref: ref
      sni_container_refs:
        - ref1
        - ref2
      connection_limit: -1
      tenant_id: 1234
'''

POOL_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Create a pool
resources:
  pool:
    type: OS::Neutron::LBaaS::Pool
    properties:
      name: my_pool
      description: my pool
      session_persistence:
        type: HTTP_COOKIE
      lb_algorithm: ROUND_ROBIN
      listener: 123
      protocol: HTTP
      admin_state_up: True
'''

MEMBER_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Create a pool member
resources:
  member:
    type: OS::Neutron::LBaaS::PoolMember
    properties:
      pool: 123
      address: 1.2.3.4
      protocol_port: 80
      weight: 1
      subnet: sub123
      admin_state_up: True
'''

MONITOR_TEMPLATE = '''
heat_template_version: 2016-04-08
description: Create a health monitor
resources:
  monitor:
    type: OS::Neutron::LBaaS::HealthMonitor
    properties:
      admin_state_up: True
      delay: 3
      expected_codes: 200-202
      http_method: HEAD
      max_retries: 5
      pool: 123
      timeout: 10
      type: HTTP
      url_path: /health
'''
