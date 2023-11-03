from celery.result import AsyncResult
from rest_framework.permissions import BasePermission
from project_orders.celery import app
from project_orders.redis import redis_storage
from .app_choices import UserType


class IsUser(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.auth.user == obj


class IsShopOwnerOrReadOnly(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method.lower() in {'get', 'post'}:
            return True
        return request.auth.user == obj.owner


class IsPartner(BasePermission):
    def has_permission(self, request, view):
        return request.auth.user.type == UserType.seller


class IsBuyer(BasePermission):
    def has_permission(self, request, view):
        return request.auth.user.type == UserType.buyer


class NotIsImporting(BasePermission):
    message = 'this action is not provided while import in progress. Please, wait.'

    def has_permission(self, request, view):
        task_id = redis_storage.get(request.auth.user.id)
        if not task_id:
            return True
        task = AsyncResult(task_id.decode(), app=app)
        return task.status != 'PENDING'

