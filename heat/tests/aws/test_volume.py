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

import copy

from cinderclient import exceptions as cinder_exp
import mock
import mox
from oslo.config import cfg
import six

from heat.common import exception
from heat.common import template_format
from heat.engine.clients.os import cinder
from heat.engine.clients.os import nova
from heat.engine.resources.aws import volume as aws_vol
from heat.engine.resources import instance
from heat.engine import rsrc_defn
from heat.engine import scheduler
from heat.tests import test_volume_utils as vt_base
from heat.tests import utils
from heat.tests.v1_1 import fakes as fakes_v1_1


volume_template = '''
{
  "AWSTemplateFormatVersion" : "2010-09-09",
  "Description" : "Volume Test",
  "Parameters" : {},
  "Resources" : {
    "WikiDatabase": {
      "Type": "AWS::EC2::Instance",
      "Properties": {
        "ImageId" : "foo",
        "InstanceType"   : "m1.large",
        "KeyName"        : "test",
        "UserData"       : "some data"
      }
    },
    "DataVolume" : {
      "Type" : "AWS::EC2::Volume",
      "Properties" : {
        "Size" : "1",
        "AvailabilityZone" : {"Fn::GetAtt": ["WikiDatabase",
                                             "AvailabilityZone"]},
        "Tags" : [{ "Key" : "Usage", "Value" : "Wiki Data Volume" }]
      }
    },
    "MountPoint" : {
      "Type" : "AWS::EC2::VolumeAttachment",
      "Properties" : {
        "InstanceId" : { "Ref" : "WikiDatabase" },
        "VolumeId"  : { "Ref" : "DataVolume" },
        "Device" : "/dev/vdc"
      }
    }
  }
}
'''


