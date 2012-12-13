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


import json
import mox
import sys
import uuid
import time

import eventlet
import nose
import unittest
from nose.plugins.attrib import attr
from heat.tests import fakes

import heat.db as db_api
from heat.common import template_format
from heat.common import identifier
from heat.engine import parser
from heat.engine.resources import wait_condition as wc
from heat.common import context
from heat.openstack.common import cfg

test_template_waitcondition = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "Just a WaitCondition.",
  "Parameters" : {},
  "Resources" : {
    "WaitHandle" : {
      "Type" : "AWS::CloudFormation::WaitConditionHandle"
    },
    "WaitForTheHandle" : {
      "Type" : "AWS::CloudFormation::WaitCondition",
      "Properties" : {
        "Handle" : {"Ref" : "WaitHandle"},
        "Timeout" : "5"
      }
    }
  }
}
'''


@attr(tag=['unit', 'resource', 'WaitCondition'])
@attr(speed='slow')
class WaitConditionTest(unittest.TestCase):
    def setUp(self):
        self.m = mox.Mox()
        self.m.StubOutWithMock(wc.WaitCondition,
                               '_get_status_reason')
        self.m.StubOutWithMock(wc.WaitCondition,
                               '_create_timeout')
        self.m.StubOutWithMock(eventlet, 'sleep')

        cfg.CONF.set_default('heat_waitcondition_server_url',
                             'http://127.0.0.1:8000/v1/waitcondition')

        self.fc = fakes.FakeKeystoneClient()

    def tearDown(self):
        self.m.UnsetStubs()

    def create_stack(self, stack_name, temp, params):
        template = parser.Template(temp)
        parameters = parser.Parameters(stack_name, template, params)
        stack = parser.Stack(context.get_admin_context(), stack_name,
                             template, parameters)

        stack.store()
        return stack

    def test_post_success_to_handle(self):

        t = template_format.parse(test_template_waitcondition)
        stack = self.create_stack('test_stack', t, {})

        wc.WaitCondition._create_timeout().AndReturn(eventlet.Timeout(5))
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('WAITING', ''))
        eventlet.sleep(1).AndReturn(None)
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('WAITING', ''))
        eventlet.sleep(1).AndReturn(None)
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('SUCCESS', 'woot toot'))

        self.m.StubOutWithMock(wc.WaitConditionHandle, 'keystone')
        wc.WaitConditionHandle.keystone().MultipleTimes().AndReturn(self.fc)

        id = identifier.ResourceIdentifier('test_tenant', stack.name,
                                           stack.id, '', 'WaitHandle')
        self.m.StubOutWithMock(wc.WaitConditionHandle, 'identifier')
        wc.WaitConditionHandle.identifier().MultipleTimes().AndReturn(id)

        self.m.ReplayAll()

        stack.create()

        resource = stack.resources['WaitForTheHandle']
        self.assertEqual(resource.state,
                         'CREATE_COMPLETE')

        r = db_api.resource_get_by_name_and_stack(None, 'WaitHandle',
                                                  stack.id)
        self.assertEqual(r.name, 'WaitHandle')

        self.m.VerifyAll()

    def test_timeout(self):

        t = template_format.parse(test_template_waitcondition)
        stack = self.create_stack('test_stack', t, {})

        tmo = eventlet.Timeout(6)
        wc.WaitCondition._create_timeout().AndReturn(tmo)
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('WAITING', ''))
        eventlet.sleep(1).AndReturn(None)
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('WAITING', ''))
        eventlet.sleep(1).AndRaise(tmo)

        self.m.StubOutWithMock(wc.WaitConditionHandle, 'keystone')
        wc.WaitConditionHandle.keystone().MultipleTimes().AndReturn(self.fc)

        id = identifier.ResourceIdentifier('test_tenant', stack.name,
                                           stack.id, '', 'WaitHandle')
        self.m.StubOutWithMock(wc.WaitConditionHandle, 'identifier')
        wc.WaitConditionHandle.identifier().MultipleTimes().AndReturn(id)

        self.m.ReplayAll()

        stack.create()

        resource = stack.resources['WaitForTheHandle']

        self.assertEqual(resource.state,
                         'CREATE_FAILED')
        self.assertEqual(wc.WaitCondition.UPDATE_REPLACE,
                  resource.handle_update())

        stack.delete()

        self.m.VerifyAll()


@attr(tag=['unit', 'resource', 'WaitConditionHandle'])
@attr(speed='fast')
class WaitConditionHandleTest(unittest.TestCase):
    def setUp(self):
        self.m = mox.Mox()
        cfg.CONF.set_default('heat_waitcondition_server_url',
                             'http://127.0.0.1:8000/v1/waitcondition')

        self.fc = fakes.FakeKeystoneClient()

    def tearDown(self):
        self.m.UnsetStubs()

    def create_stack(self, stack_name='test_stack2', params={}):
        temp = template_format.parse(test_template_waitcondition)
        template = parser.Template(temp)
        parameters = parser.Parameters(stack_name, template, params)
        stack = parser.Stack(context.get_admin_context(), stack_name,
                             template, parameters)
        # Stub out the UUID for this test, so we can get an expected signature
        self.m.StubOutWithMock(uuid, 'uuid4')
        uuid.uuid4().AndReturn('STACKABCD1234')
        self.m.ReplayAll()
        stack.store()
        return stack

    def test_handle(self):
        stack = self.create_stack()

        # Stub waitcondition status so all goes CREATE_COMPLETE
        self.m.StubOutWithMock(wc.WaitCondition, '_get_status_reason')
        wc.WaitCondition._get_status_reason(
                         mox.IgnoreArg()).AndReturn(('SUCCESS', 'woot toot'))
        self.m.StubOutWithMock(wc.WaitCondition, '_create_timeout')
        wc.WaitCondition._create_timeout().AndReturn(eventlet.Timeout(5))

        # Stub keystone() with fake client
        self.m.StubOutWithMock(wc.WaitConditionHandle, 'keystone')
        wc.WaitConditionHandle.keystone().MultipleTimes().AndReturn(self.fc)

        id = identifier.ResourceIdentifier('test_tenant', stack.name,
                                           stack.id, '', 'WaitHandle')
        self.m.StubOutWithMock(wc.WaitConditionHandle, 'identifier')
        wc.WaitConditionHandle.identifier().MultipleTimes().AndReturn(id)

        # Stub time to a fixed value so we can get an expected signature
        t = time.gmtime(1354196977)
        self.m.StubOutWithMock(time, 'gmtime')
        time.gmtime().MultipleTimes().AndReturn(t)

        self.m.ReplayAll()
        stack.create()

        resource = stack.resources['WaitHandle']
        self.assertEqual(resource.state, 'CREATE_COMPLETE')

        expected_url = "".join(
                       ['http://127.0.0.1:8000/v1/waitcondition/',
                        'arn%3Aopenstack%3Aheat%3A%3Atest_tenant%3Astacks%2F',
                        'test_stack2%2FSTACKABCD1234%2Fresources%2F',
                        'WaitHandle?',
                        'Timestamp=2012-11-29T13%3A49%3A37Z&',
                        'SignatureMethod=HmacSHA256&',
                        'AWSAccessKeyId=4567&',
                        'SignatureVersion=2&',
                        'Signature=',
                        'ePyTwmC%2F1kSigeo%2Fha7kP8Avvb45G9Y7WOQWe4F%2BnXM%3D'
                       ])

        self.assertEqual(expected_url, resource.FnGetRefId())

        self.assertEqual(resource.UPDATE_REPLACE,
                  resource.handle_update())

        stack.delete()

        self.m.VerifyAll()

# allows testing of the test directly
if __name__ == '__main__':
    sys.argv.append(__file__)
    nose.main()
