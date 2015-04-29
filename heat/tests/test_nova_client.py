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
"""Tests for :module:'heat.engine.resources.nova_utls'."""

import collections
import uuid

import mock
from novaclient import exceptions as nova_exceptions
from oslo_config import cfg
import six

from heat.common import exception
from heat.engine.clients.os import nova
from heat.tests import common
from heat.tests.nova import fakes as fakes_nova
from heat.tests import utils


class NovaClientPluginTestCase(common.HeatTestCase):
    def setUp(self):
        super(NovaClientPluginTestCase, self).setUp()
        self.nova_client = mock.MagicMock()
        con = utils.dummy_context()
        c = con.clients
        self.nova_plugin = c.client_plugin('nova')
        self.nova_plugin._client = self.nova_client


class NovaClientPluginTests(NovaClientPluginTestCase):
    """
    Basic tests for the helper methods in
    :module:'heat.engine.nova_utils'.
    """

    def test_get_ip(self):
        my_image = mock.MagicMock()
        my_image.addresses = {
            'public': [{'version': 4,
                        'addr': '4.5.6.7'},
                       {'version': 6,
                        'addr': '2401:1801:7800:0101:c058:dd33:ff18:04e6'}],
            'private': [{'version': 4,
                         'addr': '10.13.12.13'}]}

        expected = '4.5.6.7'
        observed = self.nova_plugin.get_ip(my_image, 'public', 4)
        self.assertEqual(expected, observed)

        expected = '10.13.12.13'
        observed = self.nova_plugin.get_ip(my_image, 'private', 4)
        self.assertEqual(expected, observed)

        expected = '2401:1801:7800:0101:c058:dd33:ff18:04e6'
        observed = self.nova_plugin.get_ip(my_image, 'public', 6)
        self.assertEqual(expected, observed)

    def test_get_flavor_id(self):
        """Tests the get_flavor_id function."""
        flav_id = str(uuid.uuid4())
        flav_name = 'X-Large'
        my_flavor = mock.MagicMock()
        my_flavor.name = flav_name
        my_flavor.id = flav_id
        self.nova_client.flavors.list.return_value = [my_flavor]
        self.assertEqual(flav_id, self.nova_plugin.get_flavor_id(flav_name))
        self.assertEqual(flav_id, self.nova_plugin.get_flavor_id(flav_id))
        self.assertRaises(exception.FlavorMissing,
                          self.nova_plugin.get_flavor_id, 'noflavor')
        self.assertEqual(3, self.nova_client.flavors.list.call_count)
        self.assertEqual([(), (), ()],
                         self.nova_client.flavors.list.call_args_list)

    def test_get_keypair(self):
        """Tests the get_keypair function."""
        my_pub_key = 'a cool public key string'
        my_key_name = 'mykey'
        my_key = mock.MagicMock()
        my_key.public_key = my_pub_key
        my_key.name = my_key_name
        self.nova_client.keypairs.get.side_effect = [
            my_key, nova_exceptions.NotFound(404)]
        self.assertEqual(my_key, self.nova_plugin.get_keypair(my_key_name))
        self.assertRaises(exception.UserKeyPairMissing,
                          self.nova_plugin.get_keypair, 'notakey')
        calls = [mock.call(my_key_name),
                 mock.call('notakey')]
        self.nova_client.keypairs.get.assert_has_calls(calls)

    def test_get_server(self):
        """Tests the get_server function."""
        my_server = mock.MagicMock()
        self.nova_client.servers.get.side_effect = [
            my_server, nova_exceptions.NotFound(404)]
        self.assertEqual(my_server, self.nova_plugin.get_server('my_server'))
        self.assertRaises(exception.ServerNotFound,
                          self.nova_plugin.get_server, 'idontexist')
        calls = [mock.call('my_server'),
                 mock.call('idontexist')]
        self.nova_client.servers.get.assert_has_calls(calls)

    def test_get_network_id_by_label(self):
        """Tests the get_net_id_by_label function."""
        net = mock.MagicMock()
        net.id = str(uuid.uuid4())
        self.nova_client.networks.find.side_effect = [
            net, nova_exceptions.NotFound(404),
            nova_exceptions.NoUniqueMatch()]
        self.assertEqual(net.id,
                         self.nova_plugin.get_net_id_by_label('net_label'))

        exc = self.assertRaises(
            exception.NovaNetworkNotFound,
            self.nova_plugin.get_net_id_by_label, 'idontexist')
        expected = 'The Nova network (idontexist) could not be found'
        self.assertIn(expected, six.text_type(exc))
        exc = self.assertRaises(
            exception.PhysicalResourceNameAmbiguity,
            self.nova_plugin.get_net_id_by_label, 'notUnique')
        expected = ('Multiple physical resources were found '
                    'with name (notUnique)')
        self.assertIn(expected, six.text_type(exc))
        calls = [mock.call(label='net_label'),
                 mock.call(label='idontexist'),
                 mock.call(label='notUnique')]
        self.nova_client.networks.find.assert_has_calls(calls)

    def test_get_nova_network_id(self):
        """Tests the get_nova_network_id function."""
        net = mock.MagicMock()
        net.id = str(uuid.uuid4())
        not_existent_net_id = str(uuid.uuid4())
        self.nova_client.networks.get.side_effect = [
            net, nova_exceptions.NotFound(404)]
        self.nova_client.networks.find.side_effect = [
            nova_exceptions.NotFound(404)]

        self.assertEqual(net.id,
                         self.nova_plugin.get_nova_network_id(net.id))
        exc = self.assertRaises(
            exception.NovaNetworkNotFound,
            self.nova_plugin.get_nova_network_id, not_existent_net_id)
        expected = ('The Nova network (%s) could not be found' %
                    not_existent_net_id)
        self.assertIn(expected, six.text_type(exc))

        calls = [mock.call(net.id),
                 mock.call(not_existent_net_id)]
        self.nova_client.networks.get.assert_has_calls(calls)
        self.nova_client.networks.find.assert_called_once_with(
            label=not_existent_net_id)

    def test_get_status(self):
        server = self.m.CreateMockAnything()
        server.status = 'ACTIVE'

        observed = self.nova_plugin.get_status(server)
        self.assertEqual('ACTIVE', observed)

        server.status = 'ACTIVE(STATUS)'
        observed = self.nova_plugin.get_status(server)
        self.assertEqual('ACTIVE', observed)


