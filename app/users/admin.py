from django.contrib.admin import register as admin_register, ModelAdmin, TabularInline
from django.contrib.auth.admin import UserAdmin
from imagekit.admin import AdminThumbnail
from .models import User, ConfirmRegistrationToken, Shop, Category, Product, Contact, \
    ProductParameter, ProductInfo, SellerOrderItem, SellerOrder, \
    Parameter, ShopCategory, BuyerOrder, ValueOfParameter, Token


class SellerOrderItemInline(TabularInline):
    model = SellerOrderItem


class CategoryInline(TabularInline):
    model = Category


class ShopCategoryInline(TabularInline):
    model = ShopCategory


class ProductInline(TabularInline):
    model = Product


class ShopInline(TabularInline):
    model = Shop


class AuthTokenInline(TabularInline):
    model = Token


class ProductInfoInline(TabularInline):
    model = ProductInfo


class ProductParameterInline(TabularInline):
    model = ProductParameter


class ContactInline(TabularInline):
    model = Contact


class BuyerOrderInline(TabularInline):
    model = BuyerOrder


class SellerOrderInline(TabularInline):
    model = SellerOrder


@admin_register(User)
class CustomUserAdmin(UserAdmin):
    """
    Панель управления пользователями
    """
    model = User

    list_display = ('id',
                    'email',
                    'first_name',
                    'last_name',
                    'is_staff',
                    'need_confirmation',
                    '__str__',
                    'admin_thumbnail')

    admin_thumbnail = AdminThumbnail(image_field='picture_thumbnail')

    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('picture', 'email', 'first_name', 'last_name')}),
    )

    fieldsets = (
        (None, {'fields': ('picture', 'email', 'password', 'type')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'username')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'need_confirmation', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    list_filter = UserAdmin.list_filter + ('need_confirmation', )

    search_fields = ('email', )

    inlines = (ShopInline, AuthTokenInline, ContactInline, BuyerOrderInline, )


@admin_register(ConfirmRegistrationToken)
class ConfirmRegistrationTokenAdmin(ModelAdmin):
    list_display = ('user', 'token')
    search_fields = ('user__email', )


@admin_register(Shop)
class ShopAdmin(ModelAdmin):
    list_display = ('id', 'name', 'owner', 'email', 'url', 'is_open', 'base_shipping_price')

    search_fields = ('id', 'owner__email', 'email', 'name', 'url')
    list_filter = ('is_open', 'categories__category__name')
    inlines = (ShopCategoryInline, ProductInfoInline, )


@admin_register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('id', 'name', )
    search_fields = ('name', )
    inlines = (ShopCategoryInline, )


@admin_register(ShopCategory)
class ShopCategoryAdmin(ModelAdmin):
    list_display = ('external_id', 'shop', 'category')
    search_fields = ('external_id', 'shop__name')
    list_filter = ('category__name',)


@admin_register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('name', )
    search_fields = list_display


@admin_register(ProductInfo)
class ProductInfoAdmin(ModelAdmin):
    list_display = ('id',
                    'external_id',
                    'category',
                    'product',
                    'shop',
                    'quantity',
                    'price',
                    'price_rrc',
                    '__str__',
                    'admin_thumbnail')

    admin_thumbnail = AdminThumbnail(image_field='picture_thumbnail')

    search_fields = ('external_id', 'product__name')
    list_filter = ('shop__name', 'category__category__name')
    inlines = (ProductParameterInline, )


@admin_register(Parameter)
class ParameterAdmin(ModelAdmin):
    list_display = ('name', )
    search_fields = list_display


@admin_register(ValueOfParameter)
class ValueOfParameter(ModelAdmin):
    list_display = ('value', )
    search_fields = list_display


@admin_register(ProductParameter)
class ProductParameterAdmin(ModelAdmin):
    list_display = ('product_info', 'parameter', 'value')
    search_fields = ('product_info__product__name', )
    list_filter = ('parameter__name', 'value__value')


@admin_register(Contact)
class ContactAdmin(ModelAdmin):
    list_display = ('id', 'user', 'city', 'street', 'house', 'structure', 'building', 'apartment', 'phone', 'is_deleted')
    search_fields = (list_display[0], 'user__email') + list_display[2:-1]
    list_filter = ('is_deleted', )


@admin_register(BuyerOrder)
class BuyerOrderAdmin(ModelAdmin):
    list_display = ('id', 'user', 'state', 'total_sum', 'created_at', 'total_sum')
    search_fields = ('id', 'user__email', 'created_at')
    list_filter = ('state', )
    inlines = (SellerOrderInline,)


@admin_register(SellerOrder)
class SellerOrderAdmin(ModelAdmin):
    list_display = ('id', 'buyer_order', 'shop', 'updated_at', 'created_at', 'state', 'contact', 'shipping_price', 'summary')
    search_fields = ('id', 'buyer_order__id', 'buyer_order__user__email', 'shop__email', 'created_at', 'contact__phone')
    list_filter = ('state', 'shop__name', 'contact__city')
    inlines = (SellerOrderItemInline,)


@admin_register(SellerOrderItem)
class SellerOrderItemAdmin(ModelAdmin):
    list_display = ('id', 'order', 'product_info', 'quantity', 'purchase_price', 'purchase_price_rrc')
    search_fields = ('id', 'order__id', 'product_info__product__name', )
    list_filter = ('order__state', 'order__shop__name',)

