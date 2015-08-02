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

import mock
from neutronclient.common import exceptions as qe

from heat.common import exception
from heat.engine.clients.os import neutron
from heat.tests import common
from heat.tests import utils


class NeutronClientPluginTestCase(common.HeatTestCase):
    def setUp(self):
        super(NeutronClientPluginTestCase, self).setUp()
        self.neutron_client = mock.MagicMock()

        con = utils.dummy_context()
        c = con.clients
        self.neutron_plugin = c.client_plugin('neutron')
        self.neutron_plugin._client = self.neutron_client


class NeutronClientPluginTests(NeutronClientPluginTestCase):
    def setUp(self):
        super(NeutronClientPluginTests, self).setUp()
        self.mock_find = self.patchobject(neutron.neutronV20,
                                          'find_resourceid_by_name_or_id')
        self.mock_find.return_value = 42

    def test_find_neutron_resource(self):
        props = {'net': 'test_network'}

        res = self.neutron_plugin.find_neutron_resource(props, 'net',
                                                        'network')
        self.assertEqual(42, res)
        self.mock_find.assert_called_once_with(self.neutron_client, 'network',
                                               'test_network')

    def test_resolve_network(self):
        props = {'net': 'test_network'}

        res = self.neutron_plugin.resolve_network(props, 'net', 'net_id')
        self.assertEqual(42, res)
        self.mock_find.assert_called_once_with(self.neutron_client, 'network',
                                               'test_network')

        # check resolve if was send id instead of name
        props = {'net_id': 77}
        res = self.neutron_plugin.resolve_network(props, 'net', 'net_id')
        self.assertEqual(77, res)
        # in this case find_resourceid_by_name_or_id is not called
        self.mock_find.assert_called_once_with(self.neutron_client, 'network',
                                               'test_network')

    def test_resolve_subnet(self):
        props = {'snet': 'test_subnet'}

        res = self.neutron_plugin.resolve_subnet(props, 'snet', 'snet_id')
        self.assertEqual(42, res)
        self.mock_find.assert_called_once_with(self.neutron_client, 'subnet',
                                               'test_subnet')

        # check resolve if was send id instead of name
        props = {'snet_id': 77}
        res = self.neutron_plugin.resolve_subnet(props, 'snet', 'snet_id')
        self.assertEqual(77, res)
        # in this case find_resourceid_by_name_or_id is not called
        self.mock_find.assert_called_once_with(self.neutron_client, 'subnet',
                                               'test_subnet')

    def test_get_secgroup_uuids(self):
        # test get from uuids
        sgs_uuid = ['b62c3079-6946-44f5-a67b-6b9091884d4f',
                    '9887157c-d092-40f5-b547-6361915fce7d']

        sgs_list = self.neutron_plugin.get_secgroup_uuids(sgs_uuid)
        self.assertEqual(sgs_uuid, sgs_list)
        # test get from name, return only one
        sgs_non_uuid = ['security_group_1']
        expected_groups = ['0389f747-7785-4757-b7bb-2ab07e4b09c3']
        fake_list = {
            'security_groups': [
                {
                    'tenant_id': 'test_tenant_id',
                    'id': '0389f747-7785-4757-b7bb-2ab07e4b09c3',
                    'name': 'security_group_1',
                    'security_group_rules': [],
                    'description': 'no protocol'
                }
            ]
        }
        self.neutron_client.list_security_groups.return_value = fake_list
        self.assertEqual(expected_groups,
                         self.neutron_plugin.get_secgroup_uuids(sgs_non_uuid))
        # test only one belong to the tenant
        fake_list = {
            'security_groups': [
                {
                    'tenant_id': 'test_tenant_id',
                    'id': '0389f747-7785-4757-b7bb-2ab07e4b09c3',
                    'name': 'security_group_1',
                    'security_group_rules': [],
                    'description': 'no protocol'
                },
                {
                    'tenant_id': 'not_test_tenant_id',
                    'id': '384ccd91-447c-4d83-832c-06974a7d3d05',
                    'name': 'security_group_1',
                    'security_group_rules': [],
                    'description': 'no protocol'
                }
            ]
        }
        self.neutron_client.list_security_groups.return_value = fake_list
        self.assertEqual(expected_groups,
                         self.neutron_plugin.get_secgroup_uuids(sgs_non_uuid))
        # test there are two securityGroups with same name, and the two
        # all belong to the tenant
        fake_list = {
            'security_groups': [
                {
                    'tenant_id': 'test_tenant_id',
                    'id': '0389f747-7785-4757-b7bb-2ab07e4b09c3',
                    'name': 'security_group_1',
                    'security_group_rules': [],
                    'description': 'no protocol'
                },
                {
                    'tenant_id': 'test_tenant_id',
                    'id': '384ccd91-447c-4d83-832c-06974a7d3d05',
                    'name': 'security_group_1',
                    'security_group_rules': [],
                    'description': 'no protocol'
                }
            ]
        }
        self.neutron_client.list_security_groups.return_value = fake_list
        self.assertRaises(exception.PhysicalResourceNameAmbiguity,
                          self.neutron_plugin.get_secgroup_uuids,
                          sgs_non_uuid)


