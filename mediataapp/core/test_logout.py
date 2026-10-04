from django.conf import settings
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse


class LogoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='logout_test')

    def authenticated_client(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        return client

    def test_sidebar_submits_logout_with_csrf_and_accessible_button(self):
        client = self.authenticated_client()
        response = client.get(reverse('empresa_success'))

        self.assertContains(response, '<form method="post" action="/logout/">')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'type="submit" class="nav-link text-danger"')
        self.assertContains(response, 'aria-label="Sair do sistema"')

    def test_post_flushes_session_redirects_to_login_and_blocks_dashboard(self):
        for url in (reverse('logout'), '/accounts/logout/'):
            with self.subTest(url=url):
                client = self.authenticated_client()
                session = client.session
                session['draft'] = 'temporary-session-data'
                session.save()
                previous_session_key = session.session_key
                client.get(reverse('empresa_success'))

                response = client.post(
                    url,
                    {'csrfmiddlewaretoken': client.cookies[settings.CSRF_COOKIE_NAME].value},
                    follow=True,
                )

                self.assertRedirects(response, reverse('login'))
                self.assertFalse(response.context['user'].is_authenticated)
                self.assertNotIn(SESSION_KEY, client.session)
                self.assertNotIn('draft', client.session)
                self.assertFalse(Session.objects.filter(session_key=previous_session_key).exists())
                self.assertRedirects(
                    client.get(reverse('dashboard')),
                    f"{reverse('login')}?next={reverse('dashboard')}",
                )

    def test_get_does_not_log_out_the_user(self):
        client = self.authenticated_client()
        response = client.get(reverse('logout'))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))

    def test_post_without_csrf_does_not_log_out_the_user(self):
        client = self.authenticated_client()
        response = client.post(reverse('logout'))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(client.session[SESSION_KEY], str(self.user.pk))

    def test_post_with_an_expired_session_returns_to_login(self):
        client = Client(enforce_csrf_checks=True)
        client.get(reverse('login'))
        response = client.post(
            reverse('logout'),
            {'csrfmiddlewaretoken': client.cookies[settings.CSRF_COOKIE_NAME].value},
            follow=True,
        )

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(response.context['user'].is_authenticated)
