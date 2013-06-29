# vim: tabstop=4 shiftwidth=4 softtabstop=4

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


import re

import mox

from testtools import skipIf

from heat.common import template_format
from heat.openstack.common.importutils import try_import
from heat.engine.resources import s3
from heat.engine import resource
from heat.engine import scheduler
from heat.tests.common import HeatTestCase
from heat.tests.utils import setup_dummy_db
from heat.tests.utils import parse_stack

swiftclient = try_import('swiftclient.client')

swift_template = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "Template to test S3 Bucket resources",
  "Resources" : {
    "S3BucketWebsite" : {
      "Type" : "AWS::S3::Bucket",
      "DeletionPolicy" : "Delete",
      "Properties" : {
        "AccessControl" : "PublicRead",
        "WebsiteConfiguration" : {
          "IndexDocument" : "index.html",
          "ErrorDocument" : "error.html"
         }
      }
    },
    "S3Bucket" : {
      "Type" : "AWS::S3::Bucket",
      "Properties" : {
        "AccessControl" : "Private"
      }
    }
  }
}
'''


class s3Test(HeatTestCase):
    @skipIf(swiftclient is None, 'unable to import swiftclient')
    def setUp(self):
        super(s3Test, self).setUp()
        self.m.CreateMock(swiftclient.Connection)
        self.m.StubOutWithMock(swiftclient.Connection, 'put_container')
        self.m.StubOutWithMock(swiftclient.Connection, 'delete_container')
        self.m.StubOutWithMock(swiftclient.Connection, 'get_auth')

        self.container_pattern = 'test_stack-test_resource-[0-9a-z]+'
        setup_dummy_db()

    def create_resource(self, t, stack, resource_name):
        rsrc = s3.S3Bucket('test_resource',
                           t['Resources'][resource_name],
                           stack)
        scheduler.TaskRunner(rsrc.create)()
        self.assertEqual(s3.S3Bucket.CREATE_COMPLETE, rsrc.state)
        return rsrc

    def test_create_container_name(self):
        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        stack = parse_stack(t)
        rsrc = s3.S3Bucket('test_resource',
                           t['Resources']['S3Bucket'],
                           stack)
        self.assertTrue(re.match(self.container_pattern,
                                 rsrc._create_container_name()))

    def test_attributes(self):
        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}
        ).AndReturn(None)
        swiftclient.Connection.get_auth().MultipleTimes().AndReturn(
            ('http://localhost:8080/v_2', None))
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')

        ref_id = rsrc.FnGetRefId()
        self.assertTrue(re.match(self.container_pattern,
                                 ref_id))

        self.assertEqual('localhost', rsrc.FnGetAtt('DomainName'))
        url = 'http://localhost:8080/v_2/%s' % ref_id

        self.assertEqual(url, rsrc.FnGetAtt('WebsiteURL'))

        try:
            rsrc.FnGetAtt('Foo')
            raise Exception('Expected InvalidTemplateAttribute')
        except s3.exception.InvalidTemplateAttribute:
            pass

        self.assertRaises(resource.UpdateReplace,
                          rsrc.handle_update, {}, {}, {})

        rsrc.delete()
        self.m.VerifyAll()

    def test_public_read(self):
        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'PublicRead'
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')
        rsrc.delete()
        self.m.VerifyAll()

    def test_public_read_write(self):
        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': '.r:*',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'PublicReadWrite'
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')
        rsrc.delete()
        self.m.VerifyAll()

    def test_authenticated_read(self):
        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant'}).AndReturn(None)
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        properties = t['Resources']['S3Bucket']['Properties']
        properties['AccessControl'] = 'AuthenticatedRead'
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')
        rsrc.delete()
        self.m.VerifyAll()

    def test_website(self):

        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Meta-Web-Error': 'error.html',
             'X-Container-Meta-Web-Index': 'index.html',
             'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': '.r:*'}).AndReturn(None)
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3BucketWebsite')
        rsrc.delete()
        self.m.VerifyAll()

    def test_delete_exception(self):

        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndRaise(
                swiftclient.ClientException('Test delete failure'))

        self.m.ReplayAll()
        t = template_format.parse(swift_template)
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')
        rsrc.delete()

        self.m.VerifyAll()

    def test_delete_retain(self):

        # first run, with retain policy
        swiftclient.Connection.put_container(
            mox.Regex(self.container_pattern),
            {'X-Container-Write': 'test_tenant:test_username',
             'X-Container-Read': 'test_tenant:test_username'}).AndReturn(None)
        # This should not be called
        swiftclient.Connection.delete_container(
            mox.Regex(self.container_pattern)).AndReturn(None)

        self.m.ReplayAll()
        t = template_format.parse(swift_template)

        bucket = t['Resources']['S3Bucket']
        bucket['DeletionPolicy'] = 'Retain'
        stack = parse_stack(t)
        rsrc = self.create_resource(t, stack, 'S3Bucket')
        # if delete_container is called, mox verify will succeed
        rsrc.delete()
        self.assertEqual(rsrc.DELETE_COMPLETE, rsrc.state)

        try:
            self.m.VerifyAll()
        except mox.ExpectedMethodCallsError:
            return

        raise Exception('delete_container was called despite Retain policy')
