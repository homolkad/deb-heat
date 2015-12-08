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

import six

from heat.db import api as db_api
from heat.engine import service
from heat.engine import stack
from heat.tests.convergence.framework import message_processor
from heat.tests.convergence.framework import message_queue
from heat.tests.convergence.framework import scenario_template
from heat.tests import utils


class Engine(message_processor.MessageProcessor):
    """Wrapper to the engine service.

    Methods of this class will be called from the scenario tests.
    """

    queue = message_queue.MessageQueue('engine')

    def __init__(self):
        super(Engine, self).__init__('engine')

    def scenario_template_to_hot(self, scenario_tmpl):
        """Converts the scenario template into hot template."""
        hot_tmpl = {"heat_template_version": "2013-05-23"}
        resources = {}
        for res_name, res_def in six.iteritems(scenario_tmpl.resources):
            props = getattr(res_def, 'properties')
            depends = getattr(res_def, 'depends_on')
            res_defn = {"type": "OS::Heat::TestResource"}
            if props:
                props_def = {}
                for prop_name, prop_value in props.items():
                    if type(prop_value) == scenario_template.GetRes:
                        prop_res = getattr(prop_value, "target_name")
                        prop_value = {'get_resource': prop_res}
                    elif type(prop_value) == scenario_template.GetAtt:
                        prop_res = getattr(prop_value, "target_name")
                        prop_attr = getattr(prop_value, "attr")
                        prop_value = {'get_attr': [prop_res, prop_attr]}
                    props_def[prop_name] = prop_value
                res_defn["properties"] = props_def
            if depends:
                res_defn["depends_on"] = depends
            resources[res_name] = res_defn
        hot_tmpl['resources'] = resources
        return hot_tmpl

    @message_processor.asynchronous
    def create_stack(self, stack_name, scenario_tmpl):
        cnxt = utils.dummy_context()
        srv = service.EngineService("host", "engine")
        thread_group_mgr = service.ThreadGroupManager()
        srv.thread_group_mgr = thread_group_mgr
        hot_tmpl = self.scenario_template_to_hot(scenario_tmpl)
        srv.create_stack(cnxt, stack_name, hot_tmpl,
                         params={}, files={}, args={})

    @message_processor.asynchronous
    def update_stack(self, stack_name, scenario_tmpl):
        cnxt = utils.dummy_context()
        db_stack = db_api.stack_get_by_name(cnxt, stack_name)
        srv = service.EngineService("host", "engine")
        thread_group_mgr = service.ThreadGroupManager()
        srv.thread_group_mgr = thread_group_mgr
        hot_tmpl = self.scenario_template_to_hot(scenario_tmpl)
        stack_identity = {'stack_name': stack_name,
                          'stack_id': db_stack.id,
                          'tenant': db_stack.tenant,
                          'path': ''}
        srv.update_stack(cnxt, stack_identity, hot_tmpl,
                         params={}, files={}, args={})

    @message_processor.asynchronous
    def delete_stack(self, stack_name):
        cnxt = utils.dummy_context()
        db_stack = db_api.stack_get_by_name(cnxt, stack_name)
        stack_identity = {'stack_name': stack_name,
                          'stack_id': db_stack.id,
                          'tenant': db_stack.tenant,
                          'path': ''}
        srv = service.EngineService("host", "engine")
        srv.delete_stack(cnxt, stack_identity)

    @message_processor.asynchronous
    def rollback_stack(self, stack_name):
        cntxt = utils.dummy_context()
        db_stack = db_api.stack_get_by_name(cntxt, stack_name)
        stk = stack.Stack.load(cntxt, stack=db_stack)
        stk.rollback()
