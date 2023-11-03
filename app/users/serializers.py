from django.contrib.auth.hashers import make_password, check_password
from django.core.validators import FileExtensionValidator
from django.db import IntegrityError
from django_rest_passwordreset.serializers import PasswordTokenSerializer
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueTogetherValidator
from .tasks import send_confirmation_email
from .models import User, Shop, Category, Product, Contact, \
    ProductParameter, ProductInfo, SellerOrderItem, SellerOrder, Parameter, ShopCategory, BuyerOrder, ValueOfParameter
from .app_choices import SellerOrderState, PartnerState
from django.contrib.auth.password_validation import validate_password


class ContactSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault(), write_only=True)

    class Meta:
        model = Contact
        fields = ('id', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'user', 'phone')
        read_only_fields = ('id',)

        validators = [
            UniqueTogetherValidator(
                queryset=model.objects.all(),
                fields=('user',
                        'city',
                        'street',
                        'house',
                        'structure',
                        'building',
                        'apartment',
                        'phone'),
                message='This contact is already exists.'
            )
        ]

    def update(self, instance, validated_data):
        if instance.seller_orders.exists():
            raise ValidationError({'error': 'can not to change contact. If you want, you can create a new'})
        return super().update(instance, validated_data)


class PasswordMatchValidateMixin:

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        if 'password' in attrs or 'password2' in attrs:
            password = attrs.get('password')
            confirmed_password = attrs.pop('password2', '')
            if password != confirmed_password:
                raise serializers.ValidationError({'password': 'Password mismatch'})
        return attrs


class PictureSerializerMixin(serializers.ModelSerializer):
    picture = serializers.ImageField(max_length=None, use_url=True, read_only=True)
    picture_thumbnail = serializers.ImageField(max_length=None, use_url=True, read_only=True)


class UserBaseSerializer(PasswordMatchValidateMixin, PictureSerializerMixin):

    password2 = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('id', )
        read_only_fields = ('id',)


class UserCreateSerializer(UserBaseSerializer):

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + \
                 ('username',
                  'email',
                  'first_name',
                  'last_name',
                  'password',
                  'password2',
                  'picture',
                  'picture_thumbnail', )
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        validated_data['password'] = make_password(validated_data['password'])
        user = super().create(validated_data)
        user.send_email_confirmation(self.context['request'])
        return user


class UserUpdateSerializer(UserBaseSerializer):

    current_password = serializers.CharField(required=False, write_only=True)

    class Meta(UserBaseSerializer.Meta):
        fields = UserBaseSerializer.Meta.fields + \
                 ('username',
                  'email',
                  'first_name',
                  'last_name',
                  'current_password',
                  'password',
                  'password2',
                  'picture',
                  'picture_thumbnail', )
        extra_kwargs = {'password': {'write_only': True},
                        'email': {'read_only': True}}

    def update(self, instance, validated_data):
        #  валидация при смене пароля
        if {'current_password', 'password', 'password2'} & validated_data.keys():
            current_password = validated_data.pop('current_password', '')
            if current_password == validated_data.get('password'):
                raise serializers.ValidationError({'password': 'Current password and new password can not be same'})
            if not check_password(current_password, instance.password):
                raise serializers.ValidationError({'current_password': 'Incorrect current password'})
            validated_data['password'] = make_password(validated_data['password'])

        return super().update(instance, validated_data)


class UserPictureUpdateSerializer(PictureSerializerMixin):
    picture = serializers.ImageField(max_length=None, use_url=True)

    class Meta:
        model = User
        fields = ('id',
                  'username',
                  'email',
                  'first_name',
                  'last_name',
                  'picture',
                  'picture_thumbnail', )

        read_only_fields = fields[:-2] + (fields[-1], )


class AuthenticateSerializer(serializers.Serializer):
    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True)


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ('id', 'name', 'url', 'email')
        read_only_fields = ('id',)

    def validate(self, data):
        request = self.context['request']
        user = request.auth.user
        if request.method.lower() == 'post' and Shop.objects.filter(owner=user).first():
            raise ValidationError({'error': 'you already have a shop'})
        return data

    def create(self, validated_data):
        """Метод для создания"""
        user = self.context['request'].auth.user
        validated_data['owner'] = user
        return super().create(validated_data)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name',)
        read_only_fields = ('id',)


class PartnerCategorySerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=50)
    external_id = serializers.IntegerField(min_value=1)

    class Meta:
        model = ShopCategory
        fields = ('id', 'name', 'external_id')
        read_only_fields = ('id',)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['id'] = instance.category.id
        return data


class BuyerCategorySerializer(PartnerCategorySerializer):

    class Meta(PartnerCategorySerializer.Meta):
        fields = ('id', 'name', )


class ProductSerializer(serializers.ModelSerializer):
    name = serializers.CharField()

    class Meta:
        model = Product
        fields = ('name', )


class ProductParameterSerializer(serializers.ModelSerializer):
    parameter = serializers.CharField()
    value = serializers.CharField()

    class Meta:
        model = ProductParameter
        fields = ('parameter', 'value',)


class ProductInfoBaseSerializer(PictureSerializerMixin):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(read_only=True, many=True)

    class Meta:
        model = ProductInfo


class ProductInfoSerializer(ProductInfoBaseSerializer):
    category = BuyerCategorySerializer(read_only=True)
    shop = ShopSerializer(read_only=True)

    class Meta(ProductInfoBaseSerializer.Meta):
        fields = ('id',
                  'category',
                  'product',
                  'product_parameters',
                  'shop',
                  'quantity',
                  'price',
                  'price_rrc',
                  'picture',
                  'picture_thumbnail', )
        read_only_fields = ('id',)


class ProductInfoForOrderSerializer(ProductInfoSerializer):
    class Meta(ProductInfoBaseSerializer.Meta):
        fields = ('id',
                  'category',
                  'product',
                  'product_parameters',
                  'price',
                  'price_rrc',
                  'picture',
                  'picture_thumbnail', )


class PartnerProductInfoBriefSerializer(serializers.ModelSerializer):
    product_parameters = ProductParameterSerializer(read_only=True, many=True)

    class Meta:
        model = ProductInfo
        fields = ('product_parameters', 'quantity', 'price', 'price_rrc',)


class PartnerProductInfoUpdateSerializer(ProductInfoBaseSerializer):
    product = ProductSerializer(read_only=True)
    product_parameters = ProductParameterSerializer(many=True)
    category = PartnerCategorySerializer(read_only=True)

    class Meta(ProductInfoBaseSerializer.Meta):
        fields = ('id',
                  'external_id',
                  'category',
                  'product',
                  'product_parameters',
                  'quantity',
                  'price',
                  'price_rrc',
                  'picture',
                  'picture_thumbnail',
                  )
        read_only_fields = ('id', 'external_id')

    def add_parameters(self, product_info: ProductInfo, product_parameters: list | tuple, replace_old: bool = False):
        if replace_old: product_info.product_parameters.all().delete()

        for parameter_dict in product_parameters:
            try:
                parameter, created = Parameter.objects.get_or_create(name=parameter_dict['parameter'])
                value, created = ValueOfParameter.objects.get_or_create(value=parameter_dict['value'])
                ProductParameter.objects.create(product_info=product_info,
                                                parameter=parameter,
                                                value=value)
            except:
                raise ValidationError({'product_parameters': 'bad fields'})

    def update(self, instance, validated_data):

        """
        Метод обновляет 'product_parameters', 'quantity', 'price', 'price_rrc'.
        Если указано поле 'product_parameters',
        то оно полностью заменяется на предоставленное (по логике PUT).
        """

        product_parameters = validated_data.pop('product_parameters', None)

        if product_parameters is not None:
            self.add_parameters(instance, product_parameters, replace_old=True)

        return super().update(instance, validated_data)


class PartnerProductInfoPictureUpdateSerializer(PartnerProductInfoUpdateSerializer):
    picture = serializers.ImageField(max_length=None, use_url=True)
    product_parameters = ProductParameterSerializer(many=True, read_only=True)

    class Meta(PartnerProductInfoUpdateSerializer.Meta):

        read_only_fields = PartnerProductInfoUpdateSerializer.Meta.fields[:-2] + \
                           (PartnerProductInfoUpdateSerializer.Meta.fields[-1], )


