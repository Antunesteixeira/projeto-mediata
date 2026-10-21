"""Os formulários reais do ticket persistem o mesmo contrato do Financeiro."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from usuarios.test_helpers import criar_empresa, vincular_usuario

from .models import Pagamentos, Ticket


@override_settings(TIME_ZONE='America/Sao_Paulo')
class PagamentosFinanceiroIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('Empresa integração financeira', '00.000.000/0000-81')
        cls.operador = User.objects.create_user(username='operador_integracao_financeira')
        assign_role(cls.operador, 'operador')
        vincular_usuario(cls.operador, cls.empresa)
        cls.ticket = Ticket.objects.create(
            ticket='FININT001', usuario=cls.operador, empresa=cls.empresa,
            descricao='Ticket para criação e edição de despesas',
        )
        cls.outro_ticket = Ticket.objects.create(
            ticket='FININT002', usuario=cls.operador, empresa=cls.empresa,
            descricao='Outro ticket não pode receber o pagamento por campo forjado',
        )

    def setUp(self):
        current_timezone = timezone.override('America/Sao_Paulo')
        current_timezone.__enter__()
        self.addCleanup(current_timezone.__exit__, None, None, None)
        self.hoje = timezone.localdate()
        self.url = reverse('exibir-ticket', kwargs={'key': self.ticket.key})
        self.client.force_login(self.operador)

    def payload(self, **alteracoes):
        dados = {
            'form_type': 'form-pagamento', 'tipo': 'M',
            'valor_pagamento': '100.50', 'data_vencimento': self.hoje.isoformat(),
        }
        dados.update(alteracoes)
        return dados

    def pagamento_legado(self):
        return Pagamentos.objects.create(
            ticket_pagamento=self.ticket, tipo='S', valor_pagamento=Decimal('75.25'),
            data_pagamento=self.hoje - timedelta(days=120), status_pagamento=False,
            data_vencimento=None, data_pagamento_realizado=None,
        )

    def url_edicao(self, pagamento):
        return reverse('editar-pagamento', kwargs={
            'pagamento_id': pagamento.pk, 'key': self.ticket.key,
        })

    def test_ticket_cria_pagamento_pendente_com_valor_exato_e_vencimento(self):
        vencimento = self.hoje + timedelta(days=15)
        response = self.client.post(self.url, self.payload(data_vencimento=vencimento.isoformat()))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        pagamento = Pagamentos.objects.get()
        self.assertEqual(pagamento.ticket_pagamento_id, self.ticket.pk)
        self.assertEqual(pagamento.tipo, 'M')
        self.assertEqual(pagamento.valor_pagamento, Decimal('100.50'))
        self.assertEqual(pagamento.data_vencimento, vencimento)
        self.assertFalse(pagamento.status_pagamento)
        self.assertIsNone(pagamento.data_pagamento_realizado)
        self.assertIsNone(pagamento.data_pagamento)

    def test_ticket_cria_pagamento_quitado_com_data_real_distinta_do_vencimento(self):
        vencimento = self.hoje - timedelta(days=10)
        baixa = self.hoje - timedelta(days=2)
        response = self.client.post(self.url, self.payload(
            status_pagamento='on', data_vencimento=vencimento.isoformat(),
            data_pagamento_realizado=baixa.isoformat(),
        ))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        pagamento = Pagamentos.objects.get()
        self.assertTrue(pagamento.status_pagamento)
        self.assertEqual(pagamento.valor_pagamento, Decimal('100.50'))
        self.assertEqual(pagamento.data_vencimento, vencimento)
        self.assertEqual(pagamento.data_pagamento_realizado, baixa)
        self.assertIsNone(pagamento.data_pagamento)

    def test_ticket_rejeita_pagamento_incompleto_ou_incoerente_sem_criar_registro(self):
        casos = (
            ({'data_vencimento': ''}, 'data_vencimento'),
            ({'valor_pagamento': '-0.01'}, 'valor_pagamento'),
            ({'valor_pagamento': ''}, 'valor_pagamento'),
            ({'status_pagamento': 'on', 'data_pagamento_realizado': ''}, 'data_pagamento_realizado'),
        )
        for alteracoes, campo_com_erro in casos:
            with self.subTest(alteracoes=alteracoes):
                response = self.client.post(self.url, self.payload(**alteracoes))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'tickets/ticket.html')
                self.assertIn(campo_com_erro, response.context['pagamento'].errors)
                self.assertContains(response, str(response.context['pagamento'].errors[campo_com_erro][0]))
                self.assertEqual(Pagamentos.objects.count(), 0)

    def test_criacao_no_ticket_ignora_chaves_e_data_legada_forjadas(self):
        response = self.client.post(self.url, self.payload(
            ticket_pagamento=self.outro_ticket.pk,
            ticket_pagamento_id=self.outro_ticket.pk,
            data_pagamento='2000-01-01',
            id='123456', comprovante='comprovantes/arquivo-forjado.pdf',
        ))
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        pagamento = Pagamentos.objects.get()
        self.assertEqual(pagamento.ticket_pagamento_id, self.ticket.pk)
        self.assertNotEqual(pagamento.pk, 123456)
        self.assertEqual(pagamento.valor_pagamento, Decimal('100.50'))
        self.assertEqual(pagamento.data_vencimento, self.hoje)
        self.assertIsNone(pagamento.data_pagamento)
        self.assertFalse(pagamento.comprovante)
        self.assertFalse(Pagamentos.objects.filter(ticket_pagamento=self.outro_ticket).exists())

    def test_ticket_e_editor_expoem_novas_datas_sem_input_da_data_legada(self):
        pagamento = self.pagamento_legado()
        for url, nome_form in ((self.url, 'pagamento'), (self.url_edicao(pagamento), 'form')):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'name="data_vencimento"')
                self.assertContains(response, 'name="data_pagamento_realizado"')
                self.assertNotContains(response, 'name="data_pagamento"')
                self.assertIsNone(response.context[nome_form].prefix)
                self.assertNotIn('data_pagamento', response.context[nome_form].fields)
        pagamento.refresh_from_db()
        self.assertIsNone(pagamento.data_vencimento)
        self.assertIsNone(pagamento.data_pagamento_realizado)
        self.assertEqual(pagamento.data_pagamento, self.hoje - timedelta(days=120))

    def test_edicao_standalone_preserva_datas_desconhecidas_e_data_legada(self):
        pagamento = self.pagamento_legado()
        data_antiga = pagamento.data_pagamento
        response = self.client.post(self.url_edicao(pagamento), {
            'tipo': 'T', 'data_pagamento': '2000-01-01',
        })
        self.assertRedirects(response, f'{self.url}#pagamentos', fetch_redirect_response=False)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.tipo, 'T')
        self.assertEqual(pagamento.valor_pagamento, Decimal('75.25'))
        self.assertFalse(pagamento.status_pagamento)
        self.assertEqual(pagamento.data_pagamento, data_antiga)
        self.assertIsNone(pagamento.data_vencimento)
        self.assertIsNone(pagamento.data_pagamento_realizado)
        self.assertEqual(Pagamentos.objects.count(), 1)

    def test_quitacao_standalone_exige_data_real_e_salva_no_mesmo_pagamento(self):
        pagamento = self.pagamento_legado()
        original = Pagamentos.objects.filter(pk=pagamento.pk).values().get()
        url = self.url_edicao(pagamento)
        dados = {'tipo': 'S', 'status_pagamento': 'on'}
        response = self.client.post(url, dados)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'tickets/editar-pagamento.html')
        self.assertIn('data_pagamento_realizado', response.context['form'].errors)
        self.assertEqual(Pagamentos.objects.filter(pk=pagamento.pk).values().get(), original)

        baixa = self.hoje - timedelta(days=1)
        response = self.client.post(url, {**dados, 'data_pagamento_realizado': baixa.isoformat()})
        self.assertRedirects(response, f'{self.url}#pagamentos', fetch_redirect_response=False)
        pagamento.refresh_from_db()
        self.assertTrue(pagamento.status_pagamento)
        self.assertEqual(pagamento.data_pagamento_realizado, baixa)
        self.assertEqual(pagamento.data_pagamento, original['data_pagamento'])
        self.assertIsNone(pagamento.data_vencimento)
        self.assertEqual(pagamento.valor_pagamento, Decimal('75.25'))
        self.assertEqual(Pagamentos.objects.count(), 1)
