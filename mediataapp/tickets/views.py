from django.shortcuts import render

# Create your views here.
def tickets(request):
    return render(request, 'tickets/index-tickets.html')