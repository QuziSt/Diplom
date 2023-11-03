from django.http import JsonResponse
from django.utils.crypto import get_random_string
from .app_choices import UserConfirmation


def check_email(details, *args, **kwargs):
    if not details['email']:
        return JsonResponse({'error': 'authentication without email is not provided. '
                                      'Please add an email to your social account'})


def set_random_password(details, is_new, *args, **kwargs):
    if is_new:
        random_password = get_random_string(length=8)
        details['password'] = random_password
        return {'random_password': random_password}


def set_is_confirmed(details, is_new, *args, **kwargs):
    if is_new: details['need_confirmation'] = UserConfirmation.confirmed


def get_credentials(user, is_new, random_password=None, *args, **kwargs):

    data = {}

    if is_new:
        data['token'] = user.create_auth_token()
        data['email'] = user.email
        data['password'] = random_password

    else:
        data['token'] = user.auth_token.key

    return JsonResponse(data, status=200)

