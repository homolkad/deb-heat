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

import collections
import hashlib
import itertools
import six

from oslo_serialization import jsonutils

from heat.common import exception
from heat.common.i18n import _
from heat.engine import attributes
from heat.engine.cfn import functions as cfn_funcs
from heat.engine import function


class GetParam(function.Function):
    """A function for resolving parameter references.

    Takes the form::

        get_param: <param_name>

    or::

        get_param:
          - <param_name>
          - <path1>
          - ...
    """

    def __init__(self, stack, fn_name, args):
        super(GetParam, self).__init__(stack, fn_name, args)

        self.parameters = self.stack.parameters

    def result(self):
        args = function.resolve(self.args)

        if not args:
            raise ValueError(_('Function "%s" must have arguments') %
                             self.fn_name)

        if isinstance(args, six.string_types):
            param_name = args
            path_components = []
        elif isinstance(args, collections.Sequence):
            param_name = args[0]
            path_components = args[1:]
        else:
            raise TypeError(_('Argument to "%s" must be string or list') %
                            self.fn_name)

        if not isinstance(param_name, six.string_types):
            raise TypeError(_('Parameter name in "%s" must be string') %
                            self.fn_name)

        try:
            parameter = self.parameters[param_name]
        except KeyError:
            raise exception.UserParameterMissing(key=param_name)

        def get_path_component(collection, key):
            if not isinstance(collection, (collections.Mapping,
                                           collections.Sequence)):
                raise TypeError(_('"%s" can\'t traverse path') % self.fn_name)

            if not isinstance(key, (six.string_types, int)):
                raise TypeError(_('Path components in "%s" '
                                  'must be strings') % self.fn_name)

            return collection[key]

        try:
            return six.moves.reduce(get_path_component, path_components,
                                    parameter)
        except (KeyError, IndexError, TypeError):
            return ''


class GetAttThenSelect(cfn_funcs.GetAtt):
    """A function for resolving resource attributes.

    Takes the form::

        get_attr:
          - <resource_name>
          - <attribute_name>
          - <path1>
          - ...
    """

    def _parse_args(self):
        if (not isinstance(self.args, collections.Sequence) or
                isinstance(self.args, six.string_types)):
            raise TypeError(_('Argument to "%s" must be a list') %
                            self.fn_name)

        if len(self.args) < 2:
            raise ValueError(_('Arguments to "%s" must be of the form '
                               '[resource_name, attribute, (path), ...]') %
                             self.fn_name)

        self._path_components = self.args[2:]

        return tuple(self.args[:2])

    def result(self):
        attribute = super(GetAttThenSelect, self).result()
        if attribute is None:
            return None

        path_components = function.resolve(self._path_components)
        return attributes.select_from_attribute(attribute, path_components)

    def dep_attrs(self, resource_name):
        if self._resource().name == resource_name:
            path = function.resolve(self._path_components)
            attr = [function.resolve(self._attribute)]
            if path:
                attrs = [tuple(attr + path)]
            else:
                attrs = attr
        else:
            attrs = []
        return itertools.chain(function.dep_attrs(self.args, resource_name),
                               attrs)


class GetAtt(GetAttThenSelect):
    """A function for resolving resource attributes.

    Takes the form::

        get_attr:
          - <resource_name>
          - <attribute_name>
          - <path1>
          - ...
    """

    def result(self):
        path_components = function.resolve(self._path_components)
        attribute = function.resolve(self._attribute)

        r = self._resource()
        if (r.status in (r.IN_PROGRESS, r.COMPLETE) and
                r.action in (r.CREATE, r.ADOPT, r.SUSPEND, r.RESUME,
                             r.UPDATE)):
            return r.FnGetAtt(attribute, *path_components)
        else:
            return None


