from django.db.models import Q
from django_filters import rest_framework as filters, DateFromToRangeFilter
from .models import ProductInfo, SellerOrder, BuyerOrder


class ProductFilter(filters.FilterSet):
    name = filters.CharFilter(method='filter_name')
    shop = filters.CharFilter(method='filter_shop')
    min_price = filters.NumberFilter(field_name='price', lookup_expr='gte')
    max_price = filters.NumberFilter(field_name='price', lookup_expr='lte')
    min_price_rrc = filters.NumberFilter(field_name='price_rrc', lookup_expr='gte')
    max_price_rrc = filters.NumberFilter(field_name='price_rrc', lookup_expr='lte')
    category = filters.CharFilter(method='filter_category')
    quantity = filters.NumberFilter(field_name='quantity', lookup_expr='gte')

    class Meta:
        model = ProductInfo
        fields = ('name',
                  'shop',
                  'min_price',
                  'max_price',
                  'min_price_rrc',
                  'max_price_rrc',
                  'category',
                  'quantity')

    def filter_name(self, queryset, name, value):
        return self.get_multiple_values_queryset(value, queryset, 'product__name__icontains')

    def filter_shop(self, queryset, name, value):
        return self.get_multiple_values_queryset(value, queryset, 'shop__name__icontains')

    def filter_category(self,  queryset, name, value):
        return self.get_multiple_values_queryset(value, queryset, 'category__category__name__icontains')

    def get_multiple_values_queryset(self, url_parameter_value, queryset, searched_model_attribute):
        values = url_parameter_value.split(',')
        filtering_object = Q()
        kwargs = {searched_model_attribute: None}
        for value in values:
            kwargs[searched_model_attribute] = value
            filtering_object |= Q(**kwargs)
        return queryset.filter(filtering_object)


class PartnerProductFilter(ProductFilter):
    product_external_id = filters.NumberFilter(field_name='external_id')
    category_external_id = filters.NumberFilter(field_name='category__external_id')

    class Meta(ProductFilter.Meta):
        model = ProductInfo
        fields = ('product_external_id', 'category_external_id') + ProductFilter.Meta.fields


class BuyerOrderFilter(filters.FilterSet):
    phone = filters.CharFilter(field_name='seller_orders__contact__phone', lookup_expr='icontains')
    created_at = DateFromToRangeFilter(field_name='created_at')

    class Meta:
        model = BuyerOrder
        fields = ('phone', 'created_at')


class SellerOrderFilter(filters.FilterSet):
    email = filters.CharFilter(field_name='buyer_order__user__email')
    phone = filters.CharFilter(field_name='contact__phone', lookup_expr='icontains')
    created_at = DateFromToRangeFilter(field_name='created_at')

    class Meta:
        model = SellerOrder
        fields = ('email', 'phone', 'created_at')

