import yaml
from celery.result import AsyncResult
from django.contrib.auth import authenticate
from django.db.models import Prefetch
from django.urls import reverse
from django_rest_passwordreset.models import ResetPasswordToken
from django_rest_passwordreset.serializers import EmailSerializer
from django_rest_passwordreset.views import ResetPasswordConfirm, ResetPasswordRequestToken
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse, extend_schema_view
from rest_framework import mixins, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from project_orders.celery import app
from project_orders.redis import redis_storage
from .filters import ProductFilter, PartnerProductFilter, SellerOrderFilter, BuyerOrderFilter
from .pagination import PartnerPagination
from .permissions import IsPartner, IsShopOwnerOrReadOnly, NotIsImporting
from .serializers import UserCreateSerializer, UserUpdateSerializer, UserPictureUpdateSerializer, \
    ShopSerializer, ProductInfoSerializer, PartnerProductInfoSerializer, \
    CategorySerializer, ContactSerializer, BuyerOrderSerializer, \
    PartnerOrderSerializer, PartnerStateSerializer, AuthenticateSerializer, \
    CustomPasswordTokenSerializer, SellerOrderForBuyerOrderSerializer, OrderItemBaseSerializer, ImportSerializer, \
    SwaggerStringStatusResponseExampleSerializer, SwaggerTokenResponseExampleSerializer, \
    PartnerProductInfoUpdateSerializer, PartnerProductInfoPictureUpdateSerializer, BasketSerializer
from .models import User, ConfirmRegistrationToken, Shop, Category, ProductInfo, \
    BuyerOrder, SellerOrder, SellerOrderItem, Contact
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet
from .tasks import send_confirmation_email
from .importing_products import import_products
from .app_choices import SellerOrderState, BuyerOrderState, PartnerState, UserConfirmation
from django.utils import timezone


def fix_swagger_queryset_decorator(model):
    def wrapper(old_func):
        def new_func(self, *args, **kwargs):
            if getattr(self, 'swagger_fake_view', False):
                return model.objects.none()
            return old_func(self, *args, **kwargs)
        return new_func
    return wrapper


def api_error(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'error': message}, status=status_code)


def param_value_error(value):
    return api_error(f'`{value}` is not valid value')


class UserFromRequestMixin:
    @property
    def user(self):
        return self.request.auth.user


class ImportProcessMixin(UserFromRequestMixin):

    def get_task_id(self):
        return redis_storage.get(self.user.id)

    def set_task_id(self, task_id):
        return redis_storage.set(self.user.id, task_id)


class CustomResetPasswordRequestToken(ResetPasswordRequestToken):

    @extend_schema(request=EmailSerializer, responses=SwaggerStringStatusResponseExampleSerializer)
    def post(self, request, *args, **kwargs):
        result = super().post(request, *args, **kwargs)
        user_email = request.data.get('email')
        token_key = ResetPasswordToken.objects.filter(user__email=user_email).first().key
        send_confirmation_email.delay(user_email,
                                      subject='Password Reset Token',
                                      message=token_key)
        return result


@extend_schema_view(post=extend_schema(request=CustomPasswordTokenSerializer,
                                       responses=SwaggerStringStatusResponseExampleSerializer))
class CustomResetPasswordConfirm(ResetPasswordConfirm):
    serializer_class = CustomPasswordTokenSerializer


def _get_dynamic_serializer_class(request, create_serializer, update_serializer, picture_update_serializer):
    if request.method.lower() == 'patch':
        if 'multipart/form-data' in request.content_type.lower():
            return picture_update_serializer
        return update_serializer
    return create_serializer


@extend_schema_view(create=extend_schema(responses=UserCreateSerializer,
                                         request={'application/json': UserCreateSerializer}),

                    update=extend_schema(responses=UserUpdateSerializer,
                                         request={'application/json': UserUpdateSerializer,
                                                  'multipart/form-data': UserPictureUpdateSerializer}),

                    partial_update=extend_schema(responses=UserUpdateSerializer,
                                                 request={'application/json': UserUpdateSerializer,
                                                          'multipart/form-data': UserPictureUpdateSerializer})
                    )
class UserViewSet(mixins.CreateModelMixin,
                  mixins.RetrieveModelMixin,
                  mixins.UpdateModelMixin,
                  GenericViewSet,
                  UserFromRequestMixin):

    queryset = User.objects.all()
    http_method_names = ['get', 'post', 'patch']

    def get_serializer_class(self):
        return _get_dynamic_serializer_class(self.request,
                                             UserCreateSerializer,
                                             UserUpdateSerializer,
                                             UserPictureUpdateSerializer)

    def get_object(self):
        return self.user

    def get_permissions(self):
        """Получение прав для действий."""
        if self.action != 'create':
            return [IsAuthenticated()]
        return []