class VolumeTest(vt_base.BaseVolumeTest):

    def setUp(self):
        super(VolumeTest, self).setUp()
        self.t = template_format.parse(volume_template)
        self.use_cinder = False

    def _mock_create_volume(self, fv, stack_name):
        cinder.CinderClientPlugin._create().MultipleTimes().AndReturn(
            self.cinder_fc)
        vol_name = utils.PhysName(stack_name, 'DataVolume')
        self.cinder_fc.volumes.create(
            size=1, availability_zone='nova',
            description=vol_name,
            name=vol_name,
            metadata={u'Usage': u'Wiki Data Volume'}).AndReturn(fv)

    def test_volume(self):
        fv = vt_base.FakeVolume('creating', 'available')
        stack_name = 'test_volume_create_stack'

        # create script
        self._mock_create_volume(fv, stack_name)

        # delete script
        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)

        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)
        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)

        fv.status = 'in-use'
        ex = self.assertRaises(exception.ResourceFailure,
                               scheduler.TaskRunner(rsrc.destroy))
        self.assertIn("Volume in use", six.text_type(ex))

        self._mock_delete_volume(fv)
        fv.status = 'available'
        scheduler.TaskRunner(rsrc.destroy)()

        self.m.VerifyAll()

    def test_volume_default_az(self):
        fv = vt_base.FakeVolume('creating', 'available')
        stack_name = 'test_volume_defaultaz_stack'

        # create script
        nova.NovaClientPlugin._create().AndReturn(self.fc)
        self.m.StubOutWithMock(instance.Instance, 'handle_create')
        self.m.StubOutWithMock(instance.Instance, 'check_create_complete')
        self.m.StubOutWithMock(instance.Instance, '_resolve_attribute')
        self.m.StubOutWithMock(aws_vol.VolumeAttachment,
                               'handle_create')
        self.m.StubOutWithMock(aws_vol.VolumeAttachment,
                               'check_create_complete')

        instance.Instance.handle_create().AndReturn(None)
        instance.Instance.check_create_complete(None).AndReturn(True)
        instance.Instance._resolve_attribute(
            'AvailabilityZone').MultipleTimes().AndReturn(None)
        cinder.CinderClientPlugin._create().AndReturn(
            self.cinder_fc)
        self.stub_ImageConstraint_validate()
        self.stub_ServerConstraint_validate()
        self.stub_VolumeConstraint_validate()
        vol_name = utils.PhysName(stack_name, 'DataVolume')
        self.cinder_fc.volumes.create(
            size=1, availability_zone=None,
            description=vol_name,
            name=vol_name,
            metadata={u'Usage': u'Wiki Data Volume'}).AndReturn(fv)
        aws_vol.VolumeAttachment.handle_create().AndReturn(None)
        aws_vol.VolumeAttachment.check_create_complete(
            None).AndReturn(True)

        # delete script
        self.m.StubOutWithMock(instance.Instance, 'handle_delete')
        self.m.StubOutWithMock(aws_vol.VolumeAttachment, 'handle_delete')
        self.m.StubOutWithMock(aws_vol.VolumeAttachment,
                               'check_delete_complete')
        instance.Instance.handle_delete().AndReturn(None)
        self.cinder_fc.volumes.get('vol-123').AndRaise(
            cinder_exp.NotFound('Not found'))
        cookie = object()
        aws_vol.VolumeAttachment.handle_delete().AndReturn(cookie)
        aws_vol.VolumeAttachment.check_delete_complete(cookie).AndReturn(True)

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = stack['DataVolume']
        self.assertIsNone(rsrc.validate())
        scheduler.TaskRunner(stack.create)()
        self.assertEqual((rsrc.CREATE, rsrc.COMPLETE), rsrc.state)

        scheduler.TaskRunner(stack.delete)()

        self.m.VerifyAll()

    def test_volume_create_error(self):
        fv = vt_base.FakeVolume('creating', 'error')
        stack_name = 'test_volume_create_error_stack'
        cfg.CONF.set_override('action_retry_limit', 0)

        self._mock_create_volume(fv, stack_name)

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)
        ex = self.assertRaises(exception.ResourceFailure,
                               self.create_volume, self.t, stack, 'DataVolume')
        self.assertIn('Went to status error due to "Unknown"',
                      six.text_type(ex))

        self.m.VerifyAll()

    def test_volume_bad_tags(self):
        stack_name = 'test_volume_bad_tags_stack'
        self.t['Resources']['DataVolume']['Properties'][
            'Tags'] = [{'Foo': 'bar'}]
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        ex = self.assertRaises(exception.StackValidationFailed,
                               self.create_volume, self.t, stack, 'DataVolume')
        self.assertIn('Tags Property error', six.text_type(ex))

        self.m.VerifyAll()

    def test_volume_attachment_error(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('attaching', 'error')
        stack_name = 'test_volume_attach_error_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        ex = self.assertRaises(exception.ResourceFailure,
                               self.create_attachment,
                               self.t, stack, 'MountPoint')
        self.assertIn("Volume attachment failed - Unknown status error",
                      six.text_type(ex))

        self.m.VerifyAll()

    def test_volume_attachment(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('attaching', 'in-use')
        stack_name = 'test_volume_attach_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()
        # delete script
        fva = vt_base.FakeVolume('in-use', 'available')
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.cinder_fc.volumes.get(fva.id).AndReturn(fva)
        self.fc.volumes.delete_server_volume(
            'WikiDatabase', 'vol-123').MultipleTimes().AndReturn(None)
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.fc.volumes.get_server_volume(
            u'WikiDatabase', 'vol-123').AndRaise(fakes_v1_1.fake_exception())

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')

        scheduler.TaskRunner(rsrc.delete)()

        self.m.VerifyAll()

    def test_volume_detachment_err(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('in-use', 'available')
        stack_name = 'test_volume_detach_err_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()

        # delete script
        fva = vt_base.FakeVolume('in-use', 'available')

        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.cinder_fc.volumes.get(fva.id).AndReturn(fva)

        self.fc.volumes.delete_server_volume(
            'WikiDatabase', 'vol-123').AndRaise(fakes_v1_1.fake_exception(400))

        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.fc.volumes.get_server_volume(
            u'WikiDatabase', 'vol-123').AndRaise(fakes_v1_1.fake_exception())
        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')

        scheduler.TaskRunner(rsrc.delete)()

        self.m.VerifyAll()

    def test_volume_detach_non_exist(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('in-use', 'available')
        stack_name = 'test_volume_detach_nonexist_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()
        # delete script
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.cinder_fc.volumes.get(fva.id).AndRaise(
            cinder_exp.NotFound('Not found'))

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')

        scheduler.TaskRunner(rsrc.delete)()

        self.m.VerifyAll()

    def test_volume_detach_with_latency(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('attaching', 'in-use')
        stack_name = 'test_volume_detach_latency__stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()

        # delete script
        volume_detach_cycle = 'in-use', 'detaching', 'available'
        fva = vt_base.FakeLatencyVolume(life_cycle=volume_detach_cycle)
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.cinder_fc.volumes.get(fva.id).AndReturn(fva)
        self.fc.volumes.delete_server_volume(
            'WikiDatabase', 'vol-123').MultipleTimes().AndReturn(None)
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.fc.volumes.get_server_volume(
            u'WikiDatabase', 'vol-123').AndRaise(fakes_v1_1.fake_exception())

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')

        scheduler.TaskRunner(rsrc.delete)()

        self.m.VerifyAll()

    def test_volume_detach_with_error(self):
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('attaching', 'in-use')
        stack_name = 'test_volume_detach_werr_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()

        # delete script
        fva = vt_base.FakeVolume('in-use', 'error')
        self.fc.volumes.get_server_volume(u'WikiDatabase',
                                          'vol-123').AndReturn(fva)
        self.cinder_fc.volumes.get(fva.id).AndReturn(fva)
        self.fc.volumes.delete_server_volume('WikiDatabase',
                                             'vol-123').AndReturn(None)
        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')
        detach_task = scheduler.TaskRunner(rsrc.delete)

        ex = self.assertRaises(exception.ResourceFailure, detach_task)
        self.assertIn('Volume detachment failed - Unknown status error',
                      six.text_type(ex))

        self.m.VerifyAll()

    def test_volume_delete(self):
        stack_name = 'test_volume_delete_stack'
        fv = vt_base.FakeVolume('creating', 'available')

        self._mock_create_volume(fv, stack_name)
        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['DeletionPolicy'] = 'Delete'
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = self.create_volume(self.t, stack, 'DataVolume')

        self.m.StubOutWithMock(rsrc, "handle_delete")
        rsrc.handle_delete().AndReturn(None)
        self.m.StubOutWithMock(rsrc, "check_delete_complete")
        rsrc.check_delete_complete(mox.IgnoreArg()).AndReturn(True)
        self.m.ReplayAll()
        scheduler.TaskRunner(rsrc.destroy)()

        self.m.VerifyAll()

    def test_volume_deleting_delete(self):
        fv = vt_base.FakeVolume('creating', 'available')
        stack_name = 'test_volume_deleting_stack'

        self._mock_create_volume(fv, stack_name)

        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)
        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)

        # make sure that delete was not called
        self.m.StubOutWithMock(fv, 'delete')

        self.m.StubOutWithMock(fv, 'get')
        fv.get().AndReturn(None)
        fv.get().AndRaise(cinder_exp.NotFound('Not found'))
        self.m.ReplayAll()

        fv.status = 'deleting'
        scheduler.TaskRunner(rsrc.destroy)()

        self.m.VerifyAll()

    def test_volume_update_not_supported(self):
        stack_name = 'test_volume_updnotsup_stack'
        fv = vt_base.FakeVolume('creating', 'available')

        self._mock_create_volume(fv, stack_name)
        self.m.ReplayAll()

        t = template_format.parse(volume_template)
        stack = utils.parse_stack(t, stack_name=stack_name)

        rsrc = self.create_volume(t, stack, 'DataVolume')

        props = copy.deepcopy(rsrc.properties.data)
        props['Size'] = 2
        props['Tags'] = None
        props['AvailabilityZone'] = 'other'
        after = rsrc_defn.ResourceDefinition(rsrc.name, rsrc.type(), props)

        updater = scheduler.TaskRunner(rsrc.update, after)
        ex = self.assertRaises(exception.ResourceFailure, updater)
        self.assertIn("NotSupported: Update to properties "
                      "AvailabilityZone, Size, Tags of DataVolume "
                      "(AWS::EC2::Volume) is not supported",
                      six.text_type(ex))
        self.assertEqual((rsrc.UPDATE, rsrc.FAILED), rsrc.state)

    def test_volume_check(self):
        stack = utils.parse_stack(self.t, stack_name='volume_check')
        res = stack['DataVolume']
        res.cinder = mock.Mock()

        fake_volume = vt_base.FakeVolume('available', 'available')
        res.cinder().volumes.get.return_value = fake_volume
        scheduler.TaskRunner(res.check)()
        self.assertEqual((res.CHECK, res.COMPLETE), res.state)

        fake_volume = vt_base.FakeVolume('in-use', 'in-use')
        res.cinder().volumes.get.return_value = fake_volume
        scheduler.TaskRunner(res.check)()
        self.assertEqual((res.CHECK, res.COMPLETE), res.state)

    def test_volume_check_not_available(self):
        stack = utils.parse_stack(self.t, stack_name='volume_check_na')
        res = stack['DataVolume']
        res.cinder = mock.Mock()

        fake_volume = vt_base.FakeVolume('foobar', 'foobar')
        res.cinder().volumes.get.return_value = fake_volume

        self.assertRaises(exception.ResourceFailure,
                          scheduler.TaskRunner(res.check))
        self.assertEqual((res.CHECK, res.FAILED), res.state)
        self.assertIn('foobar', res.status_reason)

    def test_volume_check_fail(self):
        stack = utils.parse_stack(self.t, stack_name='volume_check_fail')
        res = stack['DataVolume']
        res.cinder = mock.Mock()
        res.cinder().volumes.get.side_effect = Exception('boom')

        self.assertRaises(exception.ResourceFailure,
                          scheduler.TaskRunner(res.check))
        self.assertEqual((res.CHECK, res.FAILED), res.state)
        self.assertIn('boom', res.status_reason)

    def test_snapshot(self):
        stack_name = 'test_volume_snapshot_stack'
        fv = vt_base.FakeVolume('creating', 'available')
        fb = vt_base.FakeBackup('creating', 'available')

        self._mock_create_volume(fv, stack_name)

        # snapshot script
        self.m.StubOutWithMock(self.cinder_fc.backups, 'create')
        self.cinder_fc.backups.create('vol-123').AndReturn(fb)
        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)

        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['DeletionPolicy'] = 'Snapshot'
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = self.create_volume(self.t, stack, 'DataVolume')

        self._mock_delete_volume(fv)
        scheduler.TaskRunner(rsrc.destroy)()

        self.m.VerifyAll()

    def test_snapshot_error(self):
        stack_name = 'test_volume_snapshot_err_stack'
        fv = vt_base.FakeVolume('creating', 'available')
        fb = vt_base.FakeBackup('creating', 'error')

        self._mock_create_volume(fv, stack_name)

        # snapshot script
        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)
        self.m.StubOutWithMock(self.cinder_fc.backups, 'create')
        self.cinder_fc.backups.create('vol-123').AndReturn(fb)
        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['DeletionPolicy'] = 'Snapshot'
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        rsrc = self.create_volume(self.t, stack, 'DataVolume')

        ex = self.assertRaises(exception.ResourceFailure,
                               scheduler.TaskRunner(rsrc.destroy))
        self.assertIn('Unknown status error', six.text_type(ex))

        self.m.VerifyAll()

    def test_snapshot_no_volume(self):
        stack_name = 'test_volume_snapshot_novol_stack'

        cfg.CONF.set_override('action_retry_limit', 0)
        fv = vt_base.FakeVolume('creating', 'error')

        self._mock_create_volume(fv, stack_name)

        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)

        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['DeletionPolicy'] = 'Snapshot'
        self.t['Resources']['DataVolume']['Properties'][
            'AvailabilityZone'] = 'nova'
        stack = utils.parse_stack(self.t, stack_name=stack_name)
        resource_defns = stack.t.resource_definitions(stack)
        rsrc = aws_vol.Volume('DataVolume',
                              resource_defns['DataVolume'],
                              stack)

        create = scheduler.TaskRunner(rsrc.create)
        ex = self.assertRaises(exception.ResourceFailure, create)
        self.assertIn('Went to status error due to "Unknown"',
                      six.text_type(ex))

        self._mock_delete_volume(fv)
        scheduler.TaskRunner(rsrc.destroy)()

        self.m.VerifyAll()

    def test_create_from_snapshot(self):
        stack_name = 'test_volume_create_from_snapshot_stack'
        fv = vt_base.FakeVolumeWithStateTransition(
            'restoring-backup', 'available')
        fvbr = vt_base.FakeBackupRestore('vol-123')

        # create script
        cinder.CinderClientPlugin._create().AndReturn(
            self.cinder_fc)
        self.m.StubOutWithMock(self.cinder_fc.restores, 'restore')
        self.cinder_fc.restores.restore('backup-123').AndReturn(fvbr)
        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)
        self.m.StubOutWithMock(fv, 'update')
        vol_name = utils.PhysName(stack_name, 'DataVolume')
        fv.update(description=vol_name, name=vol_name)

        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['Properties'][
            'SnapshotId'] = 'backup-123'
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)

        self.m.VerifyAll()

    def test_create_from_snapshot_error(self):
        stack_name = 'test_volume_create_from_snap_err_stack'
        cfg.CONF.set_override('action_retry_limit', 0)
        fv = vt_base.FakeVolumeWithStateTransition(
            'restoring-backup', 'error')
        fvbr = vt_base.FakeBackupRestore('vol-123')

        # create script
        cinder.CinderClientPlugin._create().AndReturn(
            self.cinder_fc)
        self.m.StubOutWithMock(self.cinder_fc.restores, 'restore')
        self.cinder_fc.restores.restore('backup-123').AndReturn(fvbr)
        self.cinder_fc.volumes.get('vol-123').AndReturn(fv)
        self.m.StubOutWithMock(fv, 'update')
        vol_name = utils.PhysName(stack_name, 'DataVolume')
        fv.update(description=vol_name, name=vol_name)

        self.m.ReplayAll()

        self.t['Resources']['DataVolume']['Properties'][
            'SnapshotId'] = 'backup-123'
        stack = utils.parse_stack(self.t, stack_name=stack_name)

        ex = self.assertRaises(exception.ResourceFailure,
                               self.create_volume, self.t, stack, 'DataVolume')
        self.assertIn('Went to status error due to "Unknown"',
                      six.text_type(ex))

        self.m.VerifyAll()

    def test_volume_size_constraint(self):
        self.t['Resources']['DataVolume']['Properties']['Size'] = '0'
        stack = utils.parse_stack(self.t)
        error = self.assertRaises(exception.StackValidationFailed,
                                  self.create_volume,
                                  self.t, stack, 'DataVolume')
        self.assertEqual(
            "Property error : DataVolume: Size 0 is out of "
            "range (min: 1, max: None)", six.text_type(error))

    def test_volume_attachment_updates_not_supported(self):
        self.m.StubOutWithMock(nova.NovaClientPlugin, 'get_server')
        nova.NovaClientPlugin.get_server(mox.IgnoreArg()).AndReturn(
            mox.MockAnything())
        fv = vt_base.FakeVolume('creating', 'available')
        fva = vt_base.FakeVolume('attaching', 'in-use')
        stack_name = 'test_volume_attach_updnotsup_stack'

        self._mock_create_volume(fv, stack_name)
        self._mock_create_server_volume_script(fva)
        self.stub_VolumeConstraint_validate()

        self.m.ReplayAll()

        stack = utils.parse_stack(self.t, stack_name=stack_name)

        self.create_volume(self.t, stack, 'DataVolume')
        self.assertEqual('available', fv.status)
        rsrc = self.create_attachment(self.t, stack, 'MountPoint')

        props = copy.deepcopy(rsrc.properties.data)
        props['InstanceId'] = 'some_other_instance_id'
        props['VolumeId'] = 'some_other_volume_id'
        props['Device'] = '/dev/vdz'
        after = rsrc_defn.ResourceDefinition(rsrc.name, rsrc.type(), props)

        update_task = scheduler.TaskRunner(rsrc.update, after)
        ex = self.assertRaises(exception.ResourceFailure, update_task)
        self.assertIn('NotSupported: Update to properties Device, InstanceId, '
                      'VolumeId of MountPoint (AWS::EC2::VolumeAttachment)',
                      six.text_type(ex))
        self.assertEqual((rsrc.UPDATE, rsrc.FAILED), rsrc.state)
        self.m.VerifyAll()