class GetAttAllAttributes(GetAtt):
    """A  function for resolving resource attributes.

    Takes the form::

        get_attr:
          - <resource_name>
          - <attributes_name>
          - <path1>
          - ...

    where <attributes_name> and <path1>, ... are optional arguments. If there
    is no <attributes_name>, result will be dict of all resource's attributes.
    Else function returns resolved resource's attribute.
    """

    def _parse_args(self):
        if not self.args:
            raise ValueError(_('Arguments to "%s" can be of the next '
                               'forms: [resource_name] or '
                               '[resource_name, attribute, (path), ...]'
                               ) % self.fn_name)
        elif isinstance(self.args, collections.Sequence):
            if len(self.args) > 1:
                return super(GetAttAllAttributes, self)._parse_args()
            else:
                return self.args[0], None
        else:
            raise TypeError(_('Argument to "%s" must be a list') %
                            self.fn_name)

    def dep_attrs(self, resource_name):
        """Check if there is no attribute_name defined, return empty chain."""
        if self._attribute is not None:
            return super(GetAttAllAttributes, self).dep_attrs(resource_name)
        elif self._resource().name == resource_name:
            res = self._resource()
            attrs = six.iterkeys(res.attributes_schema)
        else:
            attrs = []
        return itertools.chain(function.dep_attrs(self.args,
                                                  resource_name), attrs)

    def result(self):
        if self._attribute is None:
            r = self._resource()
            if (r.status in (r.IN_PROGRESS, r.COMPLETE) and
                    r.action in (r.CREATE, r.ADOPT, r.SUSPEND, r.RESUME,
                                 r.UPDATE, r.CHECK, r.SNAPSHOT)):
                return r.FnGetAtts()
            else:
                return None
        else:
            return super(GetAttAllAttributes, self).result()


class Replace(cfn_funcs.Replace):
    """A function for performing string substitutions.

    Takes the form::

        str_replace:
          template: <key_1> <key_2>
          params:
            <key_1>: <value_1>
            <key_2>: <value_2>
            ...

    And resolves to::

        "<value_1> <value_2>"

    This is implemented using Python's str.replace on each key. The order in
    which replacements are performed is undefined.
    """

    def _parse_args(self):
        if not isinstance(self.args, collections.Mapping):
            raise TypeError(_('Arguments to "%s" must be a map') %
                            self.fn_name)

        try:
            mapping = self.args['params']
            string = self.args['template']
        except (KeyError, TypeError):
            example = ('''str_replace:
              template: This is var1 template var2
              params:
                var1: a
                var2: string''')
            raise KeyError(_('"str_replace" syntax should be %s') %
                           example)
        else:
            return mapping, string


class ReplaceJson(Replace):
    '''
    A function for performing string substitutions.

    Behaves the same as Replace, but tolerates non-string parameter
    values, e.g map/list - these are serialized as json before doing
    the string substitution.
    '''

    def result(self):
        template = function.resolve(self._string)
        mapping = function.resolve(self._mapping)

        if not isinstance(template, six.string_types):
            raise TypeError(_('"%s" template must be a string') % self.fn_name)

        if not isinstance(mapping, collections.Mapping):
            raise TypeError(_('"%s" params must be a map') % self.fn_name)

        def replace(string, change):
            placeholder, value = change

            if not isinstance(placeholder, six.string_types):
                raise TypeError(_('"%s" param placeholders must be strings') %
                                self.fn_name)

            if value is None:
                value = ''

            if not isinstance(value,
                              (six.string_types, six.integer_types,
                               float, bool)):
                if isinstance(value,
                              (collections.Mapping, collections.Sequence)):
                    try:
                        value = jsonutils.dumps(value, default=None)
                    except TypeError:
                        raise TypeError(_('"%(name)s" params must be strings, '
                                          'numbers, list or map. '
                                          'Failed to json serialize %(value)s'
                                          ) % {'name': self.fn_name,
                                               'value': value})
                else:
                    raise TypeError(_('"%s" params must be strings, numbers, '
                                      'list or map. ') % self.fn_name)

            return string.replace(placeholder, six.text_type(value))

        return six.moves.reduce(replace, six.iteritems(mapping), template)


class GetFile(function.Function):
    """A function for including a file inline.

    Takes the form::

        get_file: <file_key>

    And resolves to the content stored in the files dictionary under the given
    key.
    """

    def __init__(self, stack, fn_name, args):
        super(GetFile, self).__init__(stack, fn_name, args)

        self.files = self.stack.t.files

    def result(self):
        args = function.resolve(self.args)
        if not (isinstance(args, six.string_types)):
            raise TypeError(_('Argument to "%s" must be a string') %
                            self.fn_name)

        f = self.files.get(args)
        if f is None:
            fmt_data = {'fn_name': self.fn_name,
                        'file_key': args}
            raise ValueError(_('No content found in the "files" section for '
                               '%(fn_name)s path: %(file_key)s') % fmt_data)
        return f