class AuthenticateView(APIView):
    @extend_schema(responses=SwaggerTokenResponseExampleSerializer, request=AuthenticateSerializer)
    def post(self, request, *args, **kwargs):

        credentials = request.data

        credentials_serializer = AuthenticateSerializer(data=credentials)
        credentials_serializer.is_valid(raise_exception=True)

        user = authenticate(request, username=credentials['email'], password=credentials['password'])
        
        if not user:
            return api_error('incorrect credentials', status.HTTP_418_IM_A_TEAPOT)
        elif user.need_confirmation:
            return api_error('your email has not been confirmed')

        return Response({'token_key': user.auth_token.key}, status.HTTP_200_OK)


class ConfirmEmailView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name='temp_token',
                location=OpenApiParameter.PATH,
                description='The email confirmation token',
                required=True,
                type=str
            ),
        ],
        responses=SwaggerTokenResponseExampleSerializer
    )
    def get(self, request, temp_token, *args, **kwargs):
        confirm_token_obj = ConfirmRegistrationToken.objects.filter(token=temp_token).select_related('user').first()
        if not confirm_token_obj:
            return api_error('incorrect link')
        user = confirm_token_obj.user
        token_key = user.create_auth_token()
        if user.need_confirmation == UserConfirmation.need_admin:
            user.is_superuser = True
            user.is_staff = True
        user.need_confirmation = UserConfirmation.confirmed
        user.save()
        confirm_token_obj.delete()
        return Response({'token_key': token_key}, status=status.HTTP_200_OK)


class ShopView(mixins.CreateModelMixin,
               mixins.RetrieveModelMixin,
               mixins.UpdateModelMixin,
               mixins.ListModelMixin,
               GenericViewSet):

    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    http_method_names = ['get', 'post', 'patch', 'put']

    def get_permissions(self):
        """Получение прав для действий."""
        permissions = [IsShopOwnerOrReadOnly()]
        if self.action in {'create', 'update', 'partial_update'}:
            permissions.append(IsAuthenticated())
        return permissions


class CategoryView(ReadOnlyModelViewSet):

    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class ProductView(ReadOnlyModelViewSet):
    serializer_class = ProductInfoSerializer

    filterset_class = ProductFilter

    def get_queryset(self, *args, **kwargs):
        return ProductInfo.objects.filter(shop__is_open=True, quantity__gt=0).all()


@extend_schema_view(create=extend_schema(responses=PartnerProductInfoSerializer,
                                         request={'application/json': PartnerProductInfoSerializer}),

                    update=extend_schema(responses=PartnerProductInfoUpdateSerializer,
                                         request={'application/json': PartnerProductInfoUpdateSerializer,
                                                  'multipart/form-data': PartnerProductInfoPictureUpdateSerializer}),

                    partial_update=extend_schema(responses=PartnerProductInfoUpdateSerializer,
                                                 request={'application/json': PartnerProductInfoUpdateSerializer,
                                                          'multipart/form-data': PartnerProductInfoPictureUpdateSerializer})
                    )
class PartnerProductView(ModelViewSet, UserFromRequestMixin):

    filterset_class = PartnerProductFilter
    pagination_class = PartnerPagination
    permission_classes = [IsAuthenticated, IsPartner, NotIsImporting]
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_serializer_class(self):
        return _get_dynamic_serializer_class(self.request,
                                             PartnerProductInfoSerializer,
                                             PartnerProductInfoUpdateSerializer,
                                             PartnerProductInfoPictureUpdateSerializer)

    def perform_destroy(self, instance):
        instance.quantity = 0
        instance.save()

    @fix_swagger_queryset_decorator(ProductInfo)
    def get_queryset(self, *args, **kwargs):
        return self.user.shop.product_infos.all()


