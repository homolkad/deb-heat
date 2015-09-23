#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock
import six

from heat.common import exception
from heat.common import template_format
from heat.engine.clients.os import sahara
from heat.engine.resources.openstack.sahara import data_source
from heat.engine import scheduler
from heat.tests import common
from heat.tests import utils


data_source_template = """
heat_template_version: 2015-10-15
resources:
  data-source:
    type: OS::Sahara::DataSource
    properties:
      name: my-ds
      type: swift
      url: swift://container.sahara/text
      credentials:
          user: admin
          password: swordfish
"""


class SaharaDataSourceTest(common.HeatTestCase):
    def setUp(self):
        super(SaharaDataSourceTest, self).setUp()
        t = template_format.parse(data_source_template)
        self.stack = utils.parse_stack(t)
        resource_defns = self.stack.t.resource_definitions(self.stack)
        self.rsrc_defn = resource_defns['data-source']
        self.client = mock.Mock()
        self.patchobject(data_source.DataSource, 'client',
                         return_value=self.client)

    def _create_resource(self, name, snippet, stack):
        ds = data_source.DataSource(name, snippet, stack)
        value = mock.MagicMock(id='12345')
        self.client.data_sources.create.return_value = value
        scheduler.TaskRunner(ds.create)()
        return ds

    def test_create(self):
        ds = self._create_resource('data-source', self.rsrc_defn, self.stack)
        args = self.client.data_sources.create.call_args[1]
        expected_args = {
            'name': 'my-ds',
            'description': '',
            'data_source_type': 'swift',
            'url': 'swift://container.sahara/text',
            'credential_user': 'admin',
            'credential_pass': 'swordfish'
        }
        self.assertEqual(expected_args, args)
        self.assertEqual('12345', ds.resource_id)
        expected_state = (ds.CREATE, ds.COMPLETE)
        self.assertEqual(expected_state, ds.state)

    def test_resource_mapping(self):
        mapping = data_source.resource_mapping()
        self.assertEqual(1, len(mapping))
        self.assertEqual(data_source.DataSource,
                         mapping['OS::Sahara::DataSource'])

    def test_delete(self):
        ds = self._create_resource('data-source', self.rsrc_defn, self.stack)
        scheduler.TaskRunner(ds.delete)()
        self.assertEqual((ds.DELETE, ds.COMPLETE), ds.state)
        self.client.data_sources.delete.assert_called_once_with(
            ds.resource_id)

    def test_update(self):
        ds = self._create_resource('data-source', self.rsrc_defn,
                                   self.stack)
        self.rsrc_defn['Properties']['type'] = 'hdfs'
        self.rsrc_defn['Properties']['url'] = 'my/path'
        scheduler.TaskRunner(ds.update, self.rsrc_defn)()
        data = {
            'name': 'my-ds',
            'description': '',
            'type': 'hdfs',
            'url': 'my/path',
            'credentials': {
                'user': 'admin',
                'password': 'swordfish'
            }
        }
        self.client.data_sources.update.assert_called_once_with(
            '12345', data)
        self.assertEqual((ds.UPDATE, ds.COMPLETE), ds.state)

    def test_delete_not_found(self):
        ds = self._create_resource('data-source', self.rsrc_defn, self.stack)
        self.client.data_sources.delete.side_effect = (
            sahara.sahara_base.APIException(error_code=404))
        scheduler.TaskRunner(ds.delete)()
        self.assertEqual((ds.DELETE, ds.COMPLETE), ds.state)
        self.client.data_sources.delete.assert_called_once_with(
            ds.resource_id)

    def test_show_attribute(self):
        ds = self._create_resource('data-source', self.rsrc_defn, self.stack)
        value = mock.MagicMock()
        value.to_dict.return_value = {'ds': 'info'}
        self.client.data_sources.get.return_value = value
        self.assertEqual({'ds': 'info'}, ds.FnGetAtt('show'))

    def test_validate_password_without_user(self):
        self.rsrc_defn['Properties']['credentials'].pop('user')
        ds = data_source.DataSource('data-source', self.rsrc_defn, self.stack)
        ex = self.assertRaises(exception.StackValidationFailed, ds.validate)
        error_msg = ('Property error: resources.data-source.properties.'
                     'credentials: Property user not assigned')
        self.assertEqual(error_msg, six.text_type(ex))
