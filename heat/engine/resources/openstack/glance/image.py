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

from heat.common import exception
from heat.common.i18n import _
from heat.engine import constraints
from heat.engine import properties
from heat.engine import resource
from heat.engine import support


class GlanceImage(resource.Resource):
    """A resource managing images in Glance.

    A resource provides managing images that are meant to be used with other
    services.
    """

    support_status = support.SupportStatus(version='2014.2')

    PROPERTIES = (
        NAME, IMAGE_ID, IS_PUBLIC, MIN_DISK, MIN_RAM, PROTECTED,
        DISK_FORMAT, CONTAINER_FORMAT, LOCATION, TAGS
    ) = (
        'name', 'id', 'is_public', 'min_disk', 'min_ram', 'protected',
        'disk_format', 'container_format', 'location', 'tags'
    )

    properties_schema = {
        NAME: properties.Schema(
            properties.Schema.STRING,
            _('Name for the image. The name of an image is not '
              'unique to a Image Service node.')
        ),
        IMAGE_ID: properties.Schema(
            properties.Schema.STRING,
            _('The image ID. Glance will generate a UUID if not specified.')
        ),
        IS_PUBLIC: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Scope of image accessibility. Public or private. '
              'Default value is False means private.'),
            default=False,
        ),
        MIN_DISK: properties.Schema(
            properties.Schema.INTEGER,
            _('Amount of disk space (in GB) required to boot image. '
              'Default value is 0 if not specified '
              'and means no limit on the disk size.'),
            constraints=[
                constraints.Range(min=0),
            ],
            default=0
        ),
        MIN_RAM: properties.Schema(
            properties.Schema.INTEGER,
            _('Amount of ram (in MB) required to boot image. Default value '
              'is 0 if not specified and means no limit on the ram size.'),
            constraints=[
                constraints.Range(min=0),
            ],
            default=0
        ),
        PROTECTED: properties.Schema(
            properties.Schema.BOOLEAN,
            _('Whether the image can be deleted. If the value is True, '
              'the image is protected and cannot be deleted.'),
            default=False
        ),
        DISK_FORMAT: properties.Schema(
            properties.Schema.STRING,
            _('Disk format of image.'),
            required=True,
            constraints=[
                constraints.AllowedValues(['ami', 'ari', 'aki',
                                           'vhd', 'vmdk', 'raw',
                                           'qcow2', 'vdi', 'iso'])
            ]
        ),
        CONTAINER_FORMAT: properties.Schema(
            properties.Schema.STRING,
            _('Container format of image.'),
            required=True,
            constraints=[
                constraints.AllowedValues(['ami', 'ari', 'aki',
                                           'bare', 'ova', 'ovf'])
            ]
        ),
        LOCATION: properties.Schema(
            properties.Schema.STRING,
            _('URL where the data for this image already resides. For '
              'example, if the image data is stored in swift, you could '
              'specify "swift://example.com/container/obj".'),
            required=True,
        ),
        TAGS: properties.Schema(
            properties.Schema.LIST,
            _('List of image tags.'),
            update_allowed=True,
            support_status=support.SupportStatus(version='7.0.0')
        )
    }

    default_client_name = 'glance'

    entity = 'images'

    def handle_create(self):
        args = dict((k, v) for k, v in self.properties.items()
                    if v is not None)
        image_id = self.client().images.create(**args).id
        self.resource_id_set(image_id)

        if self.TAGS in args:
            for tag in args[self.TAGS]:
                self.client(
                    version=self.client_plugin().V2).image_tags.update(
                    image_id,
                    tag)

        return image_id

    def check_create_complete(self, image_id):
        image = self.client().images.get(image_id)
        return image.status == 'active'

    def handle_update(self, json_snippet=None, tmpl_diff=None, prop_diff=None):
        if prop_diff and self.TAGS in prop_diff:
            existing_tags = self.properties.get(self.TAGS, [])

            new_tags = set(prop_diff[self.TAGS]) - set(existing_tags)
            for tag in new_tags:
                self.client(
                    version=self.client_plugin().V2).image_tags.update(
                    self.resource_id,
                    tag)

            removed_tags = set(existing_tags) - set(prop_diff[self.TAGS])
            for tag in removed_tags:
                self.client(
                    version=self.client_plugin().V2).image_tags.delete(
                    self.resource_id,
                    tag)

    def _show_resource(self):
        if self.glance().version == 1.0:
            return super(GlanceImage, self)._show_resource()
        else:
            image = self.glance().images.get(self.resource_id)
            return dict(image)

    def validate(self):
        super(GlanceImage, self).validate()
        container_format = self.properties[self.CONTAINER_FORMAT]
        if (container_format in ['ami', 'ari', 'aki']
                and self.properties[self.DISK_FORMAT] != container_format):
            msg = _("Invalid mix of disk and container formats. When "
                    "setting a disk or container format to one of 'aki', "
                    "'ari', or 'ami', the container and disk formats must "
                    "match.")
            raise exception.StackValidationFailed(message=msg)

    def get_live_resource_data(self):
        image_data = super(GlanceImage, self).get_live_resource_data()
        if image_data.get('status') in ('deleted', 'killed'):
                raise exception.EntityNotFound(entity='Resource',
                                               name=self.name)
        return image_data

    def parse_live_resource_data(self, resource_properties, resource_data):
        image_reality = {}

        # NOTE(prazumovsky): At first, there's no way to get location from
        # glance; at second, location property is doubtful, because glance
        # client v2 doesn't use location, it uses locations. So, we should
        # get location property from resource properties.
        if self.client().version == 1.0:
            image_reality.update(
                {self.LOCATION: resource_properties[self.LOCATION]})

        for key in self.PROPERTIES:
            if key == self.LOCATION:
                continue
            if key == self.IMAGE_ID:
                if (resource_properties.get(self.IMAGE_ID) is not None or
                        resource_data.get(self.IMAGE_ID) != self.resource_id):
                    image_reality.update({self.IMAGE_ID: resource_data.get(
                        self.IMAGE_ID)})
                else:
                    image_reality.update({self.IMAGE_ID: None})
            else:
                image_reality.update({key: resource_data.get(key)})

        return image_reality


def resource_mapping():
    return {
        'OS::Glance::Image': GlanceImage
    }