class ImportView(APIView, ImportProcessMixin):

    def get_permissions(self):
        permissions = [IsAuthenticated()]
        if self.request.method.lower() == 'post':
            permissions.append(NotIsImporting())
        return permissions

    @extend_schema(responses=ImportSerializer)
    def get(self, request, *args, **kwargs):
        task_id = self.get_task_id()

        if not task_id:
            return Response({'status': 'no processing'}, status=status.HTTP_200_OK)

        task = AsyncResult(task_id.decode(), app=app)

        message = {'status': task.status,
                   'result': task.result}
        return Response(message, status=status.HTTP_200_OK)

    @extend_schema(responses=ImportSerializer,
                   request={'multipart/form-data': ImportSerializer})
    def post(self, request, *args, **kwargs):
        data = request.data
        ImportSerializer(data=data).is_valid(raise_exception=True)

        try:
            uploaded_file = data['file']
            yaml_data = uploaded_file.read().decode('utf-8')
            json_data = yaml.safe_load(yaml_data)
        except:
            return api_error('unable to load data from the file', status.HTTP_406_NOT_ACCEPTABLE)

        task = import_products.delay(self.user.id, self.user.email, json_data)

        self.set_task_id(task.id)

        return Response({'status': 'processing',
                         'result':  {'url': request.build_absolute_uri(reverse('partner_import'))}},
                        status=status.HTTP_201_CREATED)


class PartnerStateView(APIView, UserFromRequestMixin):

    permission_classes = [IsAuthenticated, IsPartner]

    @property
    def users_shop(self):
        return self.user.shop

    @extend_schema(responses=PartnerStateSerializer)
    def get(self, request):
        return Response({'shop_is_open': self.users_shop.is_open}, status=status.HTTP_200_OK)

    @extend_schema(responses=PartnerStateSerializer, request=PartnerStateSerializer)
    def post(self, request):
        states = {PartnerState.open: True, PartnerState.closed: False}

        state_serializer = PartnerStateSerializer(data=request.data)
        state_serializer.is_valid(raise_exception=True)

        new_state = state_serializer.validated_data['state']
        new_state = states[new_state]

        self.users_shop.is_open = new_state
        self.users_shop.save()
        return Response({'shop_is_open': new_state}, status=status.HTTP_201_CREATED)


class ContactView(ModelViewSet, UserFromRequestMixin):

    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    @fix_swagger_queryset_decorator(Contact)
    def get_queryset(self, *args, **kwargs):
        return self.user.contacts.filter(is_deleted=False).all()

    def perform_destroy(self, instance):
        instance.is_deleted = True
        instance.save()


BASKET_DEL_PARAM_NAME = 'product_info'
BASKET_DEL_PARAM_DELIMITER = ','


