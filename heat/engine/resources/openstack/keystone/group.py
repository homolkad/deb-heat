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

from heat.common.i18n import _
from heat.engine import constraints
from heat.engine import properties
from heat.engine import resource
from heat.engine.resources.openstack.keystone import role_assignments
from heat.engine import support


class KeystoneGroup(resource.Resource,
                    role_assignments.KeystoneRoleAssignmentMixin):
    """Heat Template Resource for Keystone Group."""

    support_status = support.SupportStatus(
        version='2015.1',
        message=_('Supported versions: keystone v3'))

    default_client_name = 'keystone'

    PROPERTIES = (
        NAME, DOMAIN, DESCRIPTION
    ) = (
        'name', 'domain', 'description'
    )

    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('Name of keystone group.'),
            update_allowed=True
        ),
        DOMAIN: properties.Schema(
            properties.Schema.STRING,
            _('Name or id of keystone domain.'),
            default='default',
            update_allowed=True,
            constraints=[constraints.CustomConstraint('keystone.domain')]
        ),
        DESCRIPTION: properties.Schema(
            properties.Schema.STRING,
            _('Description of keystone group.'),
            default='',
            update_allowed=True
        )
    }

    properties_schema.update(
        role_assignments.KeystoneRoleAssignmentMixin.mixin_properties_schema)

    def validate(self):
        super(KeystoneGroup, self).validate()
        self.validate_assignment_properties()

    def _create_group(self,
                      group_name,
                      description,
                      domain):
        domain = self.client_plugin().get_domain_id(domain)

        return self.client().client.groups.create(
            name=group_name,
            domain=domain,
            description=description)

    def _delete_group(self, group_id):
        return self.client().client.groups.delete(group_id)

    def _update_group(self,
                      group_id,
                      domain,
                      new_name=None,
                      new_description=None):
        values = dict()

        if new_name is not None:
            values['name'] = new_name
        if new_description is not None:
            values['description'] = new_description

        values['group'] = group_id
        domain = self.client_plugin().get_domain_id(domain)
        values['domain_id'] = domain
        return self.client().client.groups.update(**values)

    def handle_create(self):
        group_name = (self.properties.get(self.NAME) or
                      self.physical_resource_name())
        description = self.properties.get(self.DESCRIPTION)
        domain = self.properties.get(self.DOMAIN)

        group = self._create_group(
            group_name=group_name,
            description=description,
            domain=domain
        )

        self.resource_id_set(group.id)

        self.create_assignment(group_id=group.id)

    def handle_update(self, json_snippet, tmpl_diff, prop_diff):
        name = prop_diff.get(self.NAME) or self.physical_resource_name()
        description = prop_diff.get(self.DESCRIPTION)
        domain = (prop_diff.get(self.DOMAIN) or
                  self._stored_properties_data.get(self.DOMAIN))

        self._update_group(
            group_id=self.resource_id,
            new_name=name,
            new_description=description,
            domain=domain
        )

        self.update_assignment(prop_diff=prop_diff, group_id=self.resource_id)

    def handle_delete(self):
        if self.resource_id is not None:
            try:
                self.delete_assignment(group_id=self.resource_id)

                self._delete_group(group_id=self.resource_id)
            except Exception as ex:
                self.client_plugin().ignore_not_found(ex)


def resource_mapping():
    return {
        'OS::Keystone::Group': KeystoneGroup
    }
