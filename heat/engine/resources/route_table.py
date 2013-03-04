# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

from quantumclient.common.exceptions import QuantumClientException

from heat.openstack.common import log as logging
from heat.engine import resource

logger = logging.getLogger(__name__)


class RouteTable(resource.Resource):
    tags_schema = {'Key': {'Type': 'String',
                           'Required': True},
                   'Value': {'Type': 'String',
                             'Required': True}}

    properties_schema = {
        'VpcId': {
            'Type': 'String',
            'Required': True},
        'Tags': {'Type': 'List', 'Schema': {
            'Type': 'Map',
            'Implemented': False,
            'Schema': tags_schema}}
    }

    def __init__(self, name, json_snippet, stack):
        super(RouteTable, self).__init__(name, json_snippet, stack)

    def handle_create(self):
        client = self.quantum()
        props = {'name': self.physical_resource_name()}
        router = client.create_router({'router': props})['router']

        router_id = router['id']

        # add this router to the list of all routers in the VPC
        vpc = self.stack[self.properties.get('VpcId')]
        vpc_md = vpc.metadata
        vpc_md['all_router_ids'].append(router_id)
        vpc.metadata = vpc_md

        # TODO sbaker all_router_ids has changed, any VPCGatewayAttachment
        # for this vpc needs to be notified
        md = {
            'router_id': router_id
        }
        self.metadata = md

    def handle_delete(self):
        client = self.quantum()

        router_id = self.metadata['router_id']
        try:
            client.delete_router(router_id)
        except QuantumClientException as ex:
            if ex.status_code != 404:
                raise ex

        # remove this router from the list of all routers in the VPC
        vpc = self.stack[self.properties.get('VpcId')]
        vpc_md = vpc.metadata
        vpc_md['all_router_ids'].remove(router_id)
        vpc.metadata = vpc_md
        # TODO sbaker all_router_ids has changed, any VPCGatewayAttachment
        # for this vpc needs to be notified

    def handle_update(self, json_snippet):
        return self.UPDATE_REPLACE


class SubnetRouteTableAssocation(resource.Resource):

    properties_schema = {
        'RouteTableId': {
            'Type': 'String',
            'Required': True},
        'SubnetId': {
            'Type': 'String',
            'Required': True}
    }

    def __init__(self, name, json_snippet, stack):
        super(SubnetRouteTableAssocation, self).__init__(
            name, json_snippet, stack)

    def handle_create(self):
        client = self.quantum()
        subnet = self.stack[self.properties.get('SubnetId')]
        subnet_id = subnet.metadata['subnet_id']
        previous_router_id = subnet.metadata['router_id']

        route_table = self.stack[self.properties.get('RouteTableId')]
        router_id = route_table.metadata['router_id']

        #remove the default router association for this subnet.
        try:
            client.remove_interface_router(
                previous_router_id,
                {'subnet_id': subnet_id})
        except QuantumClientException as ex:
            if ex.status_code != 404:
                raise ex

        client.add_interface_router(
            router_id, {'subnet_id': subnet_id})

    def handle_delete(self):
        client = self.quantum()
        subnet = self.stack[self.properties.get('SubnetId')]
        subnet_id = subnet.metadata['subnet_id']
        default_router_id = subnet.metadata['default_router_id']

        route_table = self.stack[self.properties.get('RouteTableId')]
        router_id = route_table.metadata['router_id']

        try:
            client.remove_interface_router(router_id, {
                'subnet_id': subnet_id})
        except QuantumClientException as ex:
            if ex.status_code != 404:
                raise ex

        # add back the default router
        client.add_interface_router(
            default_router_id, {'subnet_id': subnet_id})

    def handle_update(self, json_snippet):
        return self.UPDATE_REPLACE


def resource_mapping():
    return {
        'AWS::EC2::RouteTable': RouteTable,
        'AWS::EC2::SubnetRouteTableAssocation': SubnetRouteTableAssocation,
    }
