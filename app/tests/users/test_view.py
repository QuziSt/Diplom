import pytest
from django.urls import reverse
from django.utils.crypto import get_random_string
from rest_framework.test import APIClient
from users.app_choices import UserType
from users.models import User, Shop, Category
from model_bakery import baker
from rest_framework import status
from project_orders.settings import EMAIL_HOST_USER


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user_factory():
    def factory(**kwargs):
        return baker.make('users.User', **kwargs)
    return factory


user_data_etalon = {'first_name': 'test',
                    'last_name': 'test_last_name',
                    'email': EMAIL_HOST_USER,
                    'password': '123abc!!!'}


@pytest.fixture
def user():
    user = User.objects.create(**user_data_etalon)
    user.create_auth_token()
    return user


@pytest.fixture
def user_headers(user):
    return {'Authorization': f'Token {user.auth_token.key}'}


@pytest.fixture
def shop_factory():
    def factory(**kwargs):
        return baker.make(Shop, **kwargs)
    return factory


@pytest.fixture
def category_factory():
    def factory(**kwargs):
        return baker.make(Category, **kwargs)
    return factory


def _get_user_required_fields_fixture(etalon):
    fixture = [(etalon, status.HTTP_201_CREATED)]
    for key in etalon.keys():
        etalon_copy = etalon.copy()
        etalon_copy.pop(key)
        fixture.append((etalon_copy, status.HTTP_400_BAD_REQUEST))
    return fixture


@pytest.mark.parametrize(('data', 'status'),
                         _get_user_required_fields_fixture({**user_data_etalon,
                                                            'password2': user_data_etalon['password']}))
@pytest.mark.django_db
def test_user_required_fields_existance(client, data, status):
    url = reverse('users')
    response = client.post(url, data)
    assert response.status_code == status


def _get_password_fixture():
    etalon = (valid_password := get_random_string(8), valid_password, status.HTTP_201_CREATED)
    password_mismatching = ('VeryGoodPass404', 'VeriGoodPass500', status.HTTP_400_BAD_REQUEST)
    fixture = [etalon, password_mismatching]
    invalid_passwords = ['12345abc', 'qwerty12', 'password'] + [get_random_string(i) for i in range(8)]
    fixture.extend([(p, p, status.HTTP_400_BAD_REQUEST) for p in invalid_passwords])
    return fixture


@pytest.mark.parametrize(('password', 'password2', 'status'), _get_password_fixture())
@pytest.mark.django_db
def test_password_validation(client, password, password2, status):
    data = user_data_etalon.copy()
    data['password'] = password
    data['password2'] = password2
    response = client.post(reverse('users'), data=data)
    assert response.status_code == status


@pytest.mark.django_db
def test_shop_creating(client, user, user_headers):
    user_type_before = user.type
    shop_data = {'name': 'TestShopName',
                 'email': EMAIL_HOST_USER}
    response = client.post('/shops/', data=shop_data, headers=user_headers)
    assert response.status_code == status.HTTP_201_CREATED

    created_shop = Shop.objects.filter(owner=user).first()  # заодно проверяем, есть ли связь магазина с юзером
    assert created_shop
    assert user_type_before == UserType.buyer
    assert created_shop.owner.type == UserType.seller


@pytest.mark.parametrize(('state', 'is_open'), (('off', False), ('on', True)))
@pytest.mark.django_db
def test_change_shop_state(client, user, shop_factory, state, is_open, user_headers):
    shop = shop_factory(owner=user)
    response = client.post(reverse('partner_state'), data={'state': state}, headers=user_headers)
    assert response.status_code == status.HTTP_201_CREATED

    shop_new_state = Shop.objects.get(owner=user).is_open
    assert shop_new_state == is_open


@pytest.mark.django_db
def test_get_categories(client, category_factory):
    category_factory(_quantity=15)
    categories_objects = Category.objects.all()

    len_categories_objects = len(categories_objects)

    next_page = '/categories/'

    # тест пагинации
    category_count = 0

    while next_page:
        response = client.get(next_page)
        assert response.status_code == status.HTTP_200_OK

        response_data = response.json()

        assert len_categories_objects == response_data['count']

        for category in response_data['results']:
            category_object = categories_objects[category_count]
            assert category['name'] == category_object.name
            assert category['id'] == category_object.id
            category_count += 1

        next_page = response_data['next']

    assert category_count == len_categories_objects

