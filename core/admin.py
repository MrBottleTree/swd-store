from django.contrib import admin
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.auth.models import User, Group
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import (
    Person, Hostel, Category, Item, Image,
    Feedback, FeedbackImage, Reaction,
    PageView, LogIngestState,
)


class SWDAdminSite(admin.AdminSite):
    site_header = "SWD Store Admin"
    site_title = "SWD Store Admin"
    index_title = "Control Panel"

    def get_urls(self):
        from core.analytics.views import analytics_view, analytics_recent_json
        custom = [
            path('analytics/', self.admin_view(analytics_view), name='analytics'),
            path('analytics/recent.json', self.admin_view(analytics_recent_json), name='analytics_recent'),
        ]
        return custom + super().get_urls()

    def get_app_list(self, request, app_label=None):
        app_list = super().get_app_list(request, app_label)
        if app_label is None:
            try:
                url = reverse(f'{self.name}:analytics')
            except Exception:
                return app_list
            app_list.insert(0, {
                'name': 'Analytics',
                'app_label': '_analytics',
                'app_url': url,
                'has_module_perms': True,
                'models': [{
                    'name': 'Traffic dashboard',
                    'object_name': 'Analytics',
                    'admin_url': url,
                    'view_only': True,
                    'perms': {'view': True, 'add': False, 'change': False, 'delete': False},
                }],
            })
        return app_list


swd_admin_site = SWDAdminSite(name='admin')


class ImageInline(admin.TabularInline):
    model = Image
    extra = 0
    fields = ('preview', 'image', 'display_order', 'added_at')
    readonly_fields = ('preview', 'added_at')
    ordering = ('display_order',)

    @admin.display(description='Preview')
    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:60px;width:60px;object-fit:cover;border-radius:6px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return '—'


class FeedbackImageInline(admin.TabularInline):
    model = FeedbackImage
    extra = 0
    fields = ('preview', 'image', 'added_at')
    readonly_fields = ('preview', 'added_at')

    @admin.display(description='Preview')
    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:60px;width:60px;object-fit:cover;border-radius:6px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return '—'


class PersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'campus', 'hostel', 'phone', 'is_subscribed', 'registered_at')
    list_display_links = ('id', 'name')
    list_editable = ('is_subscribed',)
    list_filter = ('campus', 'is_subscribed', 'hostel')
    search_fields = ('name', 'email', 'phone')
    readonly_fields = ('registered_at', 'last_notification')
    date_hierarchy = 'registered_at'
    autocomplete_fields = ('hostel',)
    ordering = ('-registered_at',)
    actions = ('mark_subscribed', 'mark_unsubscribed')
    fieldsets = (
        ('Identity', {'fields': ('name', 'email', 'avatar')}),
        ('Location', {'fields': ('campus', 'hostel')}),
        ('Contact', {'fields': ('phone',)}),
        ('Notifications', {'fields': ('is_subscribed', 'last_notification')}),
        ('Timestamps', {'fields': ('registered_at',)}),
    )

    @admin.action(description='Mark selected as subscribed')
    def mark_subscribed(self, request, queryset):
        updated = queryset.update(is_subscribed=True)
        self.message_user(request, f"{updated} person(s) subscribed.")

    @admin.action(description='Mark selected as unsubscribed')
    def mark_unsubscribed(self, request, queryset):
        updated = queryset.update(is_subscribed=False)
        self.message_user(request, f"{updated} person(s) unsubscribed.")


class HostelAdmin(admin.ModelAdmin):
    list_display = ('name', 'campus', 'resident_count')
    list_filter = ('campus',)
    search_fields = ('name',)
    ordering = ('campus', 'name')

    @admin.display(description='Residents')
    def resident_count(self, obj):
        return obj.residents.count()


class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'item_count', 'icon_class', 'added_at')
    list_display_links = ('id', 'name')
    search_fields = ('name',)
    readonly_fields = ('added_at',)
    ordering = ('-item_count', 'name')
    actions = ('recompute_item_count',)

    @admin.action(description='Recompute item count from live data')
    def recompute_item_count(self, request, queryset):
        total = 0
        for cat in queryset:
            actual = Item.objects.filter(category=cat, is_deleted=False).count()
            Category.objects.filter(pk=cat.pk).update(item_count=actual)
            total += 1
        self.message_user(request, f"Recomputed item_count for {total} categor(ies).")


class ItemAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'name', 'price', 'seller', 'category', 'hostel',
        'is_sold', 'is_deleted', 'reaction_count', 'updated_at',
    )
    list_display_links = ('id', 'name')
    list_editable = ('is_sold',)
    list_filter = ('is_sold', 'is_deleted', 'category', 'seller__campus', 'hostel', 'added_at')
    search_fields = ('id', 'name', 'description', 'phone', 'seller__email', 'seller__name')
    readonly_fields = ('added_at', 'updated_at', 'whatsapp')
    date_hierarchy = 'added_at'
    autocomplete_fields = ('seller', 'hostel', 'category')
    ordering = ('-updated_at',)
    inlines = (ImageInline,)
    actions = ('mark_sold', 'mark_unsold', 'soft_delete', 'restore', 'repost_items')
    fieldsets = (
        ('Listing', {'fields': ('name', 'description', 'category')}),
        ('Pricing', {'fields': ('price',)}),
        ('Seller & Contact', {'fields': ('seller', 'hostel', 'phone', 'whatsapp')}),
        ('Status', {'fields': ('is_sold', 'is_deleted')}),
        ('Timestamps', {'fields': ('added_at', 'updated_at')}),
    )

    def get_queryset(self, request):
        from django.db.models import Count
        return super().get_queryset(request).annotate(_reaction_count=Count('reactions'))

    @admin.display(description='Reactions', ordering='_reaction_count')
    def reaction_count(self, obj):
        return getattr(obj, '_reaction_count', 0)

    @admin.action(description='Mark selected as sold')
    def mark_sold(self, request, queryset):
        updated = queryset.update(is_sold=True)
        self.message_user(request, f"{updated} item(s) marked sold.")

    @admin.action(description='Mark selected as unsold')
    def mark_unsold(self, request, queryset):
        updated = queryset.update(is_sold=False)
        self.message_user(request, f"{updated} item(s) marked unsold.")

    @admin.action(description='Soft delete (hide from marketplace)')
    def soft_delete(self, request, queryset):
        updated = queryset.update(is_deleted=True)
        self.message_user(request, f"{updated} item(s) hidden.")

    @admin.action(description='Restore (unhide)')
    def restore(self, request, queryset):
        updated = queryset.update(is_deleted=False)
        self.message_user(request, f"{updated} item(s) restored.")

    @admin.action(description='Repost (bump updated_at to now, mark unsold)')
    def repost_items(self, request, queryset):
        from django.db.models import F
        updated = queryset.update(
            updated_at=timezone.now(),
            is_sold=False,
            repost_count=F('repost_count') + 1,
        )
        self.message_user(request, f"{updated} item(s) reposted.")


class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'preview', 'item', 'display_order', 'added_at')
    list_display_links = ('id', 'preview')
    list_filter = ('item__category', 'added_at')
    search_fields = ('item__name',)
    readonly_fields = ('preview', 'added_at')
    autocomplete_fields = ('item',)
    ordering = ('-added_at',)

    @admin.display(description='Preview')
    def preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:6px;border:1px solid #ddd;" />',
                obj.image.url,
            )
        return '—'


class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'person', 'message_preview', 'added_at')
    list_display_links = ('id', 'message_preview')
    list_filter = ('added_at',)
    search_fields = ('message', 'person__name', 'person__email')
    readonly_fields = ('added_at',)
    date_hierarchy = 'added_at'
    autocomplete_fields = ('person',)
    ordering = ('-added_at',)
    inlines = (FeedbackImageInline,)

    @admin.display(description='Message')
    def message_preview(self, obj):
        msg = (obj.message or '').strip().replace('\n', ' ')
        return (msg[:80] + '…') if len(msg) > 80 else (msg or '—')


class ReactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'person', 'reaction_type', 'created_at')
    list_filter = ('reaction_type', 'created_at')
    search_fields = ('item__name', 'person__email', 'person__name')
    readonly_fields = ('created_at',)
    date_hierarchy = 'created_at'
    autocomplete_fields = ('item', 'person')
    ordering = ('-created_at',)


class PageViewAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'status', 'method', 'path', 'email', 'campus', 'device', 'ip')
    list_filter = ('method', 'status', 'campus', 'device')
    search_fields = ('path', 'email', 'name', 'ip')
    readonly_fields = tuple(f.name for f in PageView._meta.fields)
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)

    def has_add_permission(self, request):
        return False


class LogIngestStateAdmin(admin.ModelAdmin):
    list_display = ('filename', 'signature', 'byte_offset', 'last_ingested')
    readonly_fields = ('signature', 'filename', 'byte_offset', 'last_ingested')
    ordering = ('-last_ingested',)

    def has_add_permission(self, request):
        return False


swd_admin_site.register(Person, PersonAdmin)
swd_admin_site.register(Hostel, HostelAdmin)
swd_admin_site.register(Category, CategoryAdmin)
swd_admin_site.register(Item, ItemAdmin)
swd_admin_site.register(Image, ImageAdmin)
swd_admin_site.register(Feedback, FeedbackAdmin)
swd_admin_site.register(Reaction, ReactionAdmin)
swd_admin_site.register(PageView, PageViewAdmin)
swd_admin_site.register(LogIngestState, LogIngestStateAdmin)
swd_admin_site.register(User, UserAdmin)
swd_admin_site.register(Group, GroupAdmin)
