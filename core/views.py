import json
import os
import secrets
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Q, Count
from django.conf import settings
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django_ratelimit.decorators import ratelimit

from .models import Person, Item, Image, Category, Hostel, Feedback, FeedbackImage, Campus, Reaction
from .forms import ItemForm, FeedbackForm
from . import helper

def _get_current_user(request):
    """Return Person if session has valid user_data, else None."""
    user_data = request.session.get('user_data')
    if not user_data:
        return None
    return Person.objects.filter(email=user_data['email']).first()


def _login_required(view_fn):
    """Simple decorator that redirects to sign-in if user is not authenticated."""
    from functools import wraps
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not _get_current_user(request):
            return redirect('core:sign_in')
        return view_fn(request, *args, **kwargs)
    return wrapper

@ratelimit(key='ip', rate='20/m', block=False)
@csrf_exempt
def sign_in(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)
    if _get_current_user(request):
        return redirect('core:home')
    state = secrets.token_urlsafe(16)
    request.session['oauth_state'] = state
    redirect_uri = request.build_absolute_uri('/auth-receiver')
    google_auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urlencode({
        'client_id': settings.GOOGLE_OAUTH_CLIENT_ID or '',
        'redirect_uri': redirect_uri,
        'scope': 'openid email profile',
        'response_type': 'code',
        'state': state,
        'access_type': 'online',
    })
    return render(request, 'core/sign_in.html', {
        'google_client_id': settings.GOOGLE_OAUTH_CLIENT_ID or '',
        'login_uri': redirect_uri,
        'google_auth_url': google_auth_url,
        'debug': settings.DEBUG,
    })


def _complete_sign_in(request, user_data):
    request.session['user_data'] = user_data
    email = user_data['email']
    if not Person.objects.filter(email=email).exists():
        person = Person(email=email, name=user_data.get('name', ''))
        person.save()
    return redirect('core:home')


@ratelimit(key='ip', rate='20/m', block=False)
@csrf_exempt
def auth_receiver(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    # ── OAuth2 redirect callback (GET) ────────────────────────────────────────
    if request.method == 'GET':
        if request.GET.get('error'):
            messages.error(request, 'Sign-in was cancelled. Please try again.')
            return redirect('core:sign_in')
        code = request.GET.get('code')
        state = request.GET.get('state')
        session_state = request.session.get('oauth_state')
        if not code or not state or state != session_state:
            msg = (f'State mismatch (got {state!r}, expected {session_state!r})'
                   if settings.DEBUG else 'Sign-in failed. Please try again.')
            messages.error(request, msg)
            return redirect('core:sign_in')
        redirect_uri = request.build_absolute_uri('/auth-receiver')
        try:
            token_resp = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code': code,
                    'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
                    'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    'redirect_uri': redirect_uri,
                    'grant_type': 'authorization_code',
                },
                timeout=10,
            )
            token_json = token_resp.json()
            id_token_str = token_json.get('id_token')
            if not id_token_str:
                raise ValueError(
                    token_json.get('error_description') or token_json.get('error') or 'No id_token in response'
                )
            user_data = id_token.verify_oauth2_token(
                id_token_str,
                google_requests.Request(),
                settings.GOOGLE_OAUTH_CLIENT_ID,
                clock_skew_in_seconds=10,
            )
        except Exception as e:
            msg = f'Sign-in error: {e}' if settings.DEBUG else 'Sign-in failed. Please try again.'
            messages.error(request, msg)
            return redirect('core:sign_in')
        return _complete_sign_in(request, user_data)

    # ── Google One Tap credential (POST) ──────────────────────────────────────
    if request.method == 'POST':
        try:
            token = request.POST['credential']
            user_data = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_OAUTH_CLIENT_ID,
                clock_skew_in_seconds=10,
            )
        except Exception:
            messages.error(request, 'Sign-in failed. Please try again.')
            return redirect('core:sign_in')
        return _complete_sign_in(request, user_data)

    return redirect('core:sign_in')


@ratelimit(key='ip', rate='20/m', block=False)
def sign_out(request):
    request.session.pop('user_data', None)
    return redirect('core:sign_in')


