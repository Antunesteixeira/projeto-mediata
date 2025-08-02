from django.shortcuts import render, redirect
from .models import Insumos
from .forms import InsumoForm
from django.contrib import messages


# Create your views here.
def insumos(request):
    insumos_obj = Insumos.objects.all()
    if request.method == "POST":
        form = InsumoForm(request.POST)
        if form.is_valid():
            insumos = form.save(commit=False)
            insumos.save()
            messages.add_message(request, messages.SUCCESS, "Insumo cadastrado com sucesso!")
            return redirect('index-insumos')
        else:
            messages.add_message(request, messages.ERROR, "Não foi possível cadastrar o insumo, revise os dados!")
            return redirect('index-insumos')
        
    else:
        form = InsumoForm()
    
    context = {
        'form': form,
        'insumos': insumos_obj,
    }
    return render(request, 'insumos/index-insumos.html', context)

def editar_insumos(request, id):
    insumo = Insumos.objects.get(id=id)