class NovaUtilsRefreshServerTests(NovaClientPluginTestCase):
    msg = ("ClientException: The server has either erred or is "
           "incapable of performing the requested operation.")

    scenarios = [
        ('successful_refresh', dict(
            value=None,
            e_raise=False)),
        ('overlimit_error', dict(
            value=nova_exceptions.OverLimit(413, "limit reached"),
            e_raise=False)),
        ('500_error', dict(
            value=nova_exceptions.ClientException(500, msg),
            e_raise=False)),
        ('503_error', dict(
            value=nova_exceptions.ClientException(503, msg),
            e_raise=False)),
        ('unhandled_exception', dict(
            value=nova_exceptions.ClientException(501, msg),
            e_raise=True)),
    ]

    def test_refresh(self):
        server = mock.MagicMock()
        server.get.side_effect = [self.value]
        if self.e_raise:
            self.assertRaises(nova_exceptions.ClientException,
                              self.nova_plugin.refresh_server, server)
        else:
            self.assertIsNone(self.nova_plugin.refresh_server(server))
        server.get.assert_called_once_with()


class NovaUtilsUserdataTests(NovaClientPluginTestCase):

    def test_build_userdata(self):
        """Tests the build_userdata function."""
        cfg.CONF.set_override('heat_metadata_server_url',
                              'http://server.test:123')
        cfg.CONF.set_override('heat_watch_server_url',
                              'http://server.test:345')
        cfg.CONF.set_override('instance_connection_is_secure',
                              False)
        cfg.CONF.set_override(
            'instance_connection_https_validate_certificates', False)
        data = self.nova_plugin.build_userdata({})
        self.assertIn("Content-Type: text/cloud-config;", data)
        self.assertIn("Content-Type: text/cloud-boothook;", data)
        self.assertIn("Content-Type: text/part-handler;", data)
        self.assertIn("Content-Type: text/x-cfninitdata;", data)
        self.assertIn("Content-Type: text/x-shellscript;", data)
        self.assertIn("http://server.test:345", data)
        self.assertIn("http://server.test:123", data)
        self.assertIn("[Boto]", data)

    def test_build_userdata_without_instance_user(self):
        """Don't add a custom instance user when not requested."""
        cfg.CONF.set_override('instance_user',
                              'config_instance_user')
        cfg.CONF.set_override('heat_metadata_server_url',
                              'http://server.test:123')
        cfg.CONF.set_override('heat_watch_server_url',
                              'http://server.test:345')
        data = self.nova_plugin.build_userdata({}, instance_user=None)
        self.assertNotIn('user: ', data)
        self.assertNotIn('useradd', data)
        self.assertNotIn('config_instance_user', data)

    def test_build_userdata_with_instance_user(self):
        """Add the custom instance user when requested."""
        self.m.StubOutWithMock(nova.cfg, 'CONF')
        cnf = nova.cfg.CONF
        cnf.instance_user = 'config_instance_user'
        cnf.heat_metadata_server_url = 'http://server.test:123'
        cnf.heat_watch_server_url = 'http://server.test:345'
        data = self.nova_plugin.build_userdata(
            None, instance_user="custominstanceuser")
        self.assertNotIn('config_instance_user', data)
        self.assertIn("custominstanceuser", data)