class NeutronConstraintsValidate(common.HeatTestCase):
    scenarios = [
        ('validate_network',
            dict(constraint_class=neutron.NetworkConstraint,
                 resource_type='network')),
        ('validate_port',
            dict(constraint_class=neutron.PortConstraint,
                 resource_type='port')),
        ('validate_router',
            dict(constraint_class=neutron.RouterConstraint,
                 resource_type='router')),
        ('validate_subnet',
            dict(constraint_class=neutron.SubnetConstraint,
                 resource_type='subnet'))
    ]

    def test_validate(self):
        nc = mock.Mock()
        mock_create = self.patchobject(neutron.NeutronClientPlugin, '_create')
        mock_create.return_value = nc
        mock_find = self.patchobject(neutron.neutronV20,
                                     'find_resourceid_by_name_or_id')
        mock_find.side_effect = ['foo',
                                 qe.NeutronClientException(status_code=404)]

        constraint = self.constraint_class()
        ctx = utils.dummy_context()
        self.assertTrue(constraint.validate("foo", ctx))
        self.assertFalse(constraint.validate("bar", ctx))
        mock_find.assert_has_calls([mock.call(nc, self.resource_type, 'foo'),
                                    mock.call(nc, self.resource_type, 'bar')])


class TestIPConstraint(common.HeatTestCase):

    def setUp(self):
        super(TestIPConstraint, self).setUp()
        self.constraint = neutron.IPConstraint()

    def test_validate_ipv4_format(self):
        validate_format = [
            '1.1.1.1',
            '1.0.1.1',
            '255.255.255.255'
        ]
        for ip in validate_format:
            self.assertTrue(self.constraint.validate(ip, None))

    def test_invalidate_ipv4_format(self):
        invalidate_format = [
            '1.1.1.',
            '1.1.1.256',
            'invalidate format',
            '1.a.1.1'
        ]
        for ip in invalidate_format:
            self.assertFalse(self.constraint.validate(ip, None))

    def test_validate_ipv6_format(self):
        validate_format = [
            '2002:2002::20c:29ff:fe7d:811a',
            '::1',
            '2002::',
            '2002::1',
        ]
        for ip in validate_format:
            self.assertTrue(self.constraint.validate(ip, None))

    def test_invalidate_ipv6_format(self):
        invalidate_format = [
            '2002::2001::1',
            '2002::g',
            'invalidate format',
            '2001::0::',
            '20c:29ff:fe7d:811a'
        ]
        for ip in invalidate_format:
            self.assertFalse(self.constraint.validate(ip, None))


class TestMACConstraint(common.HeatTestCase):

    def setUp(self):
        super(TestMACConstraint, self).setUp()
        self.constraint = neutron.MACConstraint()

    def test_valid_mac_format(self):
        validate_format = [
            '01:23:45:67:89:ab',
            '01-23-45-67-89-ab',
            '0123.4567.89ab'
        ]
        for mac in validate_format:
            self.assertTrue(self.constraint.validate(mac, None))

    def test_invalid_mac_format(self):
        invalidate_format = [
            '8.8.8.8',
            '0a-1b-3c-4d-5e-6f-1f',
            '0a-1b-3c-4d-5e-xx'
        ]
        for mac in invalidate_format:
            self.assertFalse(self.constraint.validate(mac, None))


class TestCIDRConstraint(common.HeatTestCase):

    def setUp(self):
        super(TestCIDRConstraint, self).setUp()
        self.constraint = neutron.CIDRConstraint()

    def test_valid_cidr_format(self):
        validate_format = [
            '10.0.0.0/24',
            '6000::/64',
            '8.8.8.8'
        ]
        for cidr in validate_format:
            self.assertTrue(self.constraint.validate(cidr, None))

    def test_invalid_cidr_format(self):
        invalidate_format = [
            '::/129',
            'Invalid cidr',
            '300.0.0.0/24',
            '10.0.0.0/33',
            '8.8.8.0/ 24'
        ]
        for cidr in invalidate_format:
            self.assertFalse(self.constraint.validate(cidr, None))
