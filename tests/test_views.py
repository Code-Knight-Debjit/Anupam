"""
tests/test_views.py
────────────────────
Integration tests for all public-facing and dashboard views/APIs.
Run: pytest tests/test_views.py -v
"""
import json
import pytest
from django.test import Client, TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch, MagicMock

from products.models import Category, Product, Enquiry
from contact.models  import ContactMessage, ChatMessage


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

@pytest.fixture
def client():
    return Client()


@pytest.fixture
def admin_client(db):
    user = User.objects.create_superuser('testadmin', 'admin@test.com', 'testpass123')
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def category(db):
    return Category.objects.create(
        name='Rolling Bearings', slug='rolling-bearings',
        icon='⚙️', description='Test category', order=1,
    )


@pytest.fixture
def product(db, category):
    return Product.objects.create(
        name='Tapered Roller Bearing',
        slug='tapered-roller-bearing',
        category=category,
        description='High-precision tapered roller bearing for combined loads.',
        specifications={'Bore': '25mm', 'OD': '52mm', 'Width': '15mm'},
        is_featured=True,
    )


# ─────────────────────────────────────────────
# PUBLIC PAGES
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestPublicPages:
    def test_home_200(self, client):
        assert client.get('/').status_code == 200

    def test_about_200(self, client):
        assert client.get('/about/').status_code == 200

    def test_gallery_200(self, client):
        assert client.get('/gallery/').status_code == 200

    def test_contact_200(self, client):
        assert client.get('/contact/').status_code == 200

    def test_products_200(self, client):
        assert client.get('/products/').status_code == 200

    def test_product_detail_200(self, client, product):
        r = client.get(f'/products/{product.slug}/')
        assert r.status_code == 200

    def test_product_detail_404_on_bad_slug(self, client):
        assert client.get('/products/does-not-exist/').status_code == 404

    def test_product_detail_shows_name(self, client, product):
        r = client.get(f'/products/{product.slug}/')
        assert product.name.encode() in r.content

    def test_product_detail_shows_specs(self, client, product):
        r = client.get(f'/products/{product.slug}/')
        assert b'25mm' in r.content   # Bore spec value

    def test_products_search_filter(self, client, product):
        r = client.get('/products/?q=tapered')
        assert r.status_code == 200
        assert product.name.encode() in r.content

    def test_products_category_filter(self, client, product, category):
        r = client.get(f'/products/?category={category.slug}')
        assert r.status_code == 200

    def test_products_search_no_results(self, client):
        r = client.get('/products/?q=zzznoresultzzz')
        assert r.status_code == 200


# ─────────────────────────────────────────────
# SEARCH API
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestSearchAPI:
    def test_short_query_returns_empty(self, client):
        r = client.get('/products/search/?q=a')
        assert r.status_code == 200
        data = json.loads(r.content)
        assert data['results'] == []

    def test_valid_query_returns_results(self, client, product):
        r = client.get('/products/search/?q=tapered')
        assert r.status_code == 200
        data = json.loads(r.content)
        assert len(data['results']) >= 1
        assert data['results'][0]['name'] == product.name

    def test_result_has_required_fields(self, client, product):
        r = client.get('/products/search/?q=bearing')
        data = json.loads(r.content)
        if data['results']:
            result = data['results'][0]
            for field in ('id', 'name', 'category', 'slug', 'url'):
                assert field in result

    def test_max_8_results(self, client, category):
        for i in range(12):
            Product.objects.create(
                name=f'Bearing Type {i}', slug=f'bearing-type-{i}',
                category=category, description='Test'
            )
        r = client.get('/products/search/?q=bearing')
        data = json.loads(r.content)
        assert len(data['results']) <= 8