class Join(cfn_funcs.Join):
    """A function for joining strings.

    Takes the form::

        { "list_join" : [ "<delim>", [ "<string_1>", "<string_2>", ... ] ] }

    And resolves to::

        "<string_1><delim><string_2><delim>..."
    """


class JoinMultiple(function.Function):
    """A function for joining strings.

    Takes the form::

        { "list_join" : [ "<delim>", [ "<string_1>", "<string_2>", ... ] ] }

    And resolves to::

        "<string_1><delim><string_2><delim>..."

    Optionally multiple lists may be specified, which will also be joined.
    """

    def __init__(self, stack, fn_name, args):
        super(JoinMultiple, self).__init__(stack, fn_name, args)
        example = '"%s" : [ " ", [ "str1", "str2"] ...]' % fn_name
        fmt_data = {'fn_name': fn_name,
                    'example': example}

        if isinstance(args, (six.string_types, collections.Mapping)):
            raise TypeError(_('Incorrect arguments to "%(fn_name)s" '
                              'should be: %(example)s') % fmt_data)

        try:
            self._delim = args.pop(0)
            self._joinlist = args.pop(0)
        except IndexError:
            raise ValueError(_('Incorrect arguments to "%(fn_name)s" '
                               'should be: %(example)s') % fmt_data)
        # Optionally allow additional lists, which are appended
        for l in args:
            try:
                self._joinlist += l
            except (AttributeError, TypeError):
                raise TypeError(_('Incorrect arguments to "%(fn_name)s" '
                                'should be: %(example)s') % fmt_data)

    def result(self):
        strings = function.resolve(self._joinlist)
        if strings is None:
            strings = []
        if (isinstance(strings, six.string_types) or
                not isinstance(strings, collections.Sequence)):
            raise TypeError(_('"%s" must operate on a list') % self.fn_name)

        delim = function.resolve(self._delim)
        if not isinstance(delim, six.string_types):
            raise TypeError(_('"%s" delimiter must be a string') %
                            self.fn_name)

        def ensure_string(s):
            msg = _('Items to join must be string, map or list not %s'
                    ) % (repr(s)[:200])
            if s is None:
                return ''
            elif isinstance(s, six.string_types):
                return s
            elif isinstance(s, (collections.Mapping, collections.Sequence)):
                try:
                    return jsonutils.dumps(s, default=None)
                except TypeError:
                    msg = _('Items to join must be string, map or list. '
                            '%s failed json serialization'
                            ) % (repr(s)[:200])
            else:
                msg = _('Items to join must be string, map or list not %s'
                        ) % (repr(s)[:200])
            raise TypeError(msg)

        return delim.join(ensure_string(s) for s in strings)


class ResourceFacade(cfn_funcs.ResourceFacade):
    """A function for retrieving data in a parent provider template.

    A function for obtaining data from the facade resource from within the
    corresponding provider template.

    Takes the form::

        resource_facade: <attribute_type>

    where the valid attribute types are "metadata", "deletion_policy" and
    "update_policy".
    """

    _RESOURCE_ATTRIBUTES = (
        METADATA, DELETION_POLICY, UPDATE_POLICY,
    ) = (
        'metadata', 'deletion_policy', 'update_policy'
    )


class Removed(function.Function):
    """This function existed in previous versions of HOT, but has been removed.

    Check the HOT guide for an equivalent native function.
    """

    def validate(self):
        exp = (_("The function %s is not supported in this version of HOT.") %
               self.fn_name)
        raise exception.InvalidTemplateVersion(explanation=exp)

    def result(self):
        return super(Removed, self).result()


