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

from heat.engine import clients as heat_clients
from heat.openstack.common import log as logging


try:
    from barbicanclient import client as barbican_client
    from barbicanclient.common import auth
except ImportError:
    barbican_client = None
    auth = None
    LOG = logging.getLogger(__name__)
    LOG.warn(_("barbican plugin loaded, but "
               "python-barbicanclient requirement not satisfied."))


class Clients(heat_clients.OpenStackClients):

    def __init__(self, context):
        super(Clients, self).__init__(context)
        self._barbican = None

    def barbican(self):
        if self._barbican:
            return self._barbican

        keystone_client = self.keystone().client
        auth_plugin = auth.KeystoneAuthV2(keystone=keystone_client)
        self._barbican = barbican_client.Client(auth_plugin=auth_plugin)
        return self._barbican