class NovaUtilsMetadataTests(NovaClientPluginTestCase):

    def test_serialize_string(self):
        original = {'test_key': 'simple string value'}
        self.assertEqual(original, self.nova_plugin.meta_serialize(original))

    def test_serialize_int(self):
        original = {'test_key': 123}
        expected = {'test_key': '123'}
        self.assertEqual(expected, self.nova_plugin.meta_serialize(original))

    def test_serialize_list(self):
        original = {'test_key': [1, 2, 3]}
        expected = {'test_key': '[1, 2, 3]'}
        self.assertEqual(expected, self.nova_plugin.meta_serialize(original))

    def test_serialize_dict(self):
        original = {'test_key': {'a': 'b', 'c': 'd'}}
        expected = {'test_key': '{"a": "b", "c": "d"}'}
        self.assertEqual(expected, self.nova_plugin.meta_serialize(original))

    def test_serialize_none(self):
        original = {'test_key': None}
        expected = {'test_key': 'null'}
        self.assertEqual(expected, self.nova_plugin.meta_serialize(original))

    def test_serialize_no_value(self):
        """This test is to prove that the user can only pass in a dict to nova
        metadata.
        """
        excp = self.assertRaises(exception.StackValidationFailed,
                                 self.nova_plugin.meta_serialize, "foo")
        self.assertIn('metadata needs to be a Map', six.text_type(excp))

    def test_serialize_combined(self):
        original = {
            'test_key_1': 123,
            'test_key_2': 'a string',
            'test_key_3': {'a': 'b'},
            'test_key_4': None,
        }
        expected = {
            'test_key_1': '123',
            'test_key_2': 'a string',
            'test_key_3': '{"a": "b"}',
            'test_key_4': 'null',
        }

        self.assertEqual(expected, self.nova_plugin.meta_serialize(original))


class ServerConstraintTest(common.HeatTestCase):

    def setUp(self):
        super(ServerConstraintTest, self).setUp()
        self.ctx = utils.dummy_context()
        self.mock_get_server = mock.Mock()
        self.ctx.clients.client_plugin(
            'nova').get_server = self.mock_get_server
        self.constraint = nova.ServerConstraint()

    def test_validation(self):
        self.mock_get_server.return_value = mock.MagicMock()
        self.assertTrue(self.constraint.validate("foo", self.ctx))

    def test_validation_error(self):
        self.mock_get_server.side_effect = exception.ServerNotFound(
            server='bar')
        self.assertFalse(self.constraint.validate("bar", self.ctx))


