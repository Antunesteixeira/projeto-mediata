from datetime import date, datetime, timezone as datetime_timezone
from importlib import import_module
from queue import Queue
from threading import Barrier, Thread
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, connections, IntegrityError, transaction
from django.db.migrations.state import ProjectState
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rolepermissions.roles import assign_role
from usuarios.test_helpers import criar_empresa, vincular_usuario

from .models import SequenciaTicket, Ticket


OCTOBER = date(2026, 10, 13)


@override_settings(TIME_ZONE='America/Sao_Paulo')
class NumeracaoTicketTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = criar_empresa()
        cls.operator = User.objects.create_user(username='operador_numeracao_fixture')
        assign_role(cls.operator, 'operador')
        vincular_usuario(cls.operator, cls.company)
        cls.subscriber = User.objects.create_user(username='assinante_numeracao_fixture')
        assign_role(cls.subscriber, 'assinante')

    def setUp(self):
        current_timezone = timezone.override('America/Sao_Paulo')
        current_timezone.__enter__()
        self.addCleanup(current_timezone.__exit__, None, None, None)

    def create_ticket(self, number='', day=OCTOBER, **changes):
        fields = {
            'ticket': number, 'usuario': self.operator, 'empresa': self.company,
            'descricao': 'Solicitação fictícia para numeração',
        }
        fields.update(changes)
        with patch('django.utils.timezone.localdate', return_value=day):
            return Ticket.objects.create(**fields)

    def numbering_snapshot(self):
        return {
            'tickets': list(Ticket.objects.order_by('pk').values()),
            'sequences': list(SequenciaTicket.objects.order_by('prefixo').values()),
        }

    def post_ticket(self, user, number=None):
        self.client.force_login(user)
        payload = {
            'descricao': f'Solicitação de {user.username}',
            'status': 'L', 'data_finalizar': '2026-10-31',
        }
        if number is not None:
            payload['ticket'] = number
        with patch('django.utils.timezone.localdate', return_value=OCTOBER):
            return self.client.post(reverse('cadastro-ticket'), payload)

    def assert_successful_post(self, response):
        self.assertEqual(
            response.status_code, 302,
            response.context['form'].errors if response.status_code == 200 else None,
        )

    def test_blank_and_whitespace_numbers_generate_monthly_codes(self):
        for index, number in enumerate(('', '   ', '\t\n '), start=1):
            with self.subTest(number=repr(number)):
                ticket = self.create_ticket(number)
                self.assertEqual(ticket.ticket, f'2610{index:03d}')
        with patch('django.utils.timezone.localdate', return_value=OCTOBER):
            omitted = Ticket.objects.create(usuario=self.operator, descricao='Número omitido')
        self.assertEqual(omitted.ticket, '2610004')
        self.assertEqual(SequenciaTicket.objects.get(prefixo='2610').ultimo_numero, 4)

    def test_manual_code_is_preserved_and_duplicate_is_rejected(self):
        ticket = self.create_ticket('MANUAL-001')
        self.assertEqual(ticket.ticket, 'MANUAL-001')
        before = self.numbering_snapshot()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_ticket('MANUAL-001')
        self.assertEqual(self.numbering_snapshot(), before)

    def test_manual_monthly_code_reserves_its_sequence(self):
        first = self.create_ticket()
        manual = self.create_ticket('2610111')
        following = self.create_ticket()
        self.assertEqual(first.ticket, '2610001')
        self.assertEqual(manual.ticket, '2610111')
        self.assertEqual(following.ticket, '2610112')
        self.assertEqual(SequenciaTicket.objects.get(prefixo='2610').ultimo_numero, 112)

    def test_codes_outside_ascii_monthly_pattern_do_not_reserve_a_sequence(self):
        for number in ('MANUAL-002', '2613001', '2610９９９', '26101000'):
            with self.subTest(number=number):
                ticket = self.create_ticket(number)
                self.assertEqual(ticket.ticket, number)
        self.assertFalse(SequenciaTicket.objects.exists())
        self.assertEqual(self.create_ticket().ticket, '2610001')

    def test_utc_month_boundary_uses_the_date_in_sao_paulo(self):
        # 01:30 UTC ainda corresponde a 31/10 em São Paulo.
        with patch('django.utils.timezone.now', return_value=datetime(
            2026, 11, 1, 1, 30, tzinfo=datetime_timezone.utc,
        )):
            october_ticket = Ticket.objects.create(descricao='Antes da meia-noite local')
        with patch('django.utils.timezone.now', return_value=datetime(
            2026, 11, 1, 3, 30, tzinfo=datetime_timezone.utc,
        )):
            november_ticket = Ticket.objects.create(descricao='Depois da meia-noite local')
        self.assertEqual(october_ticket.ticket, '2610001')
        self.assertEqual(november_ticket.ticket, '2611001')

    def test_sequence_increments_and_restarts_for_each_month_and_year(self):
        self.assertEqual(self.create_ticket().ticket, '2610001')
        self.assertEqual(self.create_ticket().ticket, '2610002')
        self.assertEqual(self.create_ticket(day=date(2026, 11, 1)).ticket, '2611001')
        self.assertEqual(self.create_ticket(day=date(2027, 1, 1)).ticket, '2701001')
        self.assertEqual(self.create_ticket().ticket, '2610003')
        self.assertEqual(dict(SequenciaTicket.objects.values_list('prefixo', 'ultimo_numero')), {
            '2610': 3, '2611': 1, '2701': 1,
        })

    def test_legacy_numbers_use_highest_valid_suffix_without_rewriting_records(self):
        legacy = Ticket.objects.bulk_create([
            Ticket(ticket=number, descricao=f'Ticket legado {number}')
            for number in ('2610003', '2610090', '2610111', '2610ABC', '2610９９９', '26101000')
        ])
        before = {ticket.pk: ticket.ticket for ticket in legacy}
        self.assertFalse(SequenciaTicket.objects.filter(prefixo='2610').exists())
        created = self.create_ticket()
        self.assertEqual(created.ticket, '2610112')
        self.assertEqual(dict(Ticket.objects.filter(pk__in=before).values_list('pk', 'ticket')), before)

    def test_migration_seed_uses_historical_models_and_preserves_legacy_codes(self):
        Ticket.objects.bulk_create([
            Ticket(ticket=number, descricao=f'Código legado {number}')
            for number in (
                '2610002', '2610111', '2610009', '2611001', '2611042', '2512999',
                '', 'MANUAL-004', '2613999', '2610９９９', '26101000', '2611999X',
            )
        ])
        # Os contadores existentes também preservam números de tickets já excluídos.
        SequenciaTicket.objects.create(prefixo='2611', ultimo_numero=50)
        SequenciaTicket.objects.create(prefixo='2609', ultimo_numero=321)
        before_tickets = self.numbering_snapshot()['tickets']
        migration = import_module('tickets.migrations.0036_sequenciaticket')
        historical_apps = ProjectState.from_apps(apps).apps
        # Só executa a seed de dados; a tabela já existe no banco de testes.
        migration.iniciar_sequencias(historical_apps, connection.schema_editor())

        self.assertEqual(self.numbering_snapshot()['tickets'], before_tickets)
        self.assertEqual(dict(SequenciaTicket.objects.values_list('prefixo', 'ultimo_numero')), {
            '2610': 111, '2611': 50, '2512': 999, '2609': 321,
        })
        seeded = self.numbering_snapshot()
        migration.iniciar_sequencias(historical_apps, connection.schema_editor())
        self.assertEqual(self.numbering_snapshot(), seeded)

    def test_existing_number_is_preserved_in_normal_and_partial_updates(self):
        automatic = self.create_ticket()
        manual = self.create_ticket('MANUAL-003')
        before_sequences = list(SequenciaTicket.objects.values())
        with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 1)):
            for ticket in (automatic, manual):
                with self.subTest(number=ticket.ticket):
                    original_number = ticket.ticket
                    ticket.descricao = 'Descrição alterada'
                    ticket.save()
                    ticket.status = 'A'
                    ticket.save(update_fields=['status'])
                    ticket.refresh_from_db()
                    self.assertEqual(ticket.ticket, original_number)
                    self.assertEqual(ticket.status, 'A')
        self.assertEqual(list(SequenciaTicket.objects.values()), before_sequences)

    def test_blank_number_on_edit_preserves_saved_code_without_allocating(self):
        ticket = self.create_ticket()
        original_number = ticket.ticket
        before_sequences = list(SequenciaTicket.objects.values())
        for partial in (False, True):
            with self.subTest(partial=partial), patch(
                'django.utils.timezone.localdate', return_value=date(2026, 11, 1),
            ):
                ticket.ticket = '   '
                ticket.status = 'V'
                ticket.save(update_fields=['status'] if partial else None)
                ticket.refresh_from_db()
                self.assertEqual(ticket.ticket, original_number)
                self.assertEqual(ticket.status, 'V')
        self.assertEqual(list(SequenciaTicket.objects.values()), before_sequences)

    def test_deleting_latest_or_all_monthly_tickets_does_not_reuse_numbers(self):
        first = self.create_ticket()
        latest = self.create_ticket()
        latest.delete()
        following = self.create_ticket()
        self.assertEqual(following.ticket, '2610003')
        first.delete()
        following.delete()
        self.assertEqual(self.create_ticket().ticket, '2610004')
        self.assertEqual(SequenciaTicket.objects.get(prefixo='2610').ultimo_numero, 4)

    def test_monthly_limit_raises_validation_error_without_database_changes(self):
        self.create_ticket('2610999')
        before = self.numbering_snapshot()
        with self.assertRaises(ValidationError) as error:
            self.create_ticket()
        self.assertIn('999', str(error.exception))
        self.assertEqual(self.numbering_snapshot(), before)

    def test_failed_ticket_insert_rolls_back_the_reserved_number(self):
        first = self.create_ticket()
        before = self.numbering_snapshot()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_ticket(key=first.key)
        self.assertEqual(self.numbering_snapshot(), before)
        self.assertEqual(self.create_ticket().ticket, '2610002')

    def test_both_roles_can_post_blank_number_and_receive_generated_codes(self):
        for index, user in enumerate((self.operator, self.subscriber), start=1):
            with self.subTest(user=user.username):
                response = self.post_ticket(user)
                self.assert_successful_post(response)
                created = Ticket.objects.get(usuario=user)
                self.assertEqual(created.ticket, f'2610{index:03d}')
                self.assertEqual(created.status, 'L')

    def test_legacy_blank_number_does_not_block_new_forms_for_either_role(self):
        legacy = Ticket.objects.bulk_create([
            Ticket(ticket='', descricao='Ticket legado com código vazio'),
        ])[0]
        for index, user in enumerate((self.operator, self.subscriber), start=1):
            with self.subTest(user=user.username):
                response = self.post_ticket(user, '' if index == 1 else '   ')
                self.assert_successful_post(response)
                self.assertEqual(Ticket.objects.get(usuario=user).ticket, f'2610{index:03d}')
                legacy.refresh_from_db()
                self.assertEqual(legacy.ticket, '')
        self.assertEqual(Ticket.objects.count(), 3)

    def test_both_roles_can_post_a_manual_number(self):
        for user, number in ((self.operator, 'MANOP001'), (self.subscriber, 'MANASS001')):
            with self.subTest(user=user.username):
                response = self.post_ticket(user, number)
                self.assert_successful_post(response)
                self.assertEqual(Ticket.objects.get(usuario=user).ticket, number)
        before = self.numbering_snapshot()
        response = self.post_ticket(self.subscriber, 'MANOP001')
        self.assertEqual(response.status_code, 200)
        self.assertIn('ticket', response.context['form'].errors)
        self.assertEqual(self.numbering_snapshot(), before)

    def test_exhausted_sequence_is_a_visible_form_error_for_both_roles(self):
        SequenciaTicket.objects.create(prefixo='2610', ultimo_numero=999)
        before = self.numbering_snapshot()
        for user in (self.operator, self.subscriber):
            with self.subTest(user=user.username):
                response = self.post_ticket(user)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '999')
                self.assertEqual(self.numbering_snapshot(), before)

    def test_editing_legacy_blank_ticket_with_exhausted_sequence_returns_field_error(self):
        legacy = Ticket.objects.bulk_create([
            Ticket(ticket='', usuario=self.operator, empresa=self.company, descricao='Descrição legada original'),
        ])[0]
        SequenciaTicket.objects.create(prefixo='2610', ultimo_numero=999)
        before = self.numbering_snapshot()
        self.client.force_login(self.operator)
        with patch('django.utils.timezone.localdate', return_value=OCTOBER):
            response = self.client.post(reverse('editar-ticket', kwargs={'key': legacy.key}), {
                'ticket': '', 'descricao': 'Descrição que não deve ser salva',
                'status': 'A', 'data_finalizar': '2026-10-31',
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn('ticket', response.context['form'].errors)
        self.assertContains(response, '999')
        self.assertEqual(self.numbering_snapshot(), before)

    def test_edit_post_with_blank_number_preserves_existing_manual_and_automatic_codes(self):
        tickets = (self.create_ticket(), self.create_ticket('MANEDIT01'))
        sequences_before = list(SequenciaTicket.objects.order_by('prefixo').values())
        self.client.force_login(self.operator)
        for ticket in tickets:
            with self.subTest(number=ticket.ticket):
                original_number = ticket.ticket
                with patch('django.utils.timezone.localdate', return_value=date(2026, 11, 1)):
                    response = self.client.post(reverse('editar-ticket', kwargs={'key': ticket.key}), {
                        'ticket': '', 'descricao': 'Descrição atualizada pelo formulário',
                        'status': 'A', 'data_finalizar': '2026-11-30',
                    })
                self.assertRedirects(
                    response, reverse('index-tickets'), fetch_redirect_response=False,
                )
                ticket.refresh_from_db()
                self.assertEqual(ticket.ticket, original_number)
                self.assertEqual(ticket.descricao, 'Descrição atualizada pelo formulário')
                self.assertEqual(ticket.status, 'A')
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertEqual(list(SequenciaTicket.objects.order_by('prefixo').values()), sequences_before)


@skipUnless(connection.vendor == 'postgresql', 'Concorrência real exige PostgreSQL.')
@override_settings(TIME_ZONE='America/Sao_Paulo')
class NumeracaoConcorrenteTicketTests(TransactionTestCase):
    def create_concurrently(self):
        barrier = Barrier(2)
        outcomes = Queue()

        def create_ticket(index):
            database = connections['default']
            database.close()
            try:
                # Limita uma falha de locking à conexão isolada deste teste.
                with database.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                barrier.wait(timeout=10)
                ticket = Ticket(descricao=f'Solicitação concorrente fictícia {index}')
                ticket.save()
                outcomes.put(('created', ticket.pk, ticket.ticket))
            except Exception as error:
                outcomes.put(('error', type(error).__name__, str(error)))
            finally:
                database.close()

        threads = [Thread(target=create_ticket, args=(index,), daemon=True) for index in range(2)]
        with patch('django.utils.timezone.localdate', return_value=OCTOBER):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'Thread não encerrou no prazo.')
        results = [outcomes.get_nowait() for _ in range(outcomes.qsize())]
        self.assertEqual(len(results), 2, results)
        self.assertTrue(all(result[0] == 'created' for result in results), results)
        self.assertEqual(len({result[1] for result in results}), 2)
        return {result[2] for result in results}

    def test_two_first_creations_share_a_new_monthly_counter_safely(self):
        self.assertEqual(self.create_concurrently(), {'2610001', '2610002'})
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertEqual(SequenciaTicket.objects.get(prefixo='2610').ultimo_numero, 2)

    def test_concurrent_creations_increment_an_existing_counter_without_duplicates(self):
        with patch('django.utils.timezone.localdate', return_value=OCTOBER):
            first = Ticket.objects.create(descricao='Primeiro ticket fictício')
        self.assertEqual(first.ticket, '2610001')
        self.assertEqual(self.create_concurrently(), {'2610002', '2610003'})
        self.assertEqual(Ticket.objects.count(), 3)
        self.assertEqual(Ticket.objects.values('ticket').distinct().count(), 3)
        self.assertEqual(SequenciaTicket.objects.get(prefixo='2610').ultimo_numero, 3)
