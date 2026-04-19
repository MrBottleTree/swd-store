from django.contrib.admin.apps import AdminConfig


class SWDAdminConfig(AdminConfig):
    default_site = 'core.admin.SWDAdminSite'
