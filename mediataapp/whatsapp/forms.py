from django import forms


class SelecionarEmpresaWhatsAppForm(forms.Form):
    empresa_id = forms.IntegerField(required=False, min_value=1)
