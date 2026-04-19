from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class CoreConfig(AppConfig):
    name = 'core'
    verbose_name = 'BITS Pilani Store'


class SWDAdminConfig(AdminConfig):
    default_site = 'core.admin.SWDAdminSite'
