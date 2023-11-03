import uuid
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.models import PermissionsMixin
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.db.models import Sum, F
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from project_orders.settings import BASE_DOMAIN, AVATAR_DEFAULT, get_avatar_path, \
    PRODUCT_PICTURE_DEFAULT, get_product_picture_path
from .app_choices import UserType, SellerOrderState, BuyerOrderState, UserConfirmation
from rest_framework.authtoken.models import Token
from phonenumber_field.modelfields import PhoneNumberField
from .tasks import send_confirmation_email
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFit


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifiers
    for authentication instead of usernames.
    """
    def create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email and password.
        """
        if not email:
            raise ValueError(_('The Email must be set'))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        """

        first_name = input('Enter first name: ')
        last_name = input('Enter last name: ')

        if not first_name:
            raise ValueError(_('Superuser must have first_name.'))
        if not last_name:
            raise ValueError(_('Superuser must have last_name.'))

        extra_fields['first_name'] = first_name
        extra_fields['last_name'] = last_name

        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', True)

        extra_fields.setdefault('need_confirmation', UserConfirmation.need_admin)

        user = self.create_user(email, password, **extra_fields)
        user.send_email_confirmation()
        return user


class User(AbstractBaseUser, PermissionsMixin):

    picture = models.ImageField(upload_to=get_avatar_path,
                                default=AVATAR_DEFAULT,
                                blank=False,
                                null=False)

    picture_thumbnail = ImageSpecField(source='picture',
                                       processors=[ResizeToFit(100, 100)],
                                       format='JPEG',
                                       options={'quality': 60})

    password = models.CharField(_('password'), max_length=128, null=False)
    first_name = models.CharField(max_length=30, null=False)
    last_name = models.CharField(max_length=30, null=False)
    username = models.CharField(max_length=30, blank=True)
    email = models.EmailField(_('email address'), unique=True, null=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    type = models.CharField(choices=UserType.choices, max_length=20, default=UserType.buyer)
    need_confirmation = models.IntegerField(choices=UserConfirmation.choices, default=UserConfirmation.need_user)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ('email',)

    def send_email_confirmation(self, request=None):
        token = uuid.uuid4()
        ConfirmRegistrationToken.objects.create(user=self, token=token)
        token_url = reverse('confirm_email', args=[token])
        full_url = request.build_absolute_uri(token_url) if request is not None else BASE_DOMAIN + token_url
        subject = 'Подтверждение регистрации'
        message = f'Для подтверждения регистрации и получения токена перейдите по ссылке: {full_url}'
        send_confirmation_email.delay(self.email, subject=subject, message=message)
        return full_url

    def update_auth_token(self):
        new_token_key = Token.generate_key()
        Token.objects.filter(user=self).update(key=new_token_key)
        return new_token_key

    def create_auth_token(self):
        new_token = Token(user=self)
        new_token.save()
        return new_token.key

    @property
    def basket_queryset(self):
        basket = self.orders.filter(state=BuyerOrderState.basket).prefetch_related('seller_orders')
        return basket

    @property
    def basket_object(self):
        return self.basket_queryset.first()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.password_copy = str(self.password)

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if self.password_copy and self.password != self.password_copy:
            self.update_auth_token()
        return super().save(*args, **kwargs)


class ConfirmRegistrationToken(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=150)

    class Meta:
        verbose_name = 'Токен подтверждения почты'
        verbose_name_plural = 'Токены подтверждения почты'
        ordering = ('user',)


class Shop(models.Model):
    owner = models.OneToOneField(User, on_delete=models.CASCADE, related_name='shop')
    name = models.CharField(max_length=50, unique=True, null=False)
    url = models.URLField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    email = models.EmailField(null=False)
    base_shipping_price = models.PositiveIntegerField(default=300)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.owner.type == UserType.buyer:
            self.owner.type = UserType.seller
            self.owner.save()
        return super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Магазин'
        verbose_name_plural = 'Магазины'
        ordering = ('email',)


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Список всех категорий'
        ordering = ('name',)


class ShopCategory(models.Model):
    external_id = models.BigIntegerField(validators=[MinValueValidator(1)])
    category = models.ForeignKey(Category,
                                 related_name='shops',
                                 blank=True,
                                 on_delete=models.CASCADE)

    shop = models.ForeignKey(Shop,
                             related_name='categories',
                             blank=True,
                             on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Категория магазина'
        verbose_name_plural = 'Категории магазинов'
        ordering = ('shop', 'category')
        constraints = [
            models.UniqueConstraint(fields=['shop', 'category', ], name='unique_shop_category'),
            models.UniqueConstraint(fields=['shop', 'external_id'], name='unique_shop_external_id')
        ]

    @property
    def name(self):
        return self.category.name

    def __str__(self):
        return f'{self.external_id} {self.name} {self.shop}'


class Product(models.Model):
    name = models.CharField(max_length=200, unique=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Список всех товаров'
        ordering = ('name',)


class ProductInfo(models.Model):

    picture = models.ImageField(upload_to=get_product_picture_path,
                                default=PRODUCT_PICTURE_DEFAULT,
                                blank=False,
                                null=False)

    picture_thumbnail = ImageSpecField(source='picture',
                                       processors=[ResizeToFit(100, 100)],
                                       format='JPEG',
                                       options={'quality': 60})

    external_id = models.BigIntegerField(validators=[MinValueValidator(1)])
    category = models.ForeignKey(ShopCategory, related_name='product_infos', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, related_name='product_infos', blank=True, on_delete=models.CASCADE)
    shop = models.ForeignKey(Shop, related_name='product_infos', blank=True, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.BigIntegerField(validators=[MinValueValidator(0)])
    price_rrc = models.BigIntegerField(validators=[MinValueValidator(0)])

    class Meta:
        verbose_name = 'Товар магазина'
        verbose_name_plural = 'Товары магазинов'
        ordering = ('shop',)
        constraints = [
            models.UniqueConstraint(fields=['shop', 'external_id'], name='unique_product_info'),
        ]

    def __str__(self):
        return f'{self.shop} {self.external_id} {self.product}'


class Parameter(models.Model):
    name = models.CharField(max_length=40)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Параметр'
        verbose_name_plural = 'Параметры'
        ordering = ('name',)


class ValueOfParameter(models.Model):
    value = models.CharField(max_length=100)

    def __str__(self):
        return self.value

    class Meta:
        verbose_name = 'Значение параметра'
        verbose_name_plural = 'Значения параметров'
        ordering = ('value',)


class ProductParameter(models.Model):
    product_info = models.ForeignKey(ProductInfo,
                                     related_name='product_parameters',
                                     blank=True,
                                     on_delete=models.CASCADE)
    parameter = models.ForeignKey(Parameter, related_name='product_parameters',
                                  blank=True,
                                  on_delete=models.CASCADE)
    value = models.ForeignKey(ValueOfParameter,
                              related_name='product_parameters',
                              blank=True,
                              on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Характеристика товара'
        verbose_name_plural = 'Характеристики товаров'
        ordering = ('product_info',)
        constraints = [
            models.UniqueConstraint(fields=['product_info', 'parameter'], name='unique_product_parameter'),
        ]


class Contact(models.Model):
    user = models.ForeignKey(User,
                             verbose_name='Пользователь',
                             related_name='contacts',
                             blank=True,
                             on_delete=models.CASCADE)

    city = models.CharField(max_length=50, verbose_name='Город')
    street = models.CharField(max_length=100, verbose_name='Улица')
    house = models.CharField(max_length=15, verbose_name='Дом', blank=True)
    structure = models.CharField(max_length=15, verbose_name='Корпус', blank=True)
    building = models.CharField(max_length=15, verbose_name='Строение', blank=True)
    apartment = models.CharField(max_length=15, verbose_name='Квартира', blank=True)
    phone = PhoneNumberField(verbose_name='Телефон')

    is_deleted = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Контакты пользователя'
        verbose_name_plural = 'Список контактов пользователя'
        ordering = ('user',)

    def __str__(self):
        fields = ('city', 'street', 'house', 'structure', 'building', 'apartment', 'phone', )

        return '\n'.join([f'{self._meta.get_field(field).verbose_name}: {getattr(self, field)}' for field in fields])


class BuyerOrder(models.Model):
    user = models.ForeignKey(User,
                             verbose_name='Пользователь',
                             related_name='orders',
                             null=True,
                             on_delete=models.CASCADE)

    created_at = models.DateTimeField(null=True)

    state = models.CharField(verbose_name='Статус', choices=BuyerOrderState.choices, max_length=16)

    @property
    def contact(self):
        return self.seller_orders.first().contact

    @property
    def total_sum(self):
        return sum([seller_order.summary for seller_order in self.seller_orders.all()
                    if seller_order.state != SellerOrderState.canceled])

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Список заказов покупателя'
        ordering = ('id',)

    def __str__(self):
        return f'{self.id} {self.user} {self.state} {self.created_at}'


class SellerOrder(models.Model):
    buyer_order = models.ForeignKey(BuyerOrder,
                                    verbose_name='Заказ покупателя',
                                    related_name='seller_orders',
                                    null=True,
                                    on_delete=models.CASCADE)

    shop = models.ForeignKey(Shop,
                             verbose_name='Заказы продавца',
                             related_name='orders',
                             null=True,
                             on_delete=models.CASCADE)

    updated_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(null=True)

    state = models.CharField(verbose_name='Статус', choices=SellerOrderState.choices, max_length=15)

    contact = models.ForeignKey(Contact,
                                verbose_name='Контакт',
                                related_name='seller_orders',
                                blank=True,
                                null=True,
                                on_delete=models.CASCADE)

    shipping_price = models.PositiveIntegerField()

    @property
    def summary(self):
        sum_of_products = self.ordered_items.aggregate(total=Sum(F('quantity') * F('purchase_price')))['total']
        if sum_of_products is None: sum_of_products = 0
        return sum_of_products + self.shipping_price

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Список заказов продавца'
        ordering = ('id',)

    def __str__(self):
        return f'{self.id} {self.buyer_order} {self.shop} {self.created_at}'

    def rollback_product_quantity(self, buyer_order=None):
        for ordered_item in self.ordered_items.all():
            product_info = ordered_item.product_info
            product_info.quantity += ordered_item.quantity
            product_info.save()

        if buyer_order is None: buyer_order = self.buyer_order

        if buyer_order.state != (partial_state := BuyerOrderState.partial_accepted):
            buyer_order.state = partial_state
            buyer_order.save()


class SellerOrderItem(models.Model):
    order = models.ForeignKey(SellerOrder,
                              verbose_name='Заказ',
                              related_name='ordered_items',
                              blank=True,
                              null=True,
                              on_delete=models.CASCADE)

    product_info = models.ForeignKey(ProductInfo,
                                     verbose_name='Информация о продукте',
                                     related_name='ordered_items',
                                     blank=True,
                                     on_delete=models.CASCADE)

    quantity = models.PositiveIntegerField(verbose_name='Количество')

    purchase_price = models.BigIntegerField(validators=[MinValueValidator(0)], blank=True, default=None)

    purchase_price_rrc = models.BigIntegerField(validators=[MinValueValidator(0)], blank=True, default=None)

    class Meta:
        verbose_name = 'Заказанная позиция'
        verbose_name_plural = 'Список заказанных позиций'
        ordering = ('product_info',)
        constraints = [
            models.UniqueConstraint(fields=['order_id', 'product_info'], name='unique_order_item'),
        ]

    def save(self, *args, **kwargs):
        if any((self.purchase_price is None, self.purchase_price_rrc is None)):
            self.purchase_price = self.product_info.price
            self.purchase_price_rrc = self.product_info.price_rrc
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.id} {self.order} {self.product_info}'