class PartnerProductInfoSerializer(PartnerProductInfoUpdateSerializer):
    product = ProductSerializer()
    category = PartnerCategorySerializer()

    #  метаданные от самого базового сериализатора
    class Meta(ProductInfoBaseSerializer.Meta):
        fields = ('id',
                  'external_id',
                  'category',
                  'product',
                  'product_parameters',
                  'quantity',
                  'price',
                  'price_rrc',
                  'picture',
                  'picture_thumbnail',
                  )

    @property
    def shop(self):
        return self.context['request'].auth.user.shop

    @property
    def is_importing(self):
        return not {'request', 'view'} & self.context.keys()

    def validate_external_id(self, value):
        if not self.is_importing and self.shop.product_infos.filter(external_id=value).exists():
            raise ValidationError(f'product with external_id {value} is already exists in your shop')
        return value

    def create(self, validated_data, shop=None):
        shop = shop or self.shop
        product_data = validated_data.pop('product')
        category_data = validated_data.pop('category')
        category_external_id = category_data['external_id']
        category_name = category_data['name']

        category_object, category_created = Category.objects.get_or_create(name=category_name)

        try:
            shop_category, shop_category_created = \
                shop.categories.get_or_create(category=category_object,
                                              defaults={'external_id': category_external_id})

        except IntegrityError:
            raise ValidationError({'category_external_id': f'category with external_id '
                                                           f'{category_external_id} already exists'})

        product_object, product_created = Product.objects.get_or_create(name=product_data['name'])

        product_parameters = validated_data.pop('product_parameters')

        product_info = ProductInfo.objects.create(product=product_object,
                                                  shop=shop,
                                                  category=shop_category,
                                                  **validated_data)

        self.add_parameters(product_info, product_parameters)
        return product_info

    def update_or_create(self, validated_data: dict, shop: Shop = None):
        shop = shop or self.shop

        instance = shop.product_infos.filter(external_id=validated_data['external_id'])\
            .prefetch_related('product_parameters',
                              'product_parameters__parameter',
                              'product_parameters__value').first()
        if instance:
            sort_key = lambda x: x['parameter']
            instance_data = PartnerProductInfoBriefSerializer(instance).data
            product_parameters_old = instance_data.pop('product_parameters')
            product_parameters_old.sort(key=sort_key)
            product_parameters_new = validated_data['product_parameters']
            fields_to_update = {key: validated_data[key]
                                for key, value in instance_data.items() if value != validated_data[key]}
            if product_parameters_old != sorted(product_parameters_new, key=sort_key):
                fields_to_update['product_parameters'] = product_parameters_new
            return self.update(instance, fields_to_update) if fields_to_update else instance
        else:
            return self.create(validated_data, shop)


class OrderItemBaseSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = SellerOrderItem
        fields = ('product_info', 'quantity')