@ratelimit(key='ip', rate='60/m', block=False)
def home(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    current_user = _get_current_user(request)
    if not current_user:
        return redirect('core:sign_in')

    category_id = request.GET.get('c')
    query = request.GET.get('q')
    sort_method = request.GET.get('sort', '0')
    selected_campus = request.GET.get('campus')

    items_query = Item.objects.select_related('seller', 'category', 'hostel').prefetch_related('images')

    # Campus filtering
    if selected_campus == 'ALL':
        campus_filter = None
    elif selected_campus in ['GOA', 'HYD', 'PIL', 'DUB']:
        items_query = items_query.filter(seller__campus=selected_campus)
        campus_filter = selected_campus
    else:
        # Default to user's campus
        if current_user.campus in ['GOA', 'HYD', 'PIL', 'DUB']:
            selected_campus = current_user.campus
            campus_filter = current_user.campus
            items_query = items_query.filter(seller__campus=current_user.campus)
        else:
            selected_campus = 'ALL'
            campus_filter = None

    if category_id:
        items_query = items_query.filter(category__id=category_id)

    if query:
        items_query = items_query.filter(
            Q(name__icontains=query) |
            Q(hostel__name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )

    # Category counts
    categories = Category.objects.all()
    categories_with_counts = []
    for cat in categories:
        cat_items = Item.objects.filter(category=cat)
        if campus_filter:
            cat_items = cat_items.filter(seller__campus=campus_filter)
        categories_with_counts.append({
            'id': cat.id,
            'name': cat.name,
            'icon_class': cat.icon_class,
            'item_count': cat_items.count(),
        })
    categories_with_counts.sort(key=lambda x: x['item_count'], reverse=True)

    items_query = items_query  # no reaction annotation needed
    items = helper.items_sort(items_query, sort_method)
    try:
        per_page = max(8, min(int(request.GET.get('per_page', '48')), 120))
    except (ValueError, TypeError):
        per_page = 48
    paginator = Paginator(items, per_page)
    page = request.GET.get('page')
    try:
        paginated_items = paginator.page(page)
    except PageNotAnInteger:
        paginated_items = paginator.page(1)
    except EmptyPage:
        paginated_items = paginator.page(paginator.num_pages)

    # Reaction data for this page's items (single DB query)
    page_item_ids = [item.id for item in paginated_items]
    rxns_raw = list(
        Reaction.objects.filter(item_id__in=page_item_ids)
        .order_by('item_id', '-created_at')
        .values_list('item_id', 'reaction_type', 'person_id')
    )
    from collections import defaultdict
    item_emojis = defaultdict(list)
    item_emojis_seen = defaultdict(set)
    item_total = defaultdict(int)
    user_item_emoji = {}
    for iid, emoji, person_id in rxns_raw:
        item_total[iid] += 1
        if emoji not in item_emojis_seen[iid] and len(item_emojis[iid]) < 3:
            item_emojis_seen[iid].add(emoji)
            item_emojis[iid].append(emoji)
        if person_id == current_user.id and iid not in user_item_emoji:
            user_item_emoji[iid] = emoji
    reaction_data = {
        str(iid): {
            'emojis': item_emojis.get(iid, []),
            'total': item_total.get(iid, 0),
            'mine': user_item_emoji.get(iid),
        }
        for iid in page_item_ids
    }
    reaction_data_json = json.dumps(reaction_data)

    campus_tabs = [
        ('GOA', 'Goa'),
        ('HYD', 'Hyderabad'),
        ('PIL', 'Pilani'),
        ('DUB', 'Dubai'),
        ('ALL', 'All Campuses'),
    ]
    return render(request, 'core/home.html', {
        'user': current_user,
        'items': paginated_items,
        'page_obj': paginated_items,
        'paginator': paginator,
        'selected_campus': selected_campus,
        'categories': categories,
        'categories_with_counts': categories_with_counts,
        'query': query or '',
        'sort_method': sort_method,
        'selected_category': category_id,
        'campus_tabs': campus_tabs,
        'reaction_data_json': reaction_data_json,
    })


@ratelimit(key='ip', rate='60/m', block=False)
def item_detail(request, id):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    current_user = _get_current_user(request)
    if not current_user:
        return redirect('core:sign_in')

    item = get_object_or_404(Item, id=id)
    similar_items = (
        Item.objects
        .filter(category=item.category)
        .exclude(id=item.id)
        .select_related('seller', 'hostel')
        .prefetch_related('images')
        .order_by('-updated_at')[:6]
    )

    # Reactions
    all_rxns = list(
        Reaction.objects.filter(item=item)
        .select_related('person')
        .order_by('-created_at')
    )
    my_emoji = None
    emoji_groups = {}
    for rxn in all_rxns:
        if rxn.person_id == current_user.id:
            my_emoji = rxn.reaction_type
        e = rxn.reaction_type
        if e not in emoji_groups:
            emoji_groups[e] = []
        emoji_groups[e].append(rxn.person.name)
    # Sort groups by count descending
    emoji_groups = dict(sorted(emoji_groups.items(), key=lambda x: len(x[1]), reverse=True))
    total_rxns = len(all_rxns)

    return render(request, 'core/item_detail.html', {
        'item': item,
        'similar_items': similar_items,
        'user': current_user,
        'all_item_rxns': all_rxns[:20],
        'total_rxns': total_rxns,
        'emoji_groups': emoji_groups,
        'my_emoji': my_emoji,
        'my_emoji_json': json.dumps(my_emoji),
    })


@ratelimit(key='ip', rate='10/m', block=False)
def add_product(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES, user=person)
        if form.is_valid():
            item = form.save(commit=False)
            item.seller = person

            whatsapp_number = form.cleaned_data.get('phone')
            hostel = form.cleaned_data.get('hostel')

            if whatsapp_number:
                person.phone = whatsapp_number
                person.save()
            if hostel:
                person.hostel = hostel
                person.save()

            item.hostel = person.hostel
            item.save()

            for idx, image_file in enumerate(request.FILES.getlist('images')[:5]):
                Image.objects.create(item=item, image=image_file, display_order=idx)

            messages.success(request, 'Product added successfully!')
            return redirect('core:my_listings')
        else:
            messages.error(request, 'Please correct the errors below.')
            return render(request, 'core/add_product.html', {'form': form})
    else:
        form = ItemForm(user=person)
        form.setdata(person.hostel, person.phone)
    return render(request, 'core/add_product.html', {'form': form, 'user': person})


@ratelimit(key='ip', rate='10/m', block=False)
def edit_item(request, id):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    item = get_object_or_404(Item, id=id)
    if item.seller != person:
        messages.error(request, 'You can only edit your own items.')
        return redirect('core:home')

    existing_images = [
        {'id': img.id, 'url': img.image.url, 'display_order': img.display_order}
        for img in item.images.all().order_by('display_order')
    ]
    existing_images_json = json.dumps(existing_images)

    if request.method == 'POST':
        form = ItemForm(request.POST, request.FILES, instance=item, user=person)
        if form.is_valid():
            updated_item = form.save(commit=False)

            whatsapp_number = form.cleaned_data.get('phone')
            hostel = form.cleaned_data.get('hostel')
            if whatsapp_number:
                person.phone = whatsapp_number
                person.save()
            if hostel:
                person.hostel = hostel
                person.save()

            updated_item.hostel = person.hostel
            updated_item.save()

            existing_ids = [
                int(x) for x in request.POST.get('existing_image_ids', '').split(',')
                if x.strip().isdigit()
            ]
            # Delete images removed by the user
            for img in item.images.all():
                if img.id not in existing_ids:
                    img.image.delete(save=False)
                    img.delete()
            # Reorder the kept images
            for idx, img_id in enumerate(existing_ids):
                try:
                    img = Image.objects.get(id=img_id, item=item)
                    img.display_order = idx
                    img.save()
                except Image.DoesNotExist:
                    pass
            # Append newly uploaded images
            next_order = len(existing_ids)
            for idx, image_file in enumerate(request.FILES.getlist('images')[:5 - next_order]):
                Image.objects.create(item=item, image=image_file, display_order=next_order + idx)

            messages.success(request, 'Item updated successfully!')
            return redirect('core:my_listings')
        else:
            return render(request, 'core/add_product.html', {
                'form': form,
                'item': item,
                'existing_images_json': existing_images_json,
                'user': person,
            })
    else:
        form = ItemForm(instance=item, user=person)
    return render(request, 'core/add_product.html', {
        'form': form,
        'item': item,
        'existing_images_json': existing_images_json,
        'user': person,
    })


@ratelimit(key='ip', rate='30/m', block=False)
def delete_item(request, id):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    item = get_object_or_404(Item, id=id)
    if item.seller == person:
        for image in item.images.all():
            image.image.delete(save=False)
            image.delete()
        item.delete()
    return redirect('core:my_listings')


@ratelimit(key='ip', rate='60/m', block=False)
def my_listings(request):
    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    listings = helper.items_sort(
        Item.objects.filter(seller=person).select_related('category', 'hostel').prefetch_related('images')
    )
    return render(request, 'core/my_listings.html', {'listings': listings, 'user': person})


@ratelimit(key='ip', rate='30/m', block=False)
def mark_sold(request, id):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    item = get_object_or_404(Item, id=id, seller=person)
    item.is_sold = True
    item.save()
    return redirect('core:my_listings')


@ratelimit(key='ip', rate='30/m', block=False)
def repost(request, id):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    item = get_object_or_404(Item, id=id)
    if item.seller != person:
        messages.error(request, 'You can only repost your own items.')
        return redirect('core:home')

    item.repost()
    messages.success(request, f"'{item.name}' has been reposted successfully!")
    source = request.GET.get('source')
    if source == 'home':
        return redirect('core:home')
    return redirect('core:my_listings')


@ratelimit(key='ip', rate='30/m', block=False)
@csrf_exempt
def bulk_action(request, action):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    if request.method != 'POST':
        return redirect('core:my_listings')

    selected_ids = request.POST.get('selected_items', '').split(',')
    items = Item.objects.filter(id__in=selected_ids, seller=person)

    if not items.exists():
        messages.error(request, 'No valid items were selected.')
        return redirect('core:my_listings')

    if action == 'repost':
        count = 0
        for item in items:
            item.is_sold = False
            item.hostel = person.hostel
            item.save()
            count += 1
        messages.success(request, f'Successfully reposted {count} item(s).')
    elif action == 'toggle_sold':
        count = 0
        for item in items:
            item.is_sold = not item.is_sold
            item.save(change_time=False)
            count += 1
        messages.success(request, f'Successfully toggled sold status for {count} item(s).')
    elif action == 'delete':
        count = 0
        for item in items:
            for image in item.images.all():
                image.image.delete(save=False)
                image.delete()
            item.delete()
            count += 1
        messages.success(request, f'Successfully deleted {count} item(s).')

    return redirect('core:my_listings')


@ratelimit(key='ip', rate='10/m', block=False)
def feedback(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)

    if request.method == 'POST':
        form = FeedbackForm(request.POST)
        if form.is_valid():
            fb = form.save(commit=False)
            fb.person = person
            fb.save()
            for image in request.FILES.getlist('images'):
                FeedbackImage.objects.create(feedback=fb, image=image)
            messages.success(request, 'Thank you for your feedback!')
            if person:
                return redirect('core:home')
            return redirect('core:feedback')
    else:
        form = FeedbackForm()

    return render(request, 'core/feedback.html', {'form': form, 'user': person})


@ratelimit(key='ip', rate='60/m', block=False)
def about(request):
    return render(request, 'core/about.html')


@ratelimit(key='ip', rate='60/m', block=False)
def terms(request):
    return render(request, 'core/terms.html')


@ratelimit(key='ip', rate='60/m', block=False)
def categories(request):
    if getattr(request, 'limited', False):
        return render(request, 'core/429.html', status=429)

    person = _get_current_user(request)
    if not person:
        return redirect('core:sign_in')

    categories = Category.objects.all()
    return render(request, 'core/categories.html', {'categories': categories, 'user': person})

def debug_sign_in(request):
    if not settings.DEBUG:
        from django.http import Http404
        raise Http404
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        name = request.POST.get('name', '').strip() or email.split('@')[0]
        if email:
            person, _ = Person.objects.get_or_create(
                email=email,
                defaults={'name': name},
            )
            if not person.name:
                person.name = name
                person.save()
            request.session['user_data'] = {'email': email, 'name': person.name}
            return redirect('core:home')
    return render(request, 'core/debug_sign_in.html')

@ratelimit(key='ip', rate='60/m', block=False)
def react_item(request, item_id):
    person = _get_current_user(request)
    if not person:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    item = get_object_or_404(Item, id=item_id)

    # GET: return reactor data without reacting
    if request.method == 'GET':
        all_rxns = list(
            Reaction.objects.filter(item=item)
            .select_related('person')
            .order_by('-created_at')
        )
        total = len(all_rxns)
        seen = set()
        recent_emojis = []
        for r in all_rxns:
            if r.reaction_type not in seen and len(recent_emojis) < 3:
                seen.add(r.reaction_type)
                recent_emojis.append(r.reaction_type)
        emoji_groups = {}
        for r in all_rxns:
            e = r.reaction_type
            if e not in emoji_groups:
                emoji_groups[e] = []
            emoji_groups[e].append(r.person.name)
        emoji_groups = dict(sorted(emoji_groups.items(), key=lambda x: len(x[1]), reverse=True))
        reactors = [
            {
                'name': r.person.name,
                'initial': (r.person.name[0].upper() if r.person.name else '?'),
                'emoji': r.reaction_type,
            }
            for r in all_rxns[:20]
        ]
        return JsonResponse({
            'total': total,
            'recent_emojis': recent_emojis,
            'emoji_groups': emoji_groups,
            'reactors': reactors,
        })

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    emoji = request.POST.get('emoji', '').strip()
    if not emoji:
        return JsonResponse({'error': 'No emoji provided'}, status=400)

    my_emoji = None
    try:
        existing = Reaction.objects.get(item=item, person=person)
        if existing.reaction_type == emoji:
            existing.delete()  # toggle off (same emoji = remove)
        else:
            existing.reaction_type = emoji  # replace with new emoji
            existing.save()
            my_emoji = emoji
    except Reaction.DoesNotExist:
        Reaction.objects.create(item=item, person=person, reaction_type=emoji)
        my_emoji = emoji

    # Build response
    all_rxns = list(
        Reaction.objects.filter(item=item)
        .select_related('person')
        .order_by('-created_at')
    )
    total = len(all_rxns)

    seen = set()
    recent_emojis = []
    for r in all_rxns:
        if r.reaction_type not in seen and len(recent_emojis) < 3:
            seen.add(r.reaction_type)
            recent_emojis.append(r.reaction_type)

    # Emoji groups with names (for detail page)
    emoji_groups = {}
    for r in all_rxns:
        e = r.reaction_type
        if e not in emoji_groups:
            emoji_groups[e] = []
        emoji_groups[e].append(r.person.name)
    emoji_groups = dict(sorted(emoji_groups.items(), key=lambda x: len(x[1]), reverse=True))

    # Reactors list (for detail page)
    reactors = [
        {
            'name': r.person.name,
            'initial': (r.person.name[0].upper() if r.person.name else '?'),
            'emoji': r.reaction_type,
        }
        for r in all_rxns[:20]
    ]

    return JsonResponse({
        'my_emoji': my_emoji,
        'recent_emojis': recent_emojis,
        'total': total,
        'emoji_groups': emoji_groups,
        'reactors': reactors,
    })

def page_not_found(request, exception):
    return render(request, 'core/404.html', status=404)


def server_error(request):
    return render(request, 'core/500.html', status=500)


def rate_limited(request, exception=None):
    return render(request, 'core/429.html', status=429)
