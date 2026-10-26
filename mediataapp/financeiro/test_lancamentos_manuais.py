"""Lançamentos avulsos compartilham o financeiro sem depender de tickets."""

from datetime import timedelta
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role

from tickets.models import Pagamentos, Recebimentos, Ticket
from usuarios.test_helpers import criar_empresa, vincular_usuario

from .forms import LancamentoManualForm
from .models import LancamentoManual


@override_settings(TIME_ZONE='America/Sao_Paulo')
class LancamentosManuaisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = criar_empresa('Financeiro avulso A', '00.000.000/0000-81')
        cls.outra_empresa = criar_empresa('Financeiro avulso B', '00.000.000/0000-82')
        cls.empresa_inativa = criar_empresa(
            'Financeiro avulso inativo', '00.000.000/0000-83', ativa=False,
        )
        cls.gestor = cls.usuario('gestor_manual_a', 'gerente', cls.empresa)
        cls.operador = cls.usuario('operador_manual_restrito', 'operador', cls.empresa)
        cls.gerente = cls.usuario('gerente_manual_a', 'gerente', cls.empresa)
        cls.outro_gestor = cls.usuario('gestor_manual_b', 'gerente', cls.outra_empresa)
        cls.assinante = cls.usuario('assinante_manual', 'assinante')
        cls.colaborador = cls.usuario('colaborador_manual', 'colaborador', cls.empresa)
        cls.cliente = cls.usuario('cliente_manual', 'cliente', cls.empresa)
        cls.sem_empresa = cls.usuario('gerente_manual_sem_empresa', 'gerente')
        cls.inativo = cls.usuario('gerente_manual_inativo', 'gerente', cls.empresa_inativa)
        cls.admin = User.objects.create_superuser(
            username='admin_manual', email='admin-manual@example.invalid',
            password='senha-apenas-para-testes',
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
        self.novo_url = reverse('financeiro:novo-lancamento')
        self.client.force_login(self.gestor)

    def dados(self, **alteracoes):
        dados = {
            'operacao': 'credito', 'descricao': 'Mensalidade sem ticket',
            'contraparte': 'Cliente avulso de teste', 'valor': '123.45',
            'data_vencimento': self.hoje.isoformat(), 'data_quitacao': '',
        }
        dados.update(alteracoes)
        return dados

    def manual(self, operacao='credito', valor='10.00', vencimento=None,
               liquidado=False, empresa=None, **alteracoes):
        dados = {
            'empresa': empresa or self.empresa, 'criado_por': self.gestor,
            'operacao': operacao, 'descricao': 'Lançamento manual de teste',
            'contraparte': 'Contraparte de teste', 'valor': Decimal(valor),
            'data_vencimento': vencimento or self.hoje,
            'liquidado': liquidado, 'data_quitacao': self.hoje if liquidado else None,
        }
        dados.update(alteracoes)
        return LancamentoManual.objects.create(**dados)

    def ticket(self, **alteracoes):
        dados = {
            'usuario': self.assinante, 'empresa': self.empresa,
            'assumido_por': self.gestor, 'descricao': 'Serviço vinculado ao financeiro',
        }
        dados.update(alteracoes)
        return Ticket.objects.create(**dados)

    def consultar(self, filtros=None, usuario=None, status=200):
        if usuario is not None:
            self.client.force_login(usuario)
        response = self.client.get(self.url, filtros or {})
        self.assertEqual(response.status_code, status)
        return response

    def identidades(self, response):
        return {
            (linha['origem'], linha['operacao'], linha['origem_id'])
            for linha in response.context['lancamentos']
        }

    def assert_manuais(self, response, esperados):
        self.assertEqual(
            self.identidades(response),
            {('manual', item.operacao, item.pk) for item in esperados},
        )

    def assert_totais(self, response, **esperados):
        for nome, valor in esperados.items():
            with self.subTest(total=nome):
                self.assertEqual(response.context['totais'][nome], Decimal(str(valor)))

    def test_botao_novo_lancamento_e_formulario_nao_exigem_ticket(self):
        response = self.consultar()
        self.assertContains(response, self.novo_url)
        response = self.client.get(self.novo_url)
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertIsInstance(form, LancamentoManualForm)
        self.assertNotIn('ticket', form.fields)
        self.assertNotIn('criado_por', form.fields)
        self.assertNotIn('empresa', form.fields)
        self.assertEqual(form.initial['operacao'], 'debito')
        self.assertEqual(Ticket.objects.count(), 0)

    def test_anonimo_precisa_entrar_para_cadastrar_e_editar(self):
        manual = self.manual()
        self.client.logout()
        for url in (self.novo_url, reverse('financeiro:editar-manual', args=[manual.pk])):
            for metodo in ('get', 'post'):
                with self.subTest(url=url, metodo=metodo):
                    response = getattr(self.client, metodo)(url, {})
                    self.assertEqual(response.status_code, 302)
                    self.assertIn('/accounts/login/', response.url)

    def test_cadastro_e_edicao_negam_perfis_sem_acesso_financeiro(self):
        manual = self.manual(descricao='Descrição financeira protegida')
        urls = (self.novo_url, reverse('financeiro:editar-manual', args=[manual.pk]))
        antes = list(LancamentoManual.objects.values())
        for usuario in (
            self.operador, self.assinante, self.cliente, self.colaborador, self.sem_empresa, self.inativo,
        ):
            self.client.force_login(usuario)
            for url in urls:
                for metodo in ('get', 'post'):
                    with self.subTest(usuario=usuario.username, url=url, metodo=metodo):
                        response = getattr(self.client, metodo)(url, self.dados())
                        self.assertEqual(response.status_code, 403)
                        self.assertNotContains(response, manual.descricao, status_code=403)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)

    def test_cadastrar_credito_e_debito_independentes_nao_cria_ticket_ou_financeiro_do_ticket(self):
        for operacao, usuario in (('credito', self.gestor), ('debito', self.gerente)):
            with self.subTest(operacao=operacao):
                self.client.force_login(usuario)
                response = self.client.post(self.novo_url, self.dados(operacao=operacao))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(urlsplit(response.url).path, self.url)
                lancamento = LancamentoManual.objects.get(operacao=operacao)
                self.assertEqual(lancamento.empresa_id, self.empresa.pk)
                self.assertEqual(lancamento.criado_por_id, usuario.pk)
                self.assertEqual(lancamento.valor, Decimal('123.45'))
                self.assertEqual(lancamento.data_vencimento, self.hoje)
                self.assertFalse(lancamento.liquidado)
                self.assertIsNone(lancamento.data_quitacao)
        self.assertEqual(LancamentoManual.objects.count(), 2)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(Pagamentos.objects.count(), 0)
        self.assertEqual(Recebimentos.objects.count(), 0)

    def test_empresa_e_autoria_sao_atribuidas_no_servidor(self):
        response = self.client.post(self.novo_url, self.dados(
            empresa=str(self.outra_empresa.pk), empresa_id=str(self.outra_empresa.pk),
            criado_por=str(self.admin.pk), criado_por_id=str(self.admin.pk),
            ticket='999', ticket_id='999',
        ))
        self.assertEqual(response.status_code, 302)
        lancamento = LancamentoManual.objects.get()
        self.assertEqual(lancamento.empresa_id, self.empresa.pk)
        self.assertEqual(lancamento.criado_por_id, self.gestor.pk)

    def test_superusuario_escolhe_empresa_ativa_explicitamente(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.novo_url)
        self.assertEqual(response.status_code, 200)
        field = response.context['form'].fields['empresa']
        self.assertTrue(field.required)
        self.assertEqual(set(field.queryset.values_list('pk', flat=True)), {
            self.empresa.pk, self.outra_empresa.pk,
        })
        for empresa in ('', str(self.empresa_inativa.pk), '99999999'):
            with self.subTest(empresa=empresa):
                response = self.client.post(self.novo_url, self.dados(empresa=empresa))
                self.assertEqual(response.status_code, 200)
                self.assertIn('empresa', response.context['form'].errors)
                self.assertFalse(LancamentoManual.objects.exists())
        response = self.client.post(self.novo_url, self.dados(empresa=self.outra_empresa.pk))
        self.assertEqual(response.status_code, 302)
        lancamento = LancamentoManual.objects.get()
        self.assertEqual(lancamento.empresa_id, self.outra_empresa.pk)
        self.assertEqual(lancamento.criado_por_id, self.admin.pk)

    def test_campos_obrigatorios_operacao_valor_e_datas_invalidos_nao_salvam(self):
        invalidos = (
            {'descricao': ''}, {'operacao': ''}, {'operacao': 'transferencia'},
            {'valor': ''}, {'valor': '0.00'}, {'valor': '-0.01'}, {'valor': 'inválido'},
            {'data_vencimento': ''}, {'data_vencimento': '2026-02-30'},
            {'data_vencimento': '21/10/2026'},
        )
        for alteracoes in invalidos:
            with self.subTest(alteracoes=alteracoes):
                response = self.client.post(self.novo_url, self.dados(**alteracoes))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(LancamentoManual.objects.exists())
        self.assertFalse(Ticket.objects.exists())

    def test_quitacao_exige_data_real_nao_futura(self):
        for data in ('', 'inválida', (self.hoje + timedelta(days=1)).isoformat()):
            with self.subTest(data=data):
                response = self.client.post(
                    self.novo_url, self.dados(liquidado='on', data_quitacao=data),
                )
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context['form'].errors)
                self.assertFalse(LancamentoManual.objects.exists())
        ontem = self.hoje - timedelta(days=1)
        response = self.client.post(
            self.novo_url, self.dados(liquidado='on', data_quitacao=ontem.isoformat()),
        )
        self.assertEqual(response.status_code, 302)
        lancamento = LancamentoManual.objects.get()
        self.assertTrue(lancamento.liquidado)
        self.assertEqual(lancamento.data_quitacao, ontem)

    def test_pendente_nao_guarda_data_de_quitacao_forjada(self):
        response = self.client.post(self.novo_url, self.dados(data_quitacao=self.hoje.isoformat()))
        self.assertEqual(response.status_code, 302)
        lancamento = LancamentoManual.objects.get()
        self.assertFalse(lancamento.liquidado)
        self.assertIsNone(lancamento.data_quitacao)

    def test_edicao_estrangeira_nao_expoe_nem_modifica_lancamento(self):
        manual = self.manual(empresa=self.outra_empresa, descricao='Segredo da outra empresa')
        url = reverse('financeiro:editar-manual', args=[manual.pk])
        antes = list(LancamentoManual.objects.values())
        for metodo in ('get', 'post'):
            with self.subTest(metodo=metodo):
                response = getattr(self.client, metodo)(url, self.dados(valor='999.99'))
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(response, manual.descricao, status_code=404)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)

    def test_editar_preserva_empresa_autor_e_data_de_cadastro(self):
        manual = self.manual()
        criado_em = manual.criado_em
        self.client.force_login(self.gerente)
        response = self.client.post(reverse('financeiro:editar-manual', args=[manual.pk]), self.dados(
            operacao='debito', descricao='Aluguel atualizado', valor='51.51',
            contraparte='Favorecido avulso', liquidado='on', data_quitacao=self.hoje.isoformat(),
            empresa=self.outra_empresa.pk, empresa_id=self.outra_empresa.pk,
            criado_por=self.gerente.pk, criado_por_id=self.gerente.pk,
        ))
        self.assertEqual(response.status_code, 302)
        manual.refresh_from_db()
        self.assertEqual(manual.empresa_id, self.empresa.pk)
        self.assertEqual(manual.criado_por_id, self.gestor.pk)
        self.assertEqual(manual.criado_em, criado_em)
        self.assertEqual(manual.operacao, 'debito')
        self.assertEqual(manual.descricao, 'Aluguel atualizado')
        self.assertEqual(manual.contraparte, 'Favorecido avulso')
        self.assertEqual(manual.valor, Decimal('51.51'))
        self.assertTrue(manual.liquidado)
        self.assertEqual(manual.data_quitacao, self.hoje)
        self.assertEqual(LancamentoManual.objects.count(), 1)

    def test_superusuario_tambem_nao_transfere_empresa_pela_edicao(self):
        manual = self.manual()
        self.client.force_login(self.admin)
        url = reverse('financeiro:editar-manual', args=[manual.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        empresa_field = response.context['form'].fields.get('empresa')
        if empresa_field is not None:
            self.assertTrue(empresa_field.disabled)
        response = self.client.post(url, self.dados(empresa=self.outra_empresa.pk))
        self.assertEqual(response.status_code, 302)
        manual.refresh_from_db()
        self.assertEqual(manual.empresa_id, self.empresa.pk)
        self.assertEqual(manual.criado_por_id, self.gestor.pk)

    def test_reabrir_lancamento_limpa_quitacao_e_atualiza_situacao(self):
        manual = self.manual(liquidado=True, vencimento=self.hoje - timedelta(days=1))
        url = reverse('financeiro:editar-manual', args=[manual.pk])
        response = self.client.post(url, self.dados(
            data_vencimento=manual.data_vencimento.isoformat(),
            data_quitacao=self.hoje.isoformat(),
        ))
        self.assertEqual(response.status_code, 302)
        manual.refresh_from_db()
        self.assertFalse(manual.liquidado)
        self.assertIsNone(manual.data_quitacao)
        self.assert_manuais(self.consultar({'situacao': 'vencido'}), [manual])
        self.assert_manuais(self.consultar({'situacao': 'recebido'}), [])

    def test_get_e_post_invalido_na_edicao_preservam_registro(self):
        manual = self.manual(liquidado=True)
        url = reverse('financeiro:editar-manual', args=[manual.pk])
        antes = list(LancamentoManual.objects.values())
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].instance.pk, manual.pk)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)
        response = self.client.post(url, self.dados(valor='-1.00'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)

    def test_tres_fontes_com_ids_iguais_nao_se_confundem_nem_duplicam(self):
        ticket = self.ticket()
        credito = Recebimentos.objects.create(
            pk=810001, ticket_recebimento=ticket, valor_recebimento=Decimal('12.34'),
            descricao_recebimento='Recebimento vinculado', data_vencimento=self.hoje,
        )
        debito = Pagamentos.objects.create(
            pk=810001, ticket_pagamento=ticket, tipo='M', valor_pagamento=Decimal('5.67'),
            data_vencimento=self.hoje,
        )
        manual = self.manual(pk=810001, valor='7.89')
        response = self.consultar()
        self.assertEqual(self.identidades(response), {
            ('ticket', 'credito', credito.pk), ('ticket', 'debito', debito.pk),
            ('manual', 'credito', manual.pk),
        })
        self.assertEqual(response.context['totais']['quantidade'], 3)
        self.assert_totais(response, credito='20.23', debito='5.67', a_receber='20.23', a_pagar='5.67')
        linhas = {(r['origem'], r['operacao']): r for r in response.context['lancamentos']}
        avulsa = linhas[('manual', 'credito')]
        for campo in ('ticket_id', 'ticket_codigo', 'ticket_key'):
            self.assertIsNone(avulsa[campo])
        self.assertEqual(avulsa['descricao'], manual.descricao)
        self.assertEqual(avulsa['contraparte'], manual.contraparte)
        self.assertEqual(avulsa['empresa_nome'], self.empresa.nome_fantasia)
        self.assertEqual(urlsplit(avulsa['url_edicao']).path,
                         reverse('financeiro:editar-manual', args=[manual.pk]))
        for operacao, nome in (('credito', 'editar-recebimento'), ('debito', 'editar-pagamento')):
            self.assertEqual(
                urlsplit(linhas[('ticket', operacao)]['url_edicao']).path,
                reverse(f'financeiro:{nome}', args=[810001]),
            )

    def test_manuais_respeitam_operacao_e_todas_as_situacoes(self):
        ontem, amanha = self.hoje - timedelta(days=1), self.hoje + timedelta(days=1)
        recebido = self.manual(valor='1.01', vencimento=ontem, liquidado=True)
        pago = self.manual('debito', '2.02', ontem, liquidado=True)
        cv = self.manual(valor='3.03', vencimento=ontem)
        dv = self.manual('debito', '4.04', ontem)
        ca = self.manual(valor='5.05')
        da = self.manual('debito', '6.06', amanha)
        todos = [recebido, pago, cv, dv, ca, da]
        for situacao, esperados in (
            ('todas', todos), ('recebido', [recebido]), ('pago', [pago]),
            ('vencido', [cv, dv]), ('aberto', [ca, da]),
        ):
            for operacao in ('todas', 'credito', 'debito'):
                with self.subTest(situacao=situacao, operacao=operacao):
                    response = self.consultar({'situacao': situacao, 'operacao': operacao})
                    self.assert_manuais(response, [
                        item for item in esperados if operacao == 'todas' or item.operacao == operacao
                    ])
        self.assert_totais(self.consultar(), credito='9.09', debito='12.12',
                           recebido='1.01', pago='2.02', a_receber='8.08', a_pagar='10.10',
                           vencido_credito='3.03', vencido_debito='4.04')

    def test_manuais_filtram_vencimento_nos_atalhos_e_intervalo_inclusivo(self):
        lancamentos = {
            dias: self.manual(valor='1.00', vencimento=self.hoje + timedelta(days=dias))
            for dias in (-2, -1, 0, 29, 30, 59, 60, 89, 90)
        }
        for dias in (30, 60, 90):
            with self.subTest(periodo=dias):
                response = self.consultar({'periodo': str(dias)})
                self.assert_manuais(response, [
                    item for offset, item in lancamentos.items() if 0 <= offset < dias
                ])
        response = self.consultar({
            'periodo': 'personalizado',
            'data_inicio': (self.hoje - timedelta(days=2)).isoformat(),
            'data_fim': (self.hoje - timedelta(days=1)).isoformat(),
        })
        self.assert_manuais(response, [lancamentos[-2], lancamentos[-1]])

    def test_isolamento_tambem_aplica_a_totais_e_filtros_forjados(self):
        proprio = self.manual(valor='10.11')
        estrangeiro = self.manual(valor='999.99', empresa=self.outra_empresa,
                                  descricao='Lançamento restrito da empresa B')
        response = self.consultar({'empresa': self.outra_empresa.pk, 'criado_por': self.admin.pk})
        self.assert_manuais(response, [proprio])
        self.assert_totais(response, credito='10.11', a_receber='10.11')
        self.assertNotContains(response, estrangeiro.descricao)
        response = self.consultar(usuario=self.outro_gestor)
        self.assert_manuais(response, [estrangeiro])
        self.assert_totais(response, credito='999.99')
        response = self.consultar(usuario=self.admin)
        self.assert_manuais(response, [proprio, estrangeiro])
        self.assert_totais(response, credito='1010.10')

    def test_intervalo_invalido_nao_expoe_lancamentos_manuais_ou_totais(self):
        manual = self.manual(valor='123.45', descricao='Manual não deve vazar por filtro inválido')
        response = self.consultar({
            'periodo': 'personalizado',
            'data_inicio': self.hoje.isoformat(),
            'data_fim': (self.hoje - timedelta(days=1)).isoformat(),
        }, status=400)
        self.assertTrue(response.context['form'].errors)
        self.assert_manuais(response, [])
        self.assertEqual(response.context['totais']['quantidade'], 0)
        self.assert_totais(response, credito=0, debito=0, recebido=0, pago=0,
                           a_receber=0, a_pagar=0, vencido_credito=0, vencido_debito=0)
        self.assertNotContains(response, manual.descricao, status_code=400)

    def test_paginacao_unica_entre_fontes_preserva_totais_e_identidades(self):
        manuais = [self.manual(valor='1.01') for _ in range(23)]
        ticket = self.ticket()
        creditos = [Recebimentos.objects.create(
            ticket_recebimento=ticket, valor_recebimento=Decimal('2.02'),
            data_vencimento=self.hoje,
        ) for _ in range(3)]
        debitos = [Pagamentos.objects.create(
            ticket_pagamento=ticket, tipo='T', valor_pagamento=Decimal('3.03'),
            data_vencimento=self.hoje,
        ) for _ in range(3)]
        filtros = {'situacao': 'aberto', 'periodo': '30'}
        primeira = self.consultar(filtros)
        pagina = primeira.context['page_obj']
        self.assertEqual(pagina.paginator.count, 29)
        self.assertEqual(pagina.paginator.per_page, 25)
        self.assertIsInstance(pagina.paginator.object_list, QuerySet)
        self.assertEqual(len(pagina.object_list), 25)
        segunda = self.consultar({**filtros, 'page': 2})
        self.assertEqual(len(segunda.context['page_obj'].object_list), 4)
        self.assertFalse(self.identidades(primeira) & self.identidades(segunda))
        self.assertEqual(self.identidades(primeira) | self.identidades(segunda), {
            *(('manual', 'credito', item.pk) for item in manuais),
            *(('ticket', 'credito', item.pk) for item in creditos),
            *(('ticket', 'debito', item.pk) for item in debitos),
        })
        for response in (primeira, segunda):
            self.assert_totais(response, credito='29.29', debito='9.09',
                               a_receber='29.29', a_pagar='9.09')
        repetida = self.consultar(filtros)
        self.assertEqual(
            [(r['origem'], r['operacao'], r['origem_id']) for r in primeira.context['lancamentos']],
            [(r['origem'], r['operacao'], r['origem_id']) for r in repetida.context['lancamentos']],
        )

    def test_descricoes_manuais_sao_escapadas(self):
        self.manual(descricao='<script>alert("manual")</script>',
                    contraparte='<img src=x onerror=alert(1)>')
        response = self.consultar()
        self.assertNotContains(response, '<script>alert("manual")</script>')
        self.assertNotContains(response, '<img src=x onerror=alert(1)>')
        self.assertContains(response, '&lt;script&gt;')
        self.assertContains(response, '&lt;img')

    def test_cadastro_e_edicao_preservam_consulta_sem_redirecionar_para_outro_site(self):
        filtros = {'operacao': 'credito', 'situacao': 'aberto', 'periodo': '30', 'page': '2'}
        query = '&'.join(f'{nome}={valor}' for nome, valor in filtros.items())
        url = f'{self.novo_url}?{query}&next=https://externo.example.invalid&empresa={self.outra_empresa.pk}'
        response = self.client.post(url, self.dados(next='https://externo.example.invalid'))
        self.assertEqual(response.status_code, 302)
        destino = urlsplit(response.url)
        self.assertEqual(destino.path, self.url)
        self.assertEqual(destino.netloc, '')
        self.assertEqual(parse_qs(destino.query), {nome: [valor] for nome, valor in filtros.items()})
        manual = LancamentoManual.objects.get()
        editar = reverse('financeiro:editar-manual', args=[manual.pk])
        response = self.client.post(f'{editar}?{query}&next=https://externo.example.invalid',
                                    self.dados(valor='13.13'))
        self.assertEqual(response.status_code, 302)
        destino = urlsplit(response.url)
        self.assertEqual(destino.path, self.url)
        self.assertEqual(destino.netloc, '')
        self.assertEqual(parse_qs(destino.query), {nome: [valor] for nome, valor in filtros.items()})

    def test_post_exige_csrf_e_rotas_nao_aceitam_metodos_inesperados(self):
        manual = self.manual()
        editar = reverse('financeiro:editar-manual', args=[manual.pk])
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.gestor)
        antes = list(LancamentoManual.objects.values())
        for url in (self.novo_url, editar):
            with self.subTest(url=url):
                self.assertEqual(protegido.post(url, self.dados()).status_code, 403)
                self.assertEqual(self.client.delete(url).status_code, 405)
                self.assertEqual(self.client.put(url, data='{}', content_type='application/json').status_code, 405)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)

    def test_indice_prepara_modal_sem_erros_e_preserva_filtros_e_pagina(self):
        for _ in range(26):
            self.manual()
        filtros = {
            'operacao': 'credito', 'situacao': 'aberto', 'periodo': 'personalizado',
            'data_inicio': self.hoje.isoformat(), 'data_fim': self.hoje.isoformat(),
            'page': '2',
        }
        response = self.consultar({
            **filtros, 'empresa': self.outra_empresa.pk,
            'next': 'https://externo.example.invalid',
        })
        manual_form = response.context['manual_form']
        self.assertIsInstance(manual_form, LancamentoManualForm)
        self.assertFalse(manual_form.is_bound)
        self.assertFalse(manual_form.errors)
        self.assertNotIn('empresa', manual_form.fields)
        self.assertFalse(response.context['reabrir_novo_lancamento'])
        self.assertEqual(response.context['page_obj'].number, 2)
        destino = urlsplit(response.context['novo_lancamento_url'])
        self.assertEqual(destino.path, self.novo_url)
        self.assertEqual(destino.netloc, '')
        self.assertEqual(parse_qs(destino.query), {
            nome: [valor] for nome, valor in filtros.items()
        })
        self.assertEqual(LancamentoManual.objects.count(), 26)

    def test_modal_invalido_preserva_dados_e_erros_sem_perder_listagem_da_empresa(self):
        proprio = self.manual(valor='10.11')
        estrangeiro = self.manual(
            valor='999.99', empresa=self.outra_empresa,
            descricao='Descrição restrita de outra empresa no modal',
        )
        antes = list(LancamentoManual.objects.values())
        dados = self.dados(
            valor='-1.00', descricao='Descrição digitada antes do erro',
            contraparte='Favorecido digitado antes do erro', apresentacao='modal',
            empresa=self.outra_empresa.pk, criado_por=self.admin.pk,
        )
        response = self.client.post(
            f'{self.novo_url}?operacao=credito&situacao=aberto&periodo=todos', dados,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'financeiro/index.html')
        form = response.context['manual_form']
        self.assertTrue(form.is_bound)
        self.assertIn('valor', form.errors)
        self.assertEqual(form['descricao'].value(), dados['descricao'])
        self.assertEqual(form['contraparte'].value(), dados['contraparte'])
        self.assertEqual(form['data_vencimento'].value(), dados['data_vencimento'])
        self.assertEqual(form['valor'].value(), dados['valor'])
        self.assertNotIn('empresa', form.fields)
        self.assertTrue(response.context['reabrir_novo_lancamento'])
        filtros_form = response.context['form']
        self.assertIsNot(form, filtros_form)
        self.assertTrue(filtros_form.is_valid())
        self.assertEqual(filtros_form.cleaned_data['operacao'], 'credito')
        self.assertEqual(filtros_form.cleaned_data['situacao'], 'aberto')
        self.assert_manuais(response, [proprio])
        self.assert_totais(response, credito='10.11', a_receber='10.11')
        self.assertNotContains(response, estrangeiro.descricao)
        self.assertEqual(list(LancamentoManual.objects.values()), antes)

    def test_modal_invalido_com_intervalo_invalido_preserva_erros_e_oculta_resultados(self):
        manual = self.manual(valor='77.77', descricao='Não mostrar com filtro inválido')
        inicio = self.hoje.isoformat()
        fim = (self.hoje - timedelta(days=1)).isoformat()
        response = self.client.post(
            f'{self.novo_url}?periodo=personalizado&data_inicio={inicio}&data_fim={fim}',
            self.dados(valor='0', descricao='Dados preservados com dois erros', apresentacao='modal'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, 'financeiro/index.html')
        self.assertTrue(response.context['form'].errors)
        self.assertIn('valor', response.context['manual_form'].errors)
        self.assertEqual(response.context['manual_form']['descricao'].value(),
                         'Dados preservados com dois erros')
        self.assertTrue(response.context['reabrir_novo_lancamento'])
        self.assert_manuais(response, [])
        self.assertEqual(response.context['totais']['quantidade'], 0)
        self.assert_totais(response, credito=0, debito=0, recebido=0, pago=0,
                           a_receber=0, a_pagar=0, vencido_credito=0, vencido_debito=0)
        self.assertNotContains(response, manual.descricao, status_code=400)
        self.assertEqual(LancamentoManual.objects.count(), 1)

    def test_modal_valido_exige_csrf_e_cria_na_empresa_preservando_retorno_seguro(self):
        protegido = Client(enforce_csrf_checks=True)
        protegido.force_login(self.gestor)
        response = protegido.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('csrftoken', protegido.cookies)
        token = protegido.cookies['csrftoken'].value
        filtros = {'operacao': 'credito', 'situacao': 'aberto', 'periodo': '30', 'page': '2'}
        query = '&'.join(f'{nome}={valor}' for nome, valor in filtros.items())
        url = f'{self.novo_url}?{query}&next=https://externo.example.invalid&empresa={self.outra_empresa.pk}'
        dados = self.dados(apresentacao='modal', empresa=self.outra_empresa.pk,
                           criado_por=self.admin.pk)
        self.assertEqual(protegido.post(url, dados).status_code, 403)
        self.assertFalse(LancamentoManual.objects.exists())
        response = protegido.post(url, {**dados, 'csrfmiddlewaretoken': token})
        self.assertEqual(response.status_code, 302)
        destino = urlsplit(response.url)
        self.assertEqual(destino.path, self.url)
        self.assertEqual(destino.netloc, '')
        self.assertEqual(parse_qs(destino.query), {nome: [valor] for nome, valor in filtros.items()})
        lancamento = LancamentoManual.objects.get()
        self.assertEqual(lancamento.empresa_id, self.empresa.pk)
        self.assertEqual(lancamento.criado_por_id, self.gestor.pk)
        self.assertEqual(lancamento.descricao, dados['descricao'])
        self.assertEqual(lancamento.valor, Decimal('123.45'))
        self.assertFalse(Ticket.objects.exists())

    def test_fallback_e_edicao_continuam_em_pagina_propria_apos_erros(self):
        manual = self.manual()
        antes = list(LancamentoManual.objects.values())
        for url, dados in (
            (self.novo_url, self.dados(valor='0', descricao='Cadastro sem JavaScript')),
            (reverse('financeiro:editar-manual', args=[manual.pk]),
             self.dados(valor='0', descricao='Edição em página própria', apresentacao='modal')),
        ):
            with self.subTest(url=url):
                response = self.client.post(url, dados)
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'financeiro/lancamento-manual.html')
                self.assertTemplateNotUsed(response, 'financeiro/index.html')
                self.assertIsInstance(response.context['form'], LancamentoManualForm)
                self.assertIn('valor', response.context['form'].errors)
                self.assertEqual(response.context['form']['descricao'].value(), dados['descricao'])
        self.assertEqual(list(LancamentoManual.objects.values()), antes)