class OrderItemBuyerSerializer(OrderItemBaseSerializer):

    status = serializers.CharField(read_only=True, required=False)

    class Meta(OrderItemBaseSerializer.Meta):
        fields = ('id', 'product_info', 'quantity', 'order', 'status',)
        extra_kwargs = {
            'order': {'write_only': True},

            'product_info': {'required': True},
            'quantity': {'required': True},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        product_info = data['product_info']
        product_info['price'] = instance.purchase_price
        product_info['price_rrc'] = instance.purchase_price_rrc
        return data


class SellerOrderItemCreateSerializer(OrderItemBuyerSerializer):
    product_info = ProductInfoForOrderSerializer(read_only=True)


class SellerOrderForBasketSerializer(serializers.ModelSerializer):
    shop = ShopSerializer(read_only=True)
    ordered_items = SellerOrderItemCreateSerializer(read_only=True, many=True)

    summary = serializers.IntegerField()

    class Meta:
        model = SellerOrder
        fields = ('id',
                  'shop',
                  'ordered_items',
                  'shipping_price',
                  'summary')


class SellerOrderForBuyerOrderSerializer(SellerOrderForBasketSerializer):
    class Meta(SellerOrderForBasketSerializer.Meta):
        fields = ('id',
                  'shop',
                  'ordered_items',
                  'shipping_price',
                  'updated_at',
                  'state',
                  'summary')


class BasketSerializer(serializers.ModelSerializer):
    seller_orders = SellerOrderForBasketSerializer(read_only=True, many=True)
    total_sum = serializers.IntegerField(read_only=True)

    class Meta:
        model = BuyerOrder
        fields = ('id', 'seller_orders', 'total_sum', )
        read_only_fields = ('id', )


class BuyerOrderSerializer(BasketSerializer):
    seller_orders = SellerOrderForBuyerOrderSerializer(read_only=True, many=True)
    contact = ContactSerializer(read_only=True)
    contact_id = serializers.PrimaryKeyRelatedField(queryset=Contact.objects.all(),
                                                    source='contact',
                                                    write_only=True)

    class Meta(BasketSerializer.Meta):
        fields = ('id', 'seller_orders', 'contact', 'contact_id', 'total_sum', 'state', 'created_at', )
        read_only_fields = BasketSerializer.Meta.read_only_fields + ('state', 'created_at', )

    def validate_contact_id(self, value):
        request = self.context['request']
        if not request.auth.user.contacts.filter(id=request.data.get('contact_id'), is_deleted=False).first():
            raise serializers.ValidationError('invalid contact')
        return value


class ProductInfoForSellerOrderSerializer(ProductInfoBaseSerializer):
    category = PartnerCategorySerializer()

    class Meta(ProductInfoBaseSerializer.Meta):
        fields = ('id',
                  'external_id',
                  'category',
                  'product',
                  'product_parameters',
                  'price',
                  'price_rrc',
                  'picture',
                  'picture_thumbnail',
                  )


class PartnerOrderProductsSerializer(OrderItemBuyerSerializer):
    product_info = ProductInfoForSellerOrderSerializer(read_only=True)


class PartnerOrderSerializer(serializers.ModelSerializer):
    ordered_items = PartnerOrderProductsSerializer(read_only=True, many=True)
    state = serializers.ChoiceField(choices=SellerOrderState.choices[1:])  # убираем статус корзины

    summary = serializers.IntegerField(read_only=True)
    contact = ContactSerializer(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = SellerOrder

        fields = ('id', 'ordered_items', 'contact', 'created_at', 'updated_at', 'state', 'shipping_price', 'summary')
        read_only_fields = ('id', 'updated_at')

    def validate_state(self, value):
        if self.instance.state in {SellerOrderState.canceled, SellerOrderState.delivered}:
            raise serializers.ValidationError('You can not change state of this order')
        return value

    def validate_shipping_price(self, value):
        if self.instance.state not in SellerOrderState.get_cancelable_by_user_states():
            raise serializers.ValidationError('You can not change shipping_price of this order')
        return value

    def update(self, instance, validated_data):
        if new_state := validated_data.get('state'):
            buyer_order = instance.buyer_order
            buyer_email = buyer_order.user.email
            seller_order_id = instance.id

            if new_state == SellerOrderState.canceled:
                instance.rollback_product_quantity(buyer_order)

            subject = f'Заказ {buyer_order.id}'
            message = f'Изменения в заказе {buyer_order.id}. ' \
                      f'\nСтатус вложенного заказа {seller_order_id} ' \
                      f'от магазина {instance.shop.name} изменён на: {new_state}\n\n'

            send_confirmation_email.delay(buyer_email, subject=subject, message=message)

        return super().update(instance, validated_data)


class PartnerStateSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=PartnerState.choices, write_only=True)
    shop_is_open = serializers.BooleanField(read_only=True)


class PositiveIntegers(serializers.ListSerializer):
    child = serializers.IntegerField(min_value=1)


class CustomPasswordTokenSerializer(PasswordTokenSerializer, PasswordMatchValidateMixin):
    password2 = serializers.CharField()

    def validate(self, data):
        PasswordTokenSerializer.validate(self, data)
        PasswordMatchValidateMixin.validate(self, data)
        return data


class ImportSerializer(serializers.Serializer):
    status = serializers.CharField(read_only=True)
    result = serializers.JSONField(allow_null=True, read_only=True)
    file = serializers.FileField(validators=[FileExtensionValidator(['yml', 'yaml'])], write_only=True)


class SwaggerStringStatusResponseExampleSerializer(serializers.Serializer):
    status = serializers.CharField(read_only=True)


class SwaggerTokenResponseExampleSerializer(serializers.Serializer):
    token_key = serializers.CharField(read_only=True)
