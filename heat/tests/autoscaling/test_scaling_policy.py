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

import datetime

import mock
from oslo.config import cfg
from oslo.utils import timeutils

from heat.common import template_format
from heat.engine import scheduler
from heat.tests.autoscaling import inline_templates
from heat.tests import common
from heat.tests import utils


as_template = inline_templates.as_template
as_params = inline_templates.as_params


class TestAutoScalingPolicy(common.HeatTestCase):
    def setUp(self):
        super(TestAutoScalingPolicy, self).setUp()
        cfg.CONF.set_default('heat_waitcondition_server_url',
                             'http://server.test:8000/v1/waitcondition')
        self.stub_keystoneclient()

    def create_scaling_policy(self, t, stack, resource_name):
        rsrc = stack[resource_name]
        self.assertIsNone(rsrc.validate())
        scheduler.TaskRunner(rsrc.create)()
        self.assertEqual((rsrc.CREATE, rsrc.COMPLETE), rsrc.state)
        return rsrc

    def test_scaling_policy_not_alarm_state(self):
        """If the details don't have 'alarm' then don't progress."""
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        test = {'current': 'not_an_alarm'}
        with mock.patch.object(pol, '_cooldown_inprogress',
                               side_effect=AssertionError()) as dont_call:
            pol.handle_signal(details=test)
            self.assertEqual([], dont_call.call_args_list)

    def test_scaling_policy_cooldown_toosoon(self):
        """If _cooldown_inprogress() returns True don't progress."""
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')
        test = {'current': 'alarm'}

        with mock.patch.object(pol.stack, 'resource_by_refid',
                               side_effect=AssertionError) as dont_call:
            with mock.patch.object(pol, '_cooldown_inprogress',
                                   return_value=True) as mock_cip:
                pol.handle_signal(details=test)
                mock_cip.assert_called_once_with()
            self.assertEqual([], dont_call.call_args_list)

    def test_scaling_policy_cooldown_ok(self):
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')
        test = {'current': 'alarm'}

        group = self.patchobject(pol.stack, 'resource_by_refid').return_value
        group.name = 'fluffy'
        with mock.patch.object(pol, '_cooldown_inprogress',
                               return_value=False) as mock_cip:
            pol.handle_signal(details=test)
            mock_cip.assert_called_once_with()
        group.adjust.assert_called_once_with(1, 'ChangeInCapacity')


class TestCooldownMixin(common.HeatTestCase):
    def setUp(self):
        super(TestCooldownMixin, self).setUp()
        cfg.CONF.set_default('heat_waitcondition_server_url',
                             'http://server.test:8000/v1/waitcondition')
        self.stub_keystoneclient()

    def create_scaling_policy(self, t, stack, resource_name):
        rsrc = stack[resource_name]
        self.assertIsNone(rsrc.validate())
        scheduler.TaskRunner(rsrc.create)()
        self.assertEqual((rsrc.CREATE, rsrc.COMPLETE), rsrc.state)
        return rsrc

    def test_is_in_progress(self):
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        now = timeutils.utcnow()
        previous_meta = {timeutils.strtime(now): 'ChangeInCapacity : 1'}
        self.patchobject(pol, 'metadata_get', return_value=previous_meta)
        self.assertTrue(pol._cooldown_inprogress())

    def test_not_in_progress(self):
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        awhile_ago = timeutils.utcnow() - datetime.timedelta(seconds=100)
        previous_meta = {timeutils.strtime(awhile_ago): 'ChangeInCapacity : 1'}
        self.patchobject(pol, 'metadata_get', return_value=previous_meta)
        self.assertFalse(pol._cooldown_inprogress())

    def test_scaling_policy_cooldown_zero(self):
        t = template_format.parse(as_template)

        # Create the scaling policy (with Cooldown=0) and scale up one
        properties = t['Resources']['WebServerScaleUpPolicy']['Properties']
        properties['Cooldown'] = '0'

        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        now = timeutils.utcnow()
        previous_meta = {timeutils.strtime(now): 'ChangeInCapacity : 1'}
        self.patchobject(pol, 'metadata_get', return_value=previous_meta)
        self.assertFalse(pol._cooldown_inprogress())

    def test_scaling_policy_cooldown_none(self):
        t = template_format.parse(as_template)

        # Create the scaling policy no Cooldown property, should behave the
        # same as when Cooldown==0
        properties = t['Resources']['WebServerScaleUpPolicy']['Properties']
        del properties['Cooldown']

        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        now = timeutils.utcnow()
        previous_meta = {timeutils.strtime(now): 'ChangeInCapacity : 1'}
        self.patchobject(pol, 'metadata_get', return_value=previous_meta)
        self.assertFalse(pol._cooldown_inprogress())

    def test_metadata_is_written(self):
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        pol = self.create_scaling_policy(t, stack, 'WebServerScaleUpPolicy')

        nowish = timeutils.strtime()
        reason = 'cool as'
        meta_set = self.patchobject(pol, 'metadata_set')
        self.patchobject(timeutils, 'strtime', return_value=nowish)
        pol._cooldown_timestamp(reason)
        meta_set.assert_called_once_with({nowish: reason})


class ScalingPolicyAttrTest(common.HeatTestCase):
    def setUp(self):
        super(ScalingPolicyAttrTest, self).setUp()
        self.stub_keystoneclient()
        t = template_format.parse(as_template)
        stack = utils.parse_stack(t, params=as_params)
        self.policy = stack['WebServerScaleUpPolicy']
        self.assertIsNone(self.policy.validate())
        scheduler.TaskRunner(self.policy.create)()
        self.assertEqual((self.policy.CREATE, self.policy.COMPLETE),
                         self.policy.state)

    def test_alarm_attribute(self):
        self.assertIn("WebServerScaleUpPolicy",
                      self.policy.FnGetAtt('AlarmUrl'))