class FlavorConstraintTest(common.HeatTestCase):

    def test_validate(self):
        client = fakes_nova.FakeClient()
        self.stub_keystoneclient()
        self.patchobject(nova.NovaClientPlugin, '_create', return_value=client)
        client.flavors = mock.MagicMock()

        flavor = collections.namedtuple("Flavor", ["id", "name"])
        flavor.id = "1234"
        flavor.name = "foo"
        client.flavors.list.return_value = [flavor]

        constraint = nova.FlavorConstraint()
        ctx = utils.dummy_context()
        self.assertFalse(constraint.validate("bar", ctx))
        self.assertTrue(constraint.validate("foo", ctx))
        self.assertTrue(constraint.validate("1234", ctx))
        nova.NovaClientPlugin._create.assert_called_once_with()
        self.assertEqual(3, client.flavors.list.call_count)
        self.assertEqual([(), (), ()],
                         client.flavors.list.call_args_list)


class KeypairConstraintTest(common.HeatTestCase):

    def test_validation(self):
        client = fakes_nova.FakeClient()
        self.patchobject(nova.NovaClientPlugin, '_create', return_value=client)
        client.keypairs = mock.MagicMock()

        key = collections.namedtuple("Key", ["name"])
        key.name = "foo"
        client.keypairs.get.side_effect = [
            fakes_nova.fake_exception(), key]

        constraint = nova.KeypairConstraint()
        ctx = utils.dummy_context()
        self.assertFalse(constraint.validate("bar", ctx))
        self.assertTrue(constraint.validate("foo", ctx))
        self.assertTrue(constraint.validate("", ctx))
        nova.NovaClientPlugin._create.assert_called_once_with()
        calls = [mock.call('bar'),
                 mock.call(key.name)]
        client.keypairs.get.assert_has_calls(calls)


class ConsoleUrlsTest(common.HeatTestCase):

    scenarios = [
        ('novnc', dict(console_type='novnc', srv_method='vnc')),
        ('xvpvnc', dict(console_type='xvpvnc', srv_method='vnc')),
        ('spice', dict(console_type='spice-html5', srv_method='spice')),
        ('rdp', dict(console_type='rdp-html5', srv_method='rdp')),
        ('serial', dict(console_type='serial', srv_method='serial')),
    ]

    def setUp(self):
        super(ConsoleUrlsTest, self).setUp()
        self.nova_client = mock.Mock()
        con = utils.dummy_context()
        c = con.clients
        self.nova_plugin = c.client_plugin('nova')
        self.nova_plugin._client = self.nova_client
        self.server = mock.Mock()
        self.console_method = getattr(self.server,
                                      'get_%s_console' % self.srv_method)

    def test_get_console_url(self):
        console = {
            'console': {
                'type': self.console_type,
                'url': '%s_console_url' % self.console_type
            }
        }
        self.console_method.return_value = console

        console_url = self.nova_plugin.get_console_urls(self.server)[
            self.console_type]

        self.assertEqual(console['console']['url'], console_url)
        self.console_method.assert_called_once_with(self.console_type)

    def test_get_console_url_tolerate_unavailable(self):
        msg = 'Unavailable console type %s.' % self.console_type
        self.console_method.side_effect = nova_exceptions.BadRequest(
            400, message=msg)

        console_url = self.nova_plugin.get_console_urls(self.server)[
            self.console_type]

        self.console_method.assert_called_once_with(self.console_type)
        self.assertEqual(msg, console_url)

    def test_get_console_urls_reraises_other_400(self):
        exc = nova_exceptions.BadRequest
        self.console_method.side_effect = exc(400, message="spam")

        urls = self.nova_plugin.get_console_urls(self.server)
        e = self.assertRaises(exc, urls.__getitem__, self.console_type)
        self.assertIn('spam', e.message)
        self.console_method.assert_called_once_with(self.console_type)

    def test_get_console_urls_reraises_other(self):
        exc = Exception
        self.console_method.side_effect = exc("spam")

        urls = self.nova_plugin.get_console_urls(self.server)
        e = self.assertRaises(exc, urls.__getitem__, self.console_type)
        self.assertIn('spam', e.args)
        self.console_method.assert_called_once_with(self.console_type)
