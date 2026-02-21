from django.contrib import admin
from .models import Campus, Person, Hostel, Category, Item, Image, Feedback, FeedbackImage


@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'email', 'campus', 'hostel', 'phone', 'registered_at')
    search_fields = ('name', 'email')
    list_filter = ('campus',)


@admin.register(Hostel)
class HostelAdmin(admin.ModelAdmin):
    list_display = ('name', 'campus')
    list_filter = ('campus',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'item_count', 'icon_class', 'added_at')


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'price', 'seller', 'category', 'hostel', 'is_sold', 'updated_at')
    list_filter = ('is_sold', 'category', 'seller__campus')
    search_fields = ('name', 'seller__email', 'seller__name')
    raw_id_fields = ('seller', 'hostel', 'category')


@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'display_order', 'added_at')
    raw_id_fields = ('item',)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'person', 'added_at')
    raw_id_fields = ('person',)


@admin.register(FeedbackImage)
class FeedbackImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'feedback', 'added_at')
    raw_id_fields = ('feedback',)
