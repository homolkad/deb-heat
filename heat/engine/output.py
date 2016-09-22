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

from heat.engine import function


class OutputDefinition(object):
    """A definition of a stack output, independent of any template format."""

    def __init__(self, name, value, description=None):
        self.name = name
        self._value = value
        self._resolved_value = None
        self._description = description

    def validate(self):
        """Validate the output value without resolving it."""
        function.validate(self._value)

    def dep_attrs(self, resource_name):
        """Iterate over attributes of a given resource that this references.

        Return an iterator over dependent attributes for specified
        resource_name in the output's value field.
        """
        return function.dep_attrs(self._value, resource_name)

    def get_value(self):
        """Resolve the value of the output."""
        if self._resolved_value is None:
            self._resolved_value = function.resolve(self._value)
        return self._resolved_value

    def description(self):
        """Return a description of the output."""
        if self._description is None:
            return 'No description given'

        return six.text_type(self._description)
