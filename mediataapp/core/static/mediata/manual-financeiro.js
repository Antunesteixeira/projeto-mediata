(function () {
    'use strict';

    document.querySelectorAll('[data-manual-financeiro]').forEach(function (form) {
        const operacao = form.elements.namedItem('operacao');
        const liquidado = form.elements.namedItem('liquidado');
        const quitacao = form.elements.namedItem('data_quitacao');
        const label = form.querySelector('[data-settlement-label]');
        const help = form.querySelector('[data-settlement-help]');
        if (!operacao || !liquidado) return;

        function atualizarQuitacao() {
            const credito = operacao.value === 'credito';
            if (label) label.textContent = credito ? 'Recebido' : 'Pago';
            if (help) {
                help.textContent = credito
                    ? 'Marque quando o valor tiver sido efetivamente recebido.'
                    : 'Marque quando o valor tiver sido efetivamente pago.';
            }
            if (quitacao) {
                quitacao.required = liquidado.checked;
                quitacao.setAttribute('aria-required', liquidado.checked ? 'true' : 'false');
            }
        }

        operacao.addEventListener('change', atualizarQuitacao);
        liquidado.addEventListener('change', atualizarQuitacao);
        atualizarQuitacao();
    });

    const modal = document.getElementById('novoLancamentoModal');
    if (!modal || !window.bootstrap || !window.bootstrap.Modal) return;

    modal.addEventListener('shown.bs.modal', function () {
        const firstField = modal.querySelector('[aria-invalid="true"]') ||
            modal.querySelector('[name="empresa"]:not(:disabled), [name="operacao"]');
        if (firstField) firstField.focus();
    });

    if (modal.dataset.reabrir === 'true') {
        window.bootstrap.Modal.getOrCreateInstance(modal).show();
    }
}());