class Repeat(function.Function):
    """A function for iterating over a list of items.

    Takes the form::

        repeat:
            template:
                <body>
            for_each:
                <var>: <list>

    The result is a new list of the same size as <list>, where each element
    is a copy of <body> with any occurrences of <var> replaced with the
    corresponding item of <list>.
    """
    def __init__(self, stack, fn_name, args):
        super(Repeat, self).__init__(stack, fn_name, args)

        self._for_each, self._template = self._parse_args()

    def _parse_args(self):
        if not isinstance(self.args, collections.Mapping):
            raise TypeError(_('Arguments to "%s" must be a map') %
                            self.fn_name)

        try:
            for_each = function.resolve(self.args['for_each'])
            template = self.args['template']
        except (KeyError, TypeError):
            example = ('''repeat:
              template: This is %var%
              for_each:
                %var%: ['a', 'b', 'c']''')
            raise KeyError(_('"repeat" syntax should be %s') %
                           example)

        if not isinstance(for_each, collections.Mapping):
            raise TypeError(_('The "for_each" argument to "%s" must contain '
                              'a map') % self.fn_name)
        for v in six.itervalues(for_each):
            if not isinstance(v, list):
                raise TypeError(_('The values of the "for_each" argument to '
                                  '"%s" must be lists') % self.fn_name)

        return for_each, template

    def _do_replacement(self, keys, values, template):
        if isinstance(template, six.string_types):
            for (key, value) in zip(keys, values):
                template = template.replace(key, value)
            return template
        elif isinstance(template, collections.Sequence):
            return [self._do_replacement(keys, values, elem)
                    for elem in template]
        elif isinstance(template, collections.Mapping):
            return dict((self._do_replacement(keys, values, k),
                         self._do_replacement(keys, values, v))
                        for (k, v) in template.items())

    def result(self):
        keys = list(six.iterkeys(self._for_each))
        lists = [self._for_each[key] for key in keys]
        template = function.resolve(self._template)
        return [self._do_replacement(keys, items, template)
                for items in itertools.product(*lists)]


class Digest(function.Function):
    """A function for performing digest operations.

    Takes the form::

        digest:
          - <algorithm>
          - <value>

    Valid algorithms are the ones provided by natively by hashlib (md5, sha1,
    sha224, sha256, sha384, and sha512) or any one provided by OpenSSL.
    """

    def validate_usage(self, args):
        if not (isinstance(args, list) and
                all([isinstance(a, six.string_types) for a in args])):
            msg = _('Argument to function "%s" must be a list of strings')
            raise TypeError(msg % self.fn_name)

        if len(args) != 2:
            msg = _('Function "%s" usage: ["<algorithm>", "<value>"]')
            raise ValueError(msg % self.fn_name)

        if six.PY3:
            algorithms = hashlib.algorithms_available
        else:
            algorithms = hashlib.algorithms

        if args[0].lower() not in algorithms:
            msg = _('Algorithm must be one of %s')
            raise ValueError(msg % six.text_type(algorithms))

    def digest(self, algorithm, value):
        _hash = hashlib.new(algorithm)
        _hash.update(six.b(value))

        return _hash.hexdigest()

    def result(self):
        args = function.resolve(self.args)
        self.validate_usage(args)

        return self.digest(*args)


class StrSplit(function.Function):
    """A function for splitting delimited strings into a list.

    Optionally extracting a specific list member by index.

    Takes the form::

        str_split: [delimiter, string, <index> ]

    or::

        str_split:
          - delimiter
          - string
          - <index>
    If <index> is specified, the specified list item will be returned
    otherwise, the whole list is returned, similar to get_attr with
    path based attributes accessing lists.
    """

    def __init__(self, stack, fn_name, args):
        super(StrSplit, self).__init__(stack, fn_name, args)
        example = '"%s" : [ ",", "apples,pears", <index>]' % fn_name
        self.fmt_data = {'fn_name': fn_name,
                         'example': example}
        self.fn_name = fn_name

        if isinstance(args, (six.string_types, collections.Mapping)):
            raise TypeError(_('Incorrect arguments to "%(fn_name)s" '
                              'should be: %(example)s') % self.fmt_data)

    def result(self):
        args = function.resolve(self.args)

        try:
            delim = args.pop(0)
            str_to_split = args.pop(0)
        except (AttributeError, IndexError):
            raise ValueError(_('Incorrect arguments to "%(fn_name)s" '
                               'should be: %(example)s') % self.fmt_data)
        split_list = str_to_split.split(delim)

        # Optionally allow an index to be specified
        if args:
            try:
                index = int(args.pop(0))
            except ValueError:
                raise ValueError(_('Incorrect index to "%(fn_name)s" '
                                   'should be: %(example)s') % self.fmt_data)
            else:
                try:
                    res = split_list[index]
                except IndexError:
                    raise ValueError(_('Incorrect index to "%(fn_name)s" '
                                       'should be between 0 and '
                                       '%(max_index)s')
                                     % {'fn_name': self.fn_name,
                                        'max_index': len(split_list) - 1})
        else:
            res = split_list
        return res
