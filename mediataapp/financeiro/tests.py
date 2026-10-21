"""Financeiro: vencimento, situação e isolamento pertencem ao lançamento."""

from datetime import date, datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from html import unescape
import re
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from tickets.models import Orcamento, Pagamentos, Recebimentos, Ticket
from usuarios.test_helpers import criar_empresa, vincular_usuario


@override_settings(TIME_ZONE='America/Sao_Paulo')
class FinanceiroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('Prestadora financeira A', '00.000.000/0000-71')
        cls.outra_empresa = criar_empresa('Prestadora financeira B', '00.000.000/0000-72')
        cls.empresa_inativa = criar_empresa(
            'Prestadora financeira inativa', '00.000.000/0000-73', ativa=False,
        )
        cls.operador = cls.usuario('operador_financeiro', 'operador', cls.empresa)
        cls.gerente = cls.usuario('gerente_financeiro', 'gerente', cls.empresa)
        cls.outro_operador = cls.usuario('operador_financeiro_b', 'operador', cls.outra_empresa)
        cls.colaborador = cls.usuario('colaborador_financeiro', 'colaborador', cls.empresa)
        cls.cliente = cls.usuario('cliente_financeiro', 'cliente', cls.empresa)
        cls.assinante = cls.usuario('assinante_financeiro', 'assinante')
        cls.sem_empresa = cls.usuario('sem_empresa_financeiro', 'operador')
        cls.inativo = cls.usuario('empresa_inativa_financeiro', 'operador', cls.empresa_inativa)
        cls.admin = User.objects.create_superuser(
            username='admin_financeiro', email='admin-financeiro@example.invalid',
            password='senha-apenas-para-testes',
        )
        # O autor permanece o cliente independente, mesmo depois da assunção.
        cls.ticket = Ticket.objects.create(
            ticket='FIN000001', usuario=cls.assinante, empresa=cls.empresa,
            assumido_por=cls.gerente, descricao='Serviço financeiro da empresa A',
        )
        cls.outro_ticket = Ticket.objects.create(
            ticket='FIN000002', usuario=cls.assinante, empresa=cls.outra_empresa,
            assumido_por=cls.outro_operador, descricao='Serviço financeiro da empresa B',
        )
        cls.disponivel = Ticket.objects.create(
            ticket='FIN000003', usuario=cls.assinante, descricao='Disponível na fila geral',
        )

    @classmethod
    def usuario(cls, nome, perfil, empresa=None):
        usuario = User.objects.create_user(username=nome)
        assign_role(usuario, perfil)
        if empresa is not None:
            vincular_usuario(usuario, empresa)
        return usuario

    def setUp(self):
        current_timezone = timezone.override('America/Sao_Paulo')
        current_timezone.__enter__()
        self.addCleanup(current_timezone.__exit__, None, None, None)
        self.hoje = timezone.localdate()
        self.url = reverse('financeiro:index')
        self.client.force_login(self.operador)

    def debito(self, valor='10.00', vencimento='hoje', pago=False, ticket=None, **extras):
        if vencimento == 'hoje':
            vencimento = self.hoje
        dados = {
            'ticket_pagamento': ticket or self.ticket,
            'tipo': 'T', 'valor_pagamento': Decimal(valor) if valor is not None else None,
            'status_pagamento': pago, 'data_vencimento': vencimento,
            'data_pagamento': self.hoje - timedelta(days=400),
        }
        dados.update(extras)
        return Pagamentos.objects.create(**dados)

    def credito(self, valor='10.00', vencimento='hoje', recebido=False, ticket=None, **extras):
        if vencimento == 'hoje':
            vencimento = self.hoje
        dados = {
            'ticket_recebimento': ticket or self.ticket,
            'valor_recebimento': Decimal(valor) if valor is not None else None,
            'status_recebimento': recebido, 'data_vencimento': vencimento,
            'recebimento_realizado': recebido,
            'descricao_recebimento': 'Crédito financeiro de teste',
        }
        dados.update(extras)
        return Recebimentos.objects.create(**dados)

    def consultar(self, filtros=None, usuario=None, status=200):
        if usuario is not None:
            self.client.force_login(usuario)
        response = self.client.get(self.url, filtros or {})
        self.assertEqual(response.status_code, status)
        return response

    def ids(self, response):
        return {
            (linha['operacao'], linha['origem_id'])
            for linha in response.context['lancamentos']
        }

    def assert_lancamentos(self, response, creditos=(), debitos=()):
        self.assertEqual(
            self.ids(response),
            {('credito', item.pk) for item in creditos}
            | {('debito', item.pk) for item in debitos},
        )

    def assert_total(self, response, **esperados):
        for nome, valor in esperados.items():
            with self.subTest(total=nome):
                self.assertEqual(response.context['totais'][nome], Decimal(str(valor)))

    def test_anonimo_precisa_entrar(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
        self.assertEqual(parse_qs(urlsplit(response.url).query)['next'], [self.url])

    def test_financeiro_restrito_a_operadores_gerentes_e_superusuarios(self):
        self.credito('987.65', descricao_recebimento='Conteúdo financeiro restrito')
        for usuario in (self.colaborador, self.cliente, self.assinante, self.sem_empresa, self.inativo):
            with self.subTest(usuario=usuario.username):
                response = self.consultar(usuario=usuario, status=403)
                self.assertNotContains(response, 'Conteúdo financeiro restrito', status_code=403)

    def test_operador_e_gerente_veem_toda_empresa_sem_filtrar_por_autor_do_ticket(self):
        credito = self.credito('123.45')
        debito = self.debito('54.32')
        estrangeiro = self.credito('500.00', ticket=self.outro_ticket)
        fila = self.credito('900.00', ticket=self.disponivel)
        for usuario in (self.operador, self.gerente):
            with self.subTest(usuario=usuario.username):
                response = self.consultar(
                    {'empresa': self.outra_empresa.pk, 'usuario': self.assinante.pk}, usuario,
                )
                self.assert_lancamentos(response, [credito], [debito])
                self.assertNotIn(('credito', estrangeiro.pk), self.ids(response))
                self.assertNotIn(('credito', fila.pk), self.ids(response))
                self.assert_total(response, credito='123.45', debito='54.32')

    def test_superusuario_enxerga_lancamentos_de_todas_as_empresas(self):
        credito = self.credito('21.11')
        estrangeiro = self.credito('31.22', ticket=self.outro_ticket)
        debito = self.debito('9.33', ticket=self.outro_ticket)
        response = self.consultar(usuario=self.admin)
        self.assert_lancamentos(response, [credito, estrangeiro], [debito])
        self.assert_total(response, credito='52.33', debito='9.33')

    def test_listagem_aceita_apenas_metodos_de_leitura(self):
        self.assertEqual(self.client.post(self.url, {}).status_code, 405)

    def test_uma_linha_por_lancamento_sem_multiplicar_joins_ou_somar_orcamento(self):
        creditos = [self.credito('10.10'), self.credito('20.20')]
        debitos = [self.debito('3.30'), self.debito('4.40'), self.debito('5.50')]
        for valor in ('999.99', '777.77'):
            Orcamento.objects.create(
                ticket_orcamento=self.ticket, orcamento='Somente previsão comercial',
                descricao='Orçamento não é lançamento', valor_total=Decimal(valor),
            )
        response = self.consultar()
        self.assert_lancamentos(response, creditos, debitos)
        self.assertEqual(response.context['totais']['quantidade'], 5)
        self.assert_total(response, credito='30.30', debito='13.20', a_receber='30.30', a_pagar='13.20')

    def test_filtro_de_operacao(self):
        credito = self.credito('12.34')
        debito = self.debito('5.67')
        for operacao, creditos, debitos, total_c, total_d in (
            ('todas', [credito], [debito], '12.34', '5.67'),
            ('credito', [credito], [], '12.34', '0.00'),
            ('debito', [], [debito], '0.00', '5.67'),
        ):
            with self.subTest(operacao=operacao):
                response = self.consultar({'operacao': operacao})
                self.assert_lancamentos(response, creditos, debitos)
                self.assert_total(response, credito=total_c, debito=total_d)

    def test_situacoes_usam_quitacao_e_vencimento_incluindo_hoje_como_aberto(self):
        ontem = self.hoje - timedelta(days=1)
        amanha = self.hoje + timedelta(days=1)
        recebido = self.credito('11.00', ontem, recebido=True)
        pago = self.debito('22.00', ontem, pago=True)
        cv = self.credito('33.00', ontem)
        dv = self.debito('44.00', ontem)
        ch = self.credito('55.00')
        dh = self.debito('66.00')
        cf = self.credito('77.00', amanha)
        df = self.debito('88.00', amanha)
        for situacao, creditos, debitos in (
            ('pago', [], [pago]), ('recebido', [recebido], []),
            ('vencido', [cv], [dv]), ('aberto', [ch, cf], [dh, df]),
            ('todas', [recebido, cv, ch, cf], [pago, dv, dh, df]),
        ):
            with self.subTest(situacao=situacao):
                response = self.consultar({'situacao': situacao})
                self.assert_lancamentos(response, creditos, debitos)
        response = self.consultar({'situacao': 'vencido'})
        self.assert_total(response, vencido_credito='33.00', vencido_debito='44.00')
        self.assertEqual({linha['situacao'] for linha in response.context['lancamentos']}, {'vencido'})

    def test_operacao_e_situacao_sao_intersecao_e_nao_ampliam_consulta(self):
        self.credito(recebido=True)
        self.debito(pago=True)
        for filtros in (
            {'operacao': 'credito', 'situacao': 'pago'},
            {'operacao': 'debito', 'situacao': 'recebido'},
        ):
            with self.subTest(filtros=filtros):
                response = self.consultar(filtros)
                self.assert_lancamentos(response)
                self.assert_total(response, credito=0, debito=0, recebido=0, pago=0)

    def test_atalhos_incluem_exatamente_proximos_30_60_90_dias(self):
        offsets = (-1, 0, 29, 30, 59, 60, 89, 90)
        lancamentos = {
            dias: self.credito(str(dias + 2), self.hoje + timedelta(days=dias))
            for dias in offsets
        }
        for dias in (30, 60, 90):
            with self.subTest(periodo=dias):
                response = self.consultar({'periodo': str(dias)})
                self.assert_lancamentos(
                    response, [item for offset, item in lancamentos.items() if 0 <= offset < dias],
                )

    def test_intervalo_personalizado_inclusivo_filtra_vencimento_e_nao_criacao_ou_baixa(self):
        inicio = self.hoje - timedelta(days=50)
        fim = self.hoje - timedelta(days=20)
        credito_inicio = self.credito('11.11', inicio, recebido=True,
                                      data_recebimento_realizado=timezone.now())
        credito_fim = self.credito('22.22', fim)
        debito_inicio = self.debito('3.33', inicio, pago=True,
                                    data_pagamento_realizado=self.hoje + timedelta(days=20))
        debito_fim = self.debito('4.44', fim)
        self.credito('300.00', inicio - timedelta(days=1))
        self.debito('400.00', fim + timedelta(days=1))
        response = self.consultar({
            'periodo': 'personalizado', 'data_inicio': inicio.isoformat(), 'data_fim': fim.isoformat(),
        })
        self.assert_lancamentos(response, [credito_inicio, credito_fim], [debito_inicio, debito_fim])
        self.assert_total(response, credito='33.33', debito='7.77', recebido='11.11', pago='3.33')

    def test_periodo_de_um_dia_aceita_inicio_igual_fim(self):
        credito = self.credito('12.00')
        self.credito('45.00', self.hoje + timedelta(days=1))
        response = self.consultar({
            'periodo': 'personalizado', 'data_inicio': self.hoje.isoformat(),
            'data_fim': self.hoje.isoformat(),
        })
        self.assert_lancamentos(response, [credito])

    def test_filtros_invalidos_exibem_erros_sem_expor_lancamentos_ou_totais(self):
        self.credito('987.65', descricao_recebimento='Crédito que não pode vazar no filtro inválido')
        invalidos = (
            {'operacao': 'qualquer'}, {'situacao': 'pendente'}, {'periodo': '365'},
            {'periodo': 'personalizado'},
            {'periodo': 'personalizado', 'data_inicio': self.hoje.isoformat()},
            {'periodo': 'personalizado', 'data_fim': self.hoje.isoformat()},
            {'periodo': 'personalizado', 'data_inicio': '2026-02-30', 'data_fim': '2026-03-01'},
            {'periodo': 'personalizado', 'data_inicio': '21/10/2026', 'data_fim': '2026-10-22'},
            {'periodo': 'personalizado', 'data_inicio': '2026-10-22', 'data_fim': '2026-10-21'},
            {'data_inicio': 'inválida'},
        )
        for filtros in invalidos:
            with self.subTest(filtros=filtros):
                response = self.consultar(filtros, status=400)
                self.assertTrue(response.context['form'].errors)
                self.assert_lancamentos(response)
                self.assertEqual(response.context['totais']['quantidade'], 0)
                self.assert_total(response, credito=0, debito=0, recebido=0, pago=0,
                                  a_receber=0, a_pagar=0, vencido_credito=0, vencido_debito=0)
                self.assertNotContains(
                    response, 'Crédito que não pode vazar no filtro inválido', status_code=400,
                )

    def test_sem_vencimento_fica_identificado_e_nao_recebe_data_ficticia(self):
        credito = self.credito('17.17', None)
        debito = self.debito('8.08', None)
        response = self.consultar()
        self.assert_lancamentos(response, [credito], [debito])
        self.assertEqual(response.context['totais']['sem_vencimento_count'], 2)
        for linha in response.context['lancamentos']:
            self.assertIsNone(linha['vencimento'])
            self.assertEqual(linha['situacao'], 'sem_vencimento')
        for filtros in ({'situacao': 'aberto'}, {'situacao': 'vencido'}, {'periodo': '30'}):
            with self.subTest(filtros=filtros):
                self.assert_lancamentos(self.consultar(filtros))
        credito.refresh_from_db()
        debito.refresh_from_db()
        self.assertIsNone(credito.data_vencimento)
        self.assertIsNone(debito.data_vencimento)
        self.assertEqual(debito.data_pagamento, self.hoje - timedelta(days=400))

    def test_quitado_sem_vencimento_mantem_situacao_realizada_e_sinalizacao(self):
        credito = self.credito('19.19', None, recebido=True)
        debito = self.debito('9.09', None, pago=True)
        self.assert_lancamentos(self.consultar({'situacao': 'recebido'}), [credito])
        self.assert_lancamentos(self.consultar({'situacao': 'pago'}), debitos=[debito])
        response = self.consultar()
        self.assertEqual(response.context['totais']['sem_vencimento_count'], 2)
        self.assertEqual(response.context['totais']['sem_quitacao_count'], 2)
        self.assert_total(response, recebido='19.19', pago='9.09')

    def test_valor_ausente_e_diferente_de_zero_e_nao_e_silenciosamente_completado(self):
        ausente_c = self.credito(None)
        ausente_d = self.debito(None)
        zero = self.credito('0.00')
        informado = self.credito('13.75')
        response = self.consultar()
        self.assert_lancamentos(response, [ausente_c, zero, informado], [ausente_d])
        self.assertEqual(response.context['totais']['sem_valor_count'], 2)
        rows = {(r['operacao'], r['origem_id']): r for r in response.context['lancamentos']}
        for chave in (('credito', ausente_c.pk), ('debito', ausente_d.pk)):
            self.assertIsNone(rows[chave]['valor'])
            self.assertTrue(rows[chave]['sem_valor'])
        self.assertEqual(rows[('credito', zero.pk)]['valor'], Decimal('0.00'))
        self.assertFalse(rows[('credito', zero.pk)]['sem_valor'])
        self.assert_total(response, credito='13.75', debito=0, a_receber='13.75')

    def test_status_canonico_prevalece_sobre_confirmacao_antiga_sem_mutacao_no_get(self):
        recebido = self.credito('71.11', recebido=True, recebimento_realizado=False)
        pendente = self.credito('82.22', recebido=False, recebimento_realizado=True)
        antes = list(Recebimentos.objects.order_by('pk').values())
        response = self.consultar()
        self.assert_total(response, recebido='71.11', a_receber='82.22')
        self.assertEqual(response.context['totais']['confirmacao_divergente_count'], 2)
        self.assert_lancamentos(self.consultar({'situacao': 'recebido'}), [recebido])
        self.assert_lancamentos(self.consultar({'situacao': 'aberto'}), [pendente])
        self.assertEqual(list(Recebimentos.objects.order_by('pk').values()), antes)

    def test_valores_quitados_e_pendentes_com_centavos_sao_exatos(self):
        self.credito('0.10', recebido=True)
        self.credito('0.20', recebido=True)
        self.credito('0.40')
        self.debito('0.01', pago=True)
        self.debito('0.02')
        response = self.consultar()
        self.assert_total(response, credito='0.70', debito='0.03', recebido='0.30',
                          pago='0.01', a_receber='0.40', a_pagar='0.02')

    def test_paginacao_preserva_filtros_e_totais_abrangem_todas_as_paginas(self):
        creditos = [self.credito('1.01') for _ in range(27)]
        self.debito('999.99')
        filtros = {
            'operacao': 'credito', 'situacao': 'aberto', 'periodo': 'personalizado',
            'data_inicio': self.hoje.isoformat(), 'data_fim': self.hoje.isoformat(),
        }
        primeira = self.consultar(filtros)
        pagina = primeira.context['page_obj']
        self.assertEqual(pagina.paginator.per_page, 25)
        self.assertEqual(pagina.paginator.count, 27)
        self.assertEqual(len(pagina.object_list), 25)
        self.assert_total(primeira, credito='27.27', debito=0, a_receber='27.27')
        links = [unescape(href) for href in re.findall(r'href="([^"]+)"', primeira.content.decode())]
        proximas = [parse_qs(urlsplit(href).query) for href in links if parse_qs(urlsplit(href).query).get('page') == ['2']]
        self.assertTrue(proximas, 'A próxima página deve ser acessível por um link.')
        for nome, valor in filtros.items():
            self.assertEqual(proximas[0].get(nome), [valor])
        segunda = self.consultar({**filtros, 'page': 2})
        self.assertEqual(len(segunda.context['page_obj'].object_list), 2)
        self.assertFalse(self.ids(primeira) & self.ids(segunda))
        self.assertEqual(self.ids(primeira) | self.ids(segunda), {('credito', c.pk) for c in creditos})
        self.assert_total(segunda, credito='27.27', a_receber='27.27')
        repetida = self.consultar(filtros)
        self.assertEqual(
            [r['origem_id'] for r in primeira.context['lancamentos']],
            [r['origem_id'] for r in repetida.context['lancamentos']],
        )

    def test_descricoes_sao_escapadas_e_link_edicao_aponta_para_financeiro(self):
        credito = self.credito(descricao_recebimento='<script>alert("financeiro")</script>')
        debito = self.debito()
        response = self.consultar()
        self.assertNotContains(response, '<script>alert("financeiro")</script>')
        self.assertContains(response, '&lt;script&gt;')
        self.assertContains(response, reverse('financeiro:editar-recebimento', args=[credito.pk]))
        self.assertContains(response, reverse('financeiro:editar-pagamento', args=[debito.pk]))

    def test_situacao_e_periodo_usam_dia_de_sao_paulo_na_virada_utc(self):
        # 22/10 UTC ainda corresponde a 21/10 em São Paulo.
        instante = datetime(2026, 10, 22, 1, 30, tzinfo=datetime_timezone.utc)
        ontem = self.credito('10.00', date(2026, 10, 20))
        hoje = self.credito('20.00', date(2026, 10, 21))
        with patch('django.utils.timezone.now', return_value=instante):
            self.assert_lancamentos(self.consultar({'situacao': 'vencido'}), [ontem])
            self.assert_lancamentos(self.consultar({'periodo': '30'}), [hoje])

    def test_editores_negam_outros_perfis_e_lancamentos_de_outra_empresa(self):
        pagamento = self.debito(ticket=self.outro_ticket)
        recebimento = self.credito(ticket=self.outro_ticket)
        urls = (
            reverse('financeiro:editar-pagamento', args=[pagamento.pk]),
            reverse('financeiro:editar-recebimento', args=[recebimento.pk]),
        )
        antes_p = list(Pagamentos.objects.values())
        antes_r = list(Recebimentos.objects.values())
        for url in urls:
            for metodo in ('get', 'post'):
                with self.subTest(url=url, metodo=metodo):
                    self.client.force_login(self.operador)
                    self.assertEqual(getattr(self.client, metodo)(url, {}).status_code, 404)
                    for usuario in (self.assinante, self.colaborador, self.cliente, self.sem_empresa, self.inativo):
                        self.client.force_login(usuario)
                        self.assertEqual(getattr(self.client, metodo)(url, {}).status_code, 403)
        self.assertEqual(list(Pagamentos.objects.values()), antes_p)
        self.assertEqual(list(Recebimentos.objects.values()), antes_r)

    def test_editores_get_preservam_datas_e_nao_reinterpretam_legados(self):
        debito = self.debito(vencimento=None, pago=True, data_pagamento_realizado=None)
        credito = self.credito(vencimento=None, recebido=True, data_recebimento_realizado=None)
        antes_p = list(Pagamentos.objects.values())
        antes_r = list(Recebimentos.objects.values())
        for nome, lancamento in (('editar-pagamento', debito), ('editar-recebimento', credito)):
            with self.subTest(nome=nome):
                response = self.client.get(reverse(f'financeiro:{nome}', args=[lancamento.pk]))
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['form'].instance.data_vencimento)
        self.assertEqual(list(Pagamentos.objects.values()), antes_p)
        self.assertEqual(list(Recebimentos.objects.values()), antes_r)

    def test_editar_debito_separa_vencimento_e_baixa_sem_aceitar_ticket_forjado(self):
        pagamento = self.debito('31.31')
        legado = pagamento.data_pagamento
        url = reverse('financeiro:editar-pagamento', args=[pagamento.pk])
        response = self.client.post(url, {
            'tipo': 'M', 'valor_pagamento': '41.41', 'status_pagamento': 'on',
            'data_vencimento': (self.hoje - timedelta(days=2)).isoformat(),
            'data_pagamento_realizado': self.hoje.isoformat(),
            'ticket_pagamento': self.outro_ticket.pk,
            'ticket_pagamento_id': self.outro_ticket.pk,
            'data_pagamento': '2000-01-01',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.url).path, self.url)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.ticket_pagamento_id, self.ticket.pk)
        self.assertEqual(pagamento.valor_pagamento, Decimal('41.41'))
        self.assertEqual(pagamento.data_vencimento, self.hoje - timedelta(days=2))
        self.assertEqual(pagamento.data_pagamento_realizado, self.hoje)
        self.assertEqual(pagamento.data_pagamento, legado)
        self.assertTrue(pagamento.status_pagamento)
        self.assertEqual(Pagamentos.objects.count(), 1)

    def test_editar_credito_baixa_e_sincroniza_confirmacao_ignorando_campos_protegidos(self):
        recebimento = self.credito('51.51')
        url = reverse('financeiro:editar-recebimento', args=[recebimento.pk])
        instante = timezone.now() - timedelta(hours=1)
        instante_local = timezone.localtime(instante).replace(microsecond=0)
        response = self.client.post(url, {
            'valor_recebimento': '61.61', 'status_recebimento': 'True',
            'data_vencimento': self.hoje.isoformat(),
            'data_recebimento_realizado': instante_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'ticket_recebimento': self.outro_ticket.pk,
            'ticket_recebimento_id': self.outro_ticket.pk,
            'razao_social': 'Favorecido forjado', 'recebimento_realizado': '',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(urlsplit(response.url).path, self.url)
        recebimento.refresh_from_db()
        self.assertEqual(recebimento.ticket_recebimento_id, self.ticket.pk)
        self.assertEqual(recebimento.valor_recebimento, Decimal('61.61'))
        self.assertEqual(recebimento.data_recebimento_realizado, instante_local)
        self.assertTrue(recebimento.status_recebimento)
        self.assertTrue(recebimento.recebimento_realizado)
        self.assertIsNone(recebimento.razao_social)
        self.assertEqual(Recebimentos.objects.count(), 1)

    def test_edicao_preserva_filtros_e_ignora_redirecionamento_externo(self):
        pagamento = self.debito('71.71')
        filtros = {
            'operacao': 'debito', 'situacao': 'aberto', 'periodo': '30', 'page': '2',
        }
        # O retorno admite somente filtros conhecidos, nunca uma URL arbitrária.
        query = '&'.join(f'{nome}={valor}' for nome, valor in filtros.items())
        url = reverse('financeiro:editar-pagamento', args=[pagamento.pk])
        url = f'{url}?{query}&next=https://externo.example.invalid/roubar&empresa={self.outra_empresa.pk}'
        response = self.client.post(url, {
            'tipo': 'T', 'valor_pagamento': '81.81',
            'data_vencimento': self.hoje.isoformat(),
            'next': 'https://externo.example.invalid/roubar',
        })
        self.assertEqual(response.status_code, 302)
        destino = urlsplit(response.url)
        self.assertEqual(destino.path, self.url)
        self.assertEqual(destino.netloc, '')
        self.assertEqual(parse_qs(destino.query), {nome: [valor] for nome, valor in filtros.items()})
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.valor_pagamento, Decimal('81.81'))
        self.assertEqual(pagamento.ticket_pagamento_id, self.ticket.pk)
