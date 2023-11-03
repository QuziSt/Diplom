from django.db import IntegrityError
from rest_framework.exceptions import ValidationError
from .serializers import PartnerProductInfoSerializer
from .models import Shop
from celery import shared_task


@shared_task()
def import_products(user_id, user_email, json_data):

    try:
        shop_name = json_data['shop']
        categories_source = json_data['categories']
        categories = {category['id']: {'name': category['name'], 'external_id': category['id']}
                      for category in categories_source}
        products = json_data['goods']
    except KeyError as error:
        return {'error': 'parse error', 'invalid_field': str(error)}

    shop_email = json_data.get('email', user_email)
    shop_base_shipping_price = int(json_data.get('shipping_price', 300))
    try:
        shop, shop_created = \
            Shop.objects.get_or_create(owner_id=user_id, defaults={'name': shop_name,
                                                                   'email': shop_email,
                                                                   'base_shipping_price': shop_base_shipping_price})
    except IntegrityError:
        return {'error': f'{shop_name}: this shop_name is already occupied'}

    serializer = PartnerProductInfoSerializer

    validated_product_infos = []

    for product_source in products:
        __source_info = {'categories': categories_source, 'product': product_source}

        try:
            category_external_id = product_source['category']
            category = categories[category_external_id]
        except KeyError as error:
            return {'error': 'category parse or matching error', 'key': str(error)} | __source_info

        try:
            product_parameters = [dict(zip(('parameter', 'value'), i))
                                  for i in product_source['parameters'].items()]

            product_data = {'external_id': product_source['id'],
                            'category': category,
                            'product': {'name': product_source['name']},
                            'product_parameters': product_parameters,
                            'price': product_source['price'],
                            'price_rrc': product_source['price_rrc'],
                            'quantity': product_source['quantity']}

        except KeyError as error:
            return {'error': 'product parse error', 'invalid_field': str(error)} | __source_info

        product_info_serializer = serializer(data=product_data)

        try:
            product_info_serializer.is_valid(raise_exception=True)
        except ValidationError as error:
            return {'error': 'invalid product_info data', 'product_info': product_source} | error.detail

        validated_product_infos.append(product_info_serializer.validated_data)

    if shop_created or not shop.product_infos.exists():
        for product_info in validated_product_infos:
            serializer().create(product_info, shop=shop)
    else:
        shop.product_infos.exclude(external_id__in={product_info['external_id']
                                                    for product_info in validated_product_infos}).update(quantity=0)

        for product_info in validated_product_infos:
            serializer().update_or_create(product_info, shop=shop)

    return {'status': 'ok', 'shop_id': shop.id}
