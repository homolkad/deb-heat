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
#

import util
import verify
from nose.plugins.attrib import attr
import unittest
import os


@attr(speed='slow')
@attr(tag=['func', 'wordpress', 'composed', 'F17',
      'WordPress_Composed_Instances.template'])
class WordPressComposedInstancesFunctionalTest(unittest.TestCase):
    def setUp(self):
        template = 'WordPress_Composed_Instances.template'

        stack_paramstr = ';'.join(['InstanceType=m1.xlarge',
                                   'DBUsername=dbuser',
                                   'DBPassword=' + os.environ['OS_PASSWORD']])

        self.stack = util.Stack(self, template, 'F17', 'x86_64', 'cfntools',
                                stack_paramstr)

        self.WebServer = util.Instance(self, 'WebServer')

        self.MySqlDatabaseServer = util.Instance(
            self,
            'DatabaseTemplate.MySqlDatabaseServer')

    def tearDown(self):
        self.stack.cleanup()

    def test_instance(self):
        self.stack.create()

        self.WebServer.wait_for_boot()
        self.MySqlDatabaseServer.wait_for_boot()

        self.WebServer.check_cfntools()
        self.WebServer.wait_for_provisioning()

        self.MySqlDatabaseServer.check_cfntools()
        self.MySqlDatabaseServer.wait_for_provisioning()

        self.assertTrue(self.WebServer.file_present
                        ('/etc/wordpress/wp-config.php'))
        print 'Wordpress installation detected.'

        # Verify the output URL parses as expected, ie check that
        # thewordpress installation is operational
        stack_url = self.stack.get_stack_output("WebsiteURL")
        print "Verifying stack output from WebsiteUrl=(%s)." % stack_url
        ver = verify.VerifyStack()
        self.assertTrue(ver.verify_wordpress(stack_url))
