from django.shortcuts import render
from core.models import User

def user_list(request):
    users = User.objects.all()
    return render(request, 'users/user_list.html', {'users': users})

