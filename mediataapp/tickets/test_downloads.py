from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.test import TransactionTestCase, override_settings
from rolepermissions.roles import assign_role

from core.models import Empresa
from usuarios.models import UsuarioEmpresa
from .models import Anexo, Pagamentos, Recebimentos, Ticket


@override_settings(LOGIN_URL='/accounts/login/', DEBUG=False)
class PrivateTicketDownloadsTests(TransactionTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Empresa.objects.create(
            nome_fantasia='Empresa fictícia A', razao_social='Empresa fictícia A LTDA',
            cnpj='10.000.000/0001-01',
        )
        cls.other_company = Empresa.objects.create(
            nome_fantasia='Empresa fictícia B', razao_social='Empresa fictícia B LTDA',
            cnpj='20.000.000/0001-02',
        )
        cls.manager = User.objects.create_user(username='private-manager-fixture')
        assign_role(cls.manager, 'gerente')
        UsuarioEmpresa.objects.create(usuario=cls.manager, empresa=cls.company)
        cls.other_manager = User.objects.create_user(username='private-foreign-fixture')
        assign_role(cls.other_manager, 'operador')
        UsuarioEmpresa.objects.create(usuario=cls.other_manager, empresa=cls.other_company)
        cls.subscriber = User.objects.create_user(username='private-subscriber-fixture')
        assign_role(cls.subscriber, 'assinante')
        cls.reader = User.objects.create_user(username='private-reader-fixture')
        assign_role(cls.reader, 'colaborador')
        UsuarioEmpresa.objects.create(usuario=cls.reader, empresa=cls.company)
        cls.unlinked = User.objects.create_user(username='private-unlinked-fixture')
        assign_role(cls.unlinked, 'operador')
        cls.superuser = User.objects.create_superuser(
            username='private-super-fixture', email='fixture@example.invalid', password='fixture-only',
        )
        cls.ticket = Ticket.objects.create(
            ticket='PRIVADO001', usuario=cls.subscriber, empresa=cls.company,
            descricao='Solicitação fictícia', nfe_path='nfe/documento-a.pdf',
        )
        cls.foreign_ticket = Ticket.objects.create(
            ticket='PRIVADO002', usuario=cls.other_manager,
            descricao='Solicitação de outra empresa', nfe_path='nfe/documento-b.pdf',
        )
        Pagamentos.objects.create(
            ticket_pagamento=cls.ticket, tipo='M', data_pagamento='2026-01-01',
            comprovante='comprovantes/pagamento-a.png',
        )
        Recebimentos.objects.create(
            ticket_recebimento=cls.ticket,
            comprovante_recebimento='comprovantes/recebimento-a.pdf',
        )
        Anexo.objects.create(ticket_anexo=cls.ticket, arquivo='anexos/anexo-a.pdf')
        Anexo.objects.create(ticket_anexo=cls.foreign_ticket, arquivo='anexos/anexo-b.pdf')

    def setUp(self):
        self.setUpTestData()
        self.directory = TemporaryDirectory(prefix='mediata-private-downloads-')
        self.addCleanup(self.directory.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.payload = b'%PDF-1.4\nArquivo ficticio para teste de isolamento.\n'
        for relative in (
            'nfe/documento-a.pdf', 'nfe/documento-b.pdf',
            'comprovantes/pagamento-a.png', 'comprovantes/recebimento-a.pdf',
            'anexos/anexo-a.pdf', 'anexos/anexo-b.pdf',
        ):
            self.write_file(relative)

    def write_file(self, relative, payload=None):
        path = Path(self.directory.name) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.payload if payload is None else payload)
        return path

    def test_anonymous_cannot_read_private_document(self):
        response = self.client.get('/media/nfe/documento-a.pdf')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_operational_user_can_read_only_files_linked_to_own_company(self):
        self.client.force_login(self.manager)
        for relative in (
            'nfe/documento-a.pdf', 'comprovantes/pagamento-a.png',
            'comprovantes/recebimento-a.pdf', 'anexos/anexo-a.pdf',
        ):
            with self.subTest(path=relative):
                response = self.client.get('/media/' + relative)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), self.payload)
                self.assertEqual(response['Cache-Control'], 'private, no-store')
                self.assertIn('Cookie', response['Vary'])
                self.assertEqual(response['X-Content-Type-Options'], 'nosniff')
                response.close()

    def test_known_foreign_paths_remain_private(self):
        self.client.force_login(self.manager)
        for relative in ('nfe/documento-b.pdf', 'anexos/anexo-b.pdf'):
            with self.subTest(path=relative):
                response = self.client.get('/media/' + relative)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(self.payload, response.content)

    def test_superuser_can_read_files_from_both_companies(self):
        self.client.force_login(self.superuser)
        for relative in ('nfe/documento-a.pdf', 'nfe/documento-b.pdf', 'anexos/anexo-b.pdf'):
            with self.subTest(path=relative):
                response = self.client.get('/media/' + relative)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(b''.join(response.streaming_content), self.payload)
                response.close()

    def test_readonly_subscriber_and_unlinked_users_cannot_read_financial_files(self):
        for user in (self.subscriber, self.reader, self.unlinked):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get('/media/nfe/documento-a.pdf')
                self.assertEqual(response.status_code, 403)

    def test_inactive_company_cannot_read_private_files(self):
        Empresa.objects.filter(pk=self.company.pk).update(ativo=False)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get('/media/nfe/documento-a.pdf').status_code, 403)

    def test_head_is_supported_and_mutating_methods_are_rejected(self):
        self.client.force_login(self.manager)
        response = self.client.head('/media/nfe/documento-a.pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Length'], str(len(self.payload)))
        self.assertEqual(b''.join(response.streaming_content), b'')
        response.close()
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                self.assertEqual(getattr(self.client, method)('/media/nfe/documento-a.pdf').status_code, 405)

    def test_orphan_and_missing_files_return_generic_not_found(self):
        self.client.force_login(self.manager)
        self.write_file('anexos/orfao.pdf')
        Anexo.objects.create(ticket_anexo=self.ticket, arquivo='anexos/ausente.pdf')
        for relative in ('anexos/orfao.pdf', 'anexos/ausente.pdf'):
            with self.subTest(path=relative):
                response = self.client.get('/media/' + relative)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(self.directory.name.encode(), response.content)

    def test_parent_traversal_and_backslashes_are_rejected(self):
        self.client.force_login(self.manager)
        for relative in ('nfe/../anexos/anexo-a.pdf', 'nfe/./documento-a.pdf', 'nfe//documento-a.pdf', r'nfe/..\anexos\anexo-a.pdf'):
            with self.subTest(path=relative):
                response = self.client.get('/media/' + relative)
                self.assertEqual(response.status_code, 404)

    def test_symlink_cannot_escape_media_root(self):
        self.client.force_login(self.manager)
        with TemporaryDirectory(prefix='mediata-private-outside-') as outside:
            target = Path(outside) / 'externo.pdf'
            target.write_bytes(self.payload)
            (Path(self.directory.name) / 'anexos' / 'link.pdf').symlink_to(target)
            Anexo.objects.create(ticket_anexo=self.ticket, arquivo='anexos/link.pdf')
            response = self.client.get('/media/anexos/link.pdf')
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(outside.encode(), response.content)

    def test_active_attachment_is_downloaded_instead_of_rendered_inline(self):
        self.client.force_login(self.manager)
        self.write_file('anexos/ativo.html', b'<script>fixture</script>')
        Anexo.objects.create(ticket_anexo=self.ticket, arquivo='anexos/ativo.html')
        response = self.client.get('/media/anexos/ativo.html')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
        response.close()
