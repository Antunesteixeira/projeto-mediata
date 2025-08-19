from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from .models import Insumos
from .forms import InsumoForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import login_required

from django.db.models import ProtectedError

from django.http import JsonResponse

from django.db.models import Q

@login_required
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

@login_required
def editar_insumos(request, id):
    insumo = Insumos.objects.get(id=id)
    insumos = Insumos.objects.all()
    form = InsumoForm(request.POST or None, instance=insumo)

    if form.is_valid():
        # Verifica se os dados do formulário foram alterados
        if form.has_changed(): 
            insumo = form.save(commit=False)
            insumo.save()
            messages.success(request, f"Insumo {insumo.codigo.upper()} - {insumo.insumo.upper()} atualizado com sucesso!")

        else:
            messages.info(request, "Nenhuma alteração foi detectada.")
            
        return redirect('index-insumos')

    context = {
        'form': form,
        'insumo': insumo,
        'insumos': insumos,
    }
    #return HttpResponse(insumo.valor_unit)
    return render(request, 'insumos/index-insumos.html', context)

@login_required
def deletar_insumo(request, id):
    insumo = get_object_or_404(Insumos, id=id)

    # opcional: checar permissão extra, ex:
    # if not request.user.has_perm('app.delete_ticket'):
    #     messages.error(request, "Você não tem permissão para excluir este ticket.")
    #     return redirect('exibir-ticket', key=key)

    try:
        insumo.delete()
        messages.success(request, f"O Insumo #{insumo.insumo} foi deletado com sucesso!")
    except ProtectedError:
        messages.error(request, "Não foi possível deletar o ticket porque há objetos relacionados protegendo-o.")
    return redirect('index-insumos') 