class BasketView(APIView, UserFromRequestMixin):

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=BasketSerializer)
    def get(self, request, *args, **kwargs):
        _basket_object = self.user.basket_object
        return Response(BasketSerializer(_basket_object).data if _basket_object else {},
                        status=status.HTTP_200_OK)

    @extend_schema(responses=BasketSerializer, request=OrderItemBaseSerializer(many=True))
    def post(self, request, *args, **kwargs):
        basket = self.user.basket_object or BuyerOrder.objects.create(user=self.request.auth.user,
                                                                      state=BuyerOrderState.basket)

        ordered_items_serializer = OrderItemBaseSerializer(data=request.data, many=True)
        ordered_items_serializer.is_valid(raise_exception=True)

        validated_ordered_items = {ordered_item_dict['product_info'].id: ordered_item_dict['quantity']
                                   for ordered_item_dict in ordered_items_serializer.validated_data}

        shops_with_ordered_products = \
            Shop.objects.filter(is_open=True,
                                product_infos__id__in=validated_ordered_items.keys())\
                .prefetch_related(Prefetch('product_infos',
                                            queryset=ProductInfo.objects.filter(id__in=validated_ordered_items.keys())),
                                  'product_infos__product')

        for shop in shops_with_ordered_products:
            order, created = SellerOrder.objects.get_or_create(buyer_order=basket,
                                                               shop=shop,
                                                               state=SellerOrderState.basket,
                                                               defaults={'shipping_price': shop.base_shipping_price})
            for product_info in shop.product_infos.all():
                SellerOrderItem.objects.update_or_create(order=order,
                                                         product_info=product_info,
                                                         defaults={'quantity': validated_ordered_items[product_info.id],
                                                                   'purchase_price': product_info.price,
                                                                   'purchase_price_rrc': product_info.price_rrc})

        return Response(BasketSerializer(self.user.basket_object).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses={
            200: OpenApiResponse(response=BasketSerializer,
                                 description='Deleted.'),
        },
        parameters=[
            OpenApiParameter(
                name=BASKET_DEL_PARAM_NAME,
                location=OpenApiParameter.QUERY,
                description=f'IDs of product info you want to remove from the basket. '
                            f'Example: {BASKET_DEL_PARAM_NAME}={BASKET_DEL_PARAM_DELIMITER.join(["1", "20", "5"])}',
                required=True,
                type=str
            ),
        ]
    )
    def delete(self, request, *args, **kwargs):

        ids_to_del_value: str = request.GET.get(BASKET_DEL_PARAM_NAME, None)

        if ids_to_del_value is None:
            return api_error(f'`{BASKET_DEL_PARAM_NAME}` - this URL`s parameter is required')

        ids_to_del_value = ids_to_del_value.strip(BASKET_DEL_PARAM_DELIMITER)

        if ids_to_del_value == '':
            return param_value_error(BASKET_DEL_PARAM_DELIMITER)

        ids_to_del = set()

        for item in ids_to_del_value.split(BASKET_DEL_PARAM_DELIMITER):

            if item == '':
                continue

            if item.isdigit() and (id_to_del := int(item)) > 0:
                ids_to_del.add(id_to_del)
            else:
                return param_value_error(item)

        basket = self.user.basket_queryset.prefetch_related('seller_orders__shop',
                                                            'seller_orders__ordered_items',
                                                            'seller_orders__ordered_items__product_info').first()

        if not basket:
            return api_error('Your basket does not exists')

        seller_orders_baskets = basket.seller_orders.all()

        all_ordered_ids = {ordered_item.product_info.id for seller_order in seller_orders_baskets
                                                        for ordered_item in seller_order.ordered_items.all()}
        unknown_ids = ids_to_del - all_ordered_ids

        if unknown_ids:
            unknown_ids = ', '.join(map(str, unknown_ids))
            return api_error(f'Unknown ids: {unknown_ids}')

        if basket.state == BuyerOrderState.basket and ids_to_del == all_ordered_ids:
            basket.delete()
            return Response({}, status=status.HTTP_200_OK)

        seller_orders_to_del = {}
        ordered_items_to_del = set()

        for seller_order in seller_orders_baskets:
            ordered_items = seller_order.ordered_items.all()
            ordered_items = {ordered_item: ordered_item.product_info.id for ordered_item in ordered_items}
            ordered_product_ids = set(ordered_items.values())
            items_to_del_in_current_order = ordered_product_ids & ids_to_del
            if not items_to_del_in_current_order:
                continue

            if ordered_product_ids == items_to_del_in_current_order:
                seller_orders_to_del[seller_order.id] = seller_order
            else:
                ordered_objects_to_del = (k for k, v in ordered_items.items() if v in items_to_del_in_current_order)

                for ordered_object in ordered_objects_to_del:
                    ordered_items_to_del.add(ordered_object.id)
                    seller_order.ordered_items.remove(ordered_object)

            ids_to_del -= items_to_del_in_current_order

            if not ids_to_del:
                break

        if seller_orders_to_del:
            basket.seller_orders.filter(id__in=seller_orders_to_del).delete()
            for seller_object in seller_orders_to_del.values():
                basket.seller_orders.remove(seller_object)

        if ordered_items_to_del:
            SellerOrderItem.objects.filter(id__in=ordered_items_to_del).delete()

        return Response(BasketSerializer(basket).data, status=status.HTTP_200_OK)


