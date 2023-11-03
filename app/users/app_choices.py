from django.db import models
from django.utils.translation import gettext_lazy as _


class UserType(models.TextChoices):
    buyer = 'buyer', _('Покупатель')
    seller = 'seller', _('Магазин')


class UserConfirmation(models.IntegerChoices):
    need_user = 2, _('Требуется подтверждение на статус пользователя')
    need_admin = 1, _('Требуется подтверждение на статус админа')
    confirmed = 0, _('Подтверждён')


class SellerOrderState(models.TextChoices):
    basket = 'basket', _('Статус корзины')
    new = 'new', _('Новый')
    confirmed = 'confirmed', _('Подтвержден')
    assembled = 'assembled', _('Собран')
    sent = 'sent', _('Отправлен')
    delivered = 'delivered', _('Доставлен')
    canceled = 'canceled', _('Отменен')

    @classmethod
    def get_cancelable_by_user_states(cls):
        return {cls.basket, cls.new, cls.confirmed, cls.assembled}


class BuyerOrderState(models.TextChoices):
    basket = 'basket', _('Статус корзины')
    partial_accepted = 'partial accepted', _('Частично принят')
    accepted = 'accepted', _('Принят')


class PartnerState(models.TextChoices):
    open = 'on', _('Открыт')
    closed = 'off', _('Закрыт')
