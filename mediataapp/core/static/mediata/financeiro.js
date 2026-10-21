(function () {
    'use strict';

    var form = document.getElementById('finance-filter-form');
    if (!form) return;

    var periodo = form.elements.periodo;
    var inicio = form.elements.data_inicio;
    var fim = form.elements.data_fim;
    if (!periodo || !inicio || !fim) return;

    // Use the server's calendar day; UTC conversion can change Brazilian dates.
    function addDays(isoDate, days) {
        var parts = isoDate.split('-').map(Number);
        if (parts.length !== 3 || parts.some(function (part) { return !Number.isFinite(part); })) return '';
        var date = new Date(parts[0], parts[1] - 1, parts[2], 12);
        date.setDate(date.getDate() + days);
        return String(date.getFullYear()) + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    }

    function applyPeriod() {
        if (periodo.value === 'todos') {
            inicio.value = '';
            fim.value = '';
        } else if (['30', '60', '90'].indexOf(periodo.value) !== -1) {
            inicio.value = form.dataset.hoje;
            fim.value = addDays(form.dataset.hoje, Number(periodo.value) - 1);
        }
    }

    periodo.addEventListener('change', applyPeriod);
    [inicio, fim].forEach(function (field) {
        field.setAttribute('aria-describedby', 'finance-period-help');
        field.addEventListener('input', function () { periodo.value = 'personalizado'; });
        field.addEventListener('change', function () { periodo.value = 'personalizado'; });
    });
    periodo.setAttribute('aria-describedby', 'finance-period-help');
}());
