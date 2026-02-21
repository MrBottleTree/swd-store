from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('sign-in', views.sign_in, name='sign_in'),
    path('auth-receiver', views.auth_receiver, name='auth_receiver'),
    path('sign-out', views.sign_out, name='sign_out'),
    path('item/<int:id>', views.item_detail, name='item_detail'),
    path('add-product', views.add_product, name='add_product'),
    path('edit-item/<int:id>', views.edit_item, name='edit_item'),
    path('delete-item/<int:id>', views.delete_item, name='delete_item'),
    path('my-listings/', views.my_listings, name='my_listings'),
    path('mark-sold/<int:id>', views.mark_sold, name='mark_sold'),
    path('repost/<int:id>', views.repost, name='repost'),
    path('bulk-action/<str:action>', views.bulk_action, name='bulk_action'),
    path('feedback', views.feedback, name='feedback'),
    path('about', views.about, name='about'),
    path('terms', views.terms, name='terms'),
    path('categories', views.categories, name='categories'),
    path('debug-sign-in', views.debug_sign_in, name='debug_sign_in'),
    path('react/<int:item_id>/', views.react_item, name='react_item'),
]
