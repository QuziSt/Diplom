from rest_framework.pagination import PageNumberPagination
from .serializers import ShopSerializer


class PartnerPagination(PageNumberPagination):

    @property
    def shop_example(self):
        # example = {field_name: field.__class__.__name__
        #            for field_name, field in ShopSerializer().get_fields().items() if not field.write_only}
        example = {'id': 5,
                   'name': 'YourShop',
                   'url': 'http://yourshop.com/',
                   'email': 'shopmail@example.com'}
        return example

    def get_paginated_response(self, *args, **kwargs):
        response = super().get_paginated_response(*args, **kwargs)
        shop = ShopSerializer(self.request.user.shop).data
        response.data = {'shop': shop, **response.data}
        return response

    def get_paginated_response_schema(self, *args, **kwargs):
        schema = super().get_paginated_response_schema(*args, **kwargs)
        schema['properties'] = {'shop':  {'type': 'dict', 'example': self.shop_example}, **schema['properties']}
        return schema