class OrderViewSet(mixins.CreateModelMixin,
                   mixins.ListModelMixin,
                   mixins.RetrieveModelMixin,
                   GenericViewSet,
                   UserFromRequestMixin):

    permission_classes = [IsAuthenticated]
    serializer_class = BuyerOrderSerializer
    filterset_class = BuyerOrderFilter
    http_method_names = ['get', 'post']

    @fix_swagger_queryset_decorator(BuyerOrder)
    def get_queryset(self, *args, **kwargs):
        return self.user.orders.exclude(state=BuyerOrderState.basket).all()

    def create(self, request, *args, **kwargs):
        user = self.user

        order = user.basket_queryset.prefetch_related('seller_orders__shop',
                                                      'seller_orders__ordered_items',
                                                      'seller_orders__ordered_items__product_info',
                                                      'seller_orders__ordered_items__product_info__product').first()
        if not order:
            return api_error('no order to confirm', status.HTTP_200_OK)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        users_contact = serializer.validated_data['contact']

        all_orders = order.seller_orders.all()

        acceptable_order = True
        quantity_to_update = {}
        ordered_items_strs = {}

        # проверка, какие товары заказаны больше, чем в наличии
        for seller_order in all_orders:

            ordered_items = seller_order.ordered_items.all()

            for ordered_item in ordered_items:
                ordered_product_info = PartnerProductInfoSerializer(ordered_item.product_info).data
                ordered_quantity = ordered_item.quantity
                available_quantity = ordered_product_info['quantity']
                result_quantity = available_quantity - ordered_quantity

                if result_quantity < 0:
                    acceptable_order = False
                    message = f'too many ordered. You ordered {ordered_quantity} pcs, ' \
                              f'but only {available_quantity} pcs in stock'
                    ordered_item.status = message

                elif acceptable_order:
                    quantity_to_update[ordered_product_info['id']] = result_quantity
                    current_order_ordered_items_strs = ordered_items_strs.setdefault(seller_order.id, [])
                    current_order_ordered_items_strs.append(f'id: {ordered_product_info["id"]}, '
                                                            f'external_id: {ordered_product_info["external_id"]}, '
                                                            f'quantity: {ordered_item.quantity}')

        if acceptable_order:
            # подтверждение заказа продавца
            current_date = timezone.now()
            for seller_order in all_orders:

                for ordered_item in seller_order.ordered_items.all():
                    ordered_product_info_id = ordered_item.product_info.id
                    ProductInfo.objects.filter(id=ordered_product_info_id)\
                                       .update(quantity=quantity_to_update[ordered_product_info_id])

                seller_order.contact = users_contact
                seller_order.state = SellerOrderState.new
                seller_order.created_at = current_date
                seller_order.save()

                subject = f'Новый заказ {seller_order.id}'
                message = f'{subject}\nТовары:\n{"".join(ordered_items_strs[seller_order.id])}\n' \
                          f'Доставить по адресу:\n{str(users_contact)}\n' \
                          f'Итог: {seller_order.summary}'

                send_confirmation_email.delay(seller_order.shop.email, subject=subject, message=message)

            order.state = BuyerOrderState.accepted
            order.created_at = current_date
            order.save()

            # уведомление покупателя
            ordered_items = []
            summary_shipping_price = 0

            for seller_order in order.seller_orders.all():
                for ordered_item in seller_order.ordered_items.all():
                    product_info = ordered_item.product_info
                    info = f'Товар: {product_info.product.name}, ' \
                           f'количество: {ordered_item.quantity}, ' \
                           f'сумма: {ordered_item.quantity * product_info.price}'
                    ordered_items.append(info)
                summary_shipping_price += seller_order.shipping_price

            ordered_items = '\n'.join(ordered_items)

            subject = f'Заказ {order.id}'
            message = f'Спасибо за {subject.lower()}!\n\n' \
                      f'Заказанные товары: \n{ordered_items}\n' \
                      f'Доставка по адресу: \n\n{str(users_contact)}\n' \
                      f'Суммарная цена доставки: {summary_shipping_price}\n' \
                      f'Итог: {order.total_sum}'

            send_confirmation_email.delay(user.email, subject=subject, message=message)

        return Response(self.get_serializer(order).data,
                        status=status.HTTP_201_CREATED if acceptable_order else status.HTTP_206_PARTIAL_CONTENT)


class BuyerSellerOrderView(mixins.DestroyModelMixin,
                           GenericViewSet,
                           UserFromRequestMixin):

    permission_classes = [IsAuthenticated]
    serializer_class = SellerOrderForBuyerOrderSerializer
    http_method_names = ['delete']

    @fix_swagger_queryset_decorator(SellerOrder)
    def get_queryset(self):
        return SellerOrder.objects.filter(buyer_order__user_id=self.user.id,
                                          state__in=SellerOrderState.get_cancelable_by_user_states()
                                          ).prefetch_related('ordered_items',
                                                             'ordered_items__product_info').all()

    def perform_destroy(self, seller_order_instance):
        buyer_order = seller_order_instance.buyer_order

        if seller_order_instance.state == SellerOrderState.basket:
            seller_order_instance.delete()

            if not buyer_order.seller_orders.exists():
                buyer_order.delete()
                return
        else:
            seller_order_instance.rollback_product_quantity(buyer_order)

            seller_order_instance.state = SellerOrderState.canceled
            seller_order_instance.save()

            seller_email = seller_order_instance.shop.email
            subject = f'Заказ {seller_order_instance.id} отменён'
            message = f'{subject} пользователем. Товары возвращены на склад.'
            send_confirmation_email.delay(seller_email, subject=subject, message=message)


class PartnerOrderView(mixins.RetrieveModelMixin,
                       # продавец может менять только state и shipping_price
                       mixins.UpdateModelMixin,
                       mixins.ListModelMixin,
                       GenericViewSet,
                       UserFromRequestMixin):

    permission_classes = [IsAuthenticated, IsPartner]
    serializer_class = PartnerOrderSerializer
    pagination_class = PartnerPagination
    filterset_class = SellerOrderFilter
    http_method_names = ['get', 'patch']

    @fix_swagger_queryset_decorator(SellerOrder)
    def get_queryset(self):
        return self.user.shop.orders.exclude(state=SellerOrderState.basket).all()