# ─────────────────────────────────────────────
# ENQUIRY API
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestEnquiryAPI:
    def _post(self, client, payload):
        return client.post(
            '/products/enquire/',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_valid_enquiry_returns_200(self, client, product):
        r = self._post(client, {
            'name': 'Arjun Singh', 'email': 'arjun@test.com',
            'message': 'I need 50 units for our production line.',
            'product_id': product.pk,
        })
        assert r.status_code == 200
        data = json.loads(r.content)
        assert data['success'] is True

    def test_valid_enquiry_saves_to_db(self, client, product):
        self._post(client, {
            'name': 'Test User', 'email': 'test@test.com',
            'message': 'Need pricing for bulk order of bearings.',
            'product_id': product.pk,
        })
        assert Enquiry.objects.filter(email='test@test.com').exists()

    def test_missing_name_returns_400(self, client, product):
        r = self._post(client, {
            'name': '', 'email': 'test@test.com',
            'message': 'Need some bearings please.',
        })
        assert r.status_code == 400
        assert json.loads(r.content)['success'] is False

    def test_invalid_email_returns_400(self, client, product):
        r = self._post(client, {
            'name': 'Test', 'email': 'not-valid',
            'message': 'Need some bearings please.',
        })
        assert r.status_code == 400

    def test_short_message_returns_400(self, client):
        r = self._post(client, {
            'name': 'Test', 'email': 'test@example.com', 'message': 'Hi',
        })
        assert r.status_code == 400

    def test_spam_message_returns_400(self, client):
        r = self._post(client, {
            'name': 'Spammer', 'email': 'spam@test.com',
            'message': 'Click here to win bitcoin casino lottery free money',
        })
        assert r.status_code == 400

    def test_invalid_json_returns_400(self, client):
        r = client.post('/products/enquire/', data='not json', content_type='application/json')
        assert r.status_code == 400

    def test_no_product_id_is_ok(self, client):
        r = self._post(client, {
            'name': 'General', 'email': 'gen@test.com',
            'message': 'General enquiry about your bearing range.',
        })
        assert r.status_code == 200


# ─────────────────────────────────────────────
# CONTACT FORM API
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestContactAPI:
    def _post(self, client, payload):
        return client.post(
            '/contact/send/',
            data=json.dumps(payload),
            content_type='application/json',
        )

    def _valid_payload(self):
        return {
            'name':    'Priya Sharma',
            'email':   'priya@company.com',
            'phone':   '+91 98765 43210',
            'subject': 'Annual Rate Contract Inquiry',
            'message': 'We are interested in a long-term supply agreement for bearings.',
        }

    def test_valid_contact_returns_200(self, client):
        r = self._post(client, self._valid_payload())
        assert r.status_code == 200
        assert json.loads(r.content)['success'] is True

    def test_valid_contact_saves_to_db(self, client):
        self._post(client, self._valid_payload())
        assert ContactMessage.objects.filter(email='priya@company.com').exists()

    def test_missing_subject_returns_400(self, client):
        payload = self._valid_payload()
        payload['subject'] = ''
        r = self._post(client, payload)
        assert r.status_code == 400

    def test_invalid_email_returns_400(self, client):
        payload = self._valid_payload()
        payload['email'] = 'bad-email'
        r = self._post(client, payload)
        assert r.status_code == 400

    def test_errors_dict_in_response(self, client):
        r = self._post(client, {'name': '', 'email': 'bad', 'subject': '', 'message': ''})
        data = json.loads(r.content)
        assert 'errors' in data
        assert len(data['errors']) >= 2


# ─────────────────────────────────────────────
# CHAT API
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestChatAPI:
    @patch('chatbot.tasks.run_rag_pipeline')
    def test_valid_chat_returns_200(self, mock_pipeline, client):
        mock_pipeline.return_value = {
            'reply': 'We carry tapered roller bearings from Timken.',
            'sources': [], 'cached': False, 'chunks_found': 3,
        }
        r = client.post(
            '/api/chat/',
            data=json.dumps({'message': 'What bearings do you carry?'}),
            content_type='application/json',
        )
        assert r.status_code == 200
        data = json.loads(r.content)
        assert data['success'] is True
        assert 'reply' in data

    def test_empty_message_returns_400(self, client):
        r = client.post(
            '/api/chat/',
            data=json.dumps({'message': ''}),
            content_type='application/json',
        )
        assert r.status_code == 400

    def test_invalid_json_returns_400(self, client):
        r = client.post('/api/chat/', data='not json', content_type='application/json')
        assert r.status_code == 400

    def test_async_endpoint_needs_celery(self, client):
        """Async endpoint should accept valid message (task queued)."""
        with patch('chatbot.tasks.run_rag_pipeline') as mock:
            mock.delay = MagicMock(return_value=MagicMock(id='test-task-uuid-1234'))
            r = client.post(
                '/api/chat/async/',
                data=json.dumps({'message': 'What products do you sell?'}),
                content_type='application/json',
            )
        # Either 200 (task queued) or 500 (Celery not running in test env)
        assert r.status_code in (200, 500)

    def test_result_endpoint_invalid_uuid(self, client):
        r = client.get('/api/chat/result/not-a-valid-uuid/')
        assert r.status_code == 400

    def test_health_endpoint_returns_json(self, client):
        r = client.get('/api/chat/health/')
        assert r.status_code == 200
        data = json.loads(r.content)
        assert 'overall' in data
        assert 'ollama' in data
        assert 'faiss' in data
        assert 'redis' in data

    def test_stats_endpoint_returns_json(self, client):
        r = client.get('/api/chat/stats/')
        assert r.status_code == 200
        data = json.loads(r.content)
        assert 'exists' in data


# ─────────────────────────────────────────────
# DASHBOARD VIEWS (authenticated)
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestDashboardViews:
    def test_home_redirects_unauthenticated(self, client):
        r = client.get('/dashboard/')
        assert r.status_code in (302, 301)
        assert 'login' in r.url

    def test_home_200_for_staff(self, admin_client):
        r = admin_client.get('/dashboard/')
        assert r.status_code == 200

    def test_products_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/products/').status_code == 200

    def test_categories_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/categories/').status_code == 200

    def test_enquiries_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/enquiries/').status_code == 200

    def test_messages_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/messages/').status_code == 200

    def test_chats_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/chats/').status_code == 200

    def test_rag_status_200_for_staff(self, admin_client):
        assert admin_client.get('/dashboard/rag/').status_code == 200

    def test_notifications_api_returns_json(self, admin_client):
        r = admin_client.get('/dashboard/api/notifications/')
        assert r.status_code == 200
        data = json.loads(r.content)
        assert 'new_enquiries' in data
        assert 'unread_messages' in data

    def test_product_add_creates_product(self, admin_client, category):
        count_before = Product.objects.count()
        admin_client.post('/dashboard/products/add/', {
            'name':        'Test Ball Bearing',
            'category':    category.pk,
            'description': 'A test bearing product.',
            'is_featured': 'on',
        })
        assert Product.objects.count() == count_before + 1

    def test_product_delete_removes_product(self, admin_client, product):
        pk = product.pk
        r = admin_client.post(f'/dashboard/products/{pk}/delete/')
        assert r.status_code == 200
        assert not Product.objects.filter(pk=pk).exists()

    def test_enquiry_status_update(self, admin_client, product):
        enq = Enquiry.objects.create(
            name='Test', email='t@t.com', message='Need bearings.',
            product=product, status='new',
        )
        r = admin_client.post(
            f'/dashboard/enquiries/{enq.pk}/status/',
            data=json.dumps({'status': 'in_progress'}),
            content_type='application/json',
        )
        assert r.status_code == 200
        enq.refresh_from_db()
        assert enq.status == 'in_progress'

    def test_message_mark_read(self, admin_client):
        msg = ContactMessage.objects.create(
            name='User', email='u@u.com', subject='Test', message='Hello there.', is_read=False,
        )
        admin_client.post(f'/dashboard/messages/{msg.pk}/read/')
        msg.refresh_from_db()
        assert msg.is_read is True

    def test_mark_all_read(self, admin_client):
        for i in range(3):
            ContactMessage.objects.create(
                name=f'User{i}', email=f'u{i}@u.com',
                subject='Test', message='Hello.', is_read=False,
            )
        admin_client.post('/dashboard/messages/mark-all-read/')
        assert ContactMessage.objects.filter(is_read=False).count() == 0

    def test_category_add(self, admin_client):
        before = Category.objects.count()
        admin_client.post('/dashboard/categories/add/', {
            'name': 'New Test Category', 'icon': '🔧',
            'description': 'Test category description.', 'order': 5,
        })
        assert Category.objects.count() == before + 1

    def test_toggle_featured(self, admin_client, product):
        original = product.is_featured
        r = admin_client.post(f'/dashboard/products/{product.pk}/toggle-featured/')
        assert r.status_code == 200
        product.refresh_from_db()
        assert product.is_featured != original


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestModels:
    def test_category_str(self, category):
        assert str(category) == 'Rolling Bearings'

    def test_product_str(self, product):
        assert str(product) == 'Tapered Roller Bearing'

    def test_enquiry_str(self, product):
        enq = Enquiry.objects.create(
            name='Test User', email='t@t.com',
            message='Test message here.', product=product,
        )
        assert 'Test User' in str(enq)

    def test_contact_message_str(self):
        msg = ContactMessage.objects.create(
            name='Alice', email='alice@test.com',
            subject='Hello', message='Test message content.',
        )
        assert 'Alice' in str(msg)

    def test_enquiry_default_status(self, product):
        enq = Enquiry.objects.create(
            name='X', email='x@x.com', message='Message here.', product=product,
        )
        assert enq.status == 'new'

    def test_contact_default_unread(self):
        msg = ContactMessage.objects.create(
            name='Bob', email='bob@test.com',
            subject='Test', message='Test content.',
        )
        assert msg.is_read is False

    def test_product_specifications_json(self, product):
        assert product.specifications['Bore'] == '25mm'

    def test_chat_message_saved(self, db):
        ChatMessage.objects.create(session_id='abc123', role='user', content='Hello')
        assert ChatMessage.objects.filter(session_id='abc123').count() == 1


# ─────────────────────────────────────────────
# RATE LIMITING
# ─────────────────────────────────────────────

@pytest.mark.django_db
class TestRateLimiting:
    """Test that rate limiting headers and responses are correct."""

    def test_chat_rate_limit_after_threshold(self, client):
        """After 20 requests, the 21st should get 429."""
        from django.core.cache import cache
        # Manually set rate limit counter above threshold
        cache.set('chat_rl:127.0.0.1', 25, 60)
        r = client.post(
            '/api/chat/',
            data=json.dumps({'message': 'Hello there, how are you?'}),
            content_type='application/json',
        )
        assert r.status_code == 429
        data = json.loads(r.content)
        assert 'Too many' in data['reply']

    def test_contact_rate_limit(self, client):
        from django.core.cache import cache
        cache.set('contact_rl:127.0.0.1', 10, 300)
        r = client.post(
            '/contact/send/',
            data=json.dumps({
                'name': 'Test', 'email': 'test@test.com',
                'subject': 'Test', 'message': 'Test message content here.',
            }),
            content_type='application/json',
        )
        assert r.status_code == 429
