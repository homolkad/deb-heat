# Copyright (c) 2014 Hewlett-Packard Development Company, L.P.
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

from oslo_log import log as logging
import oslo_messaging
from osprofiler import profiler

from heat.common.i18n import _LE
from heat.common.i18n import _LI
from heat.common import messaging as rpc_messaging
from heat.openstack.common import service
from heat.rpc import worker_client as rpc_client

LOG = logging.getLogger(__name__)


@profiler.trace_cls("rpc")
class WorkerService(service.Service):
    """
    This service is dedicated to handle internal messages to the 'worker'
    (a.k.a. 'converger') actor in convergence. Messages on this bus will
    use the 'cast' rather than 'call' method to anycast the message to
    an engine that will handle it asynchronously. It won't wait for
    or expect replies from these messages.
    """

    RPC_API_VERSION = '1.0'

    def __init__(self,
                 host,
                 topic,
                 engine_id,
                 thread_group_mgr):
        super(WorkerService, self).__init__()
        self.host = host
        self.topic = topic
        self.engine_id = engine_id
        self.thread_group_mgr = thread_group_mgr

        self._rpc_client = None
        self._rpc_server = None

    def start(self):
        target = oslo_messaging.Target(
            version=self.RPC_API_VERSION,
            server=self.host,
            topic=self.topic)
        LOG.info(_LI("Starting WorkerService ..."))

        self._rpc_server = rpc_messaging.get_rpc_server(target, self)
        self._rpc_server.start()

        self._rpc_client = rpc_client.WorkerClient()

        super(WorkerService, self).start()

    def stop(self):
        # Stop rpc connection at first for preventing new requests
        LOG.info(_LI("Stopping WorkerService ..."))
        try:
            self._rpc_server.stop()
            self._rpc_server.wait()
        except Exception as e:
            LOG.error(_LE("WorkerService is failed to stop, %s"), e)

        super(WorkerService, self).stop()
