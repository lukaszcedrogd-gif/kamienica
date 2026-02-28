from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.forms import modelform_factory
from django.shortcuts import render, redirect, get_object_or_404

from ..models import CategorizationRule


@login_required
def rule_list(request):
    """
    Wyświetla listę wszystkich reguł kategoryzacji.
    """
    rules = CategorizationRule.objects.all().order_by('keywords')
    return render(request, 'core/rule_list.html', {'rules': rules})

@login_required
def edit_rule(request, pk):
    """
    Edytuje istniejącą regułę kategoryzacji.
    """
    rule = get_object_or_404(CategorizationRule, pk=pk)
    RuleForm = modelform_factory(CategorizationRule, fields=['keywords', 'title'])

    if request.method == 'POST':
        form = RuleForm(request.POST, instance=rule)
        if form.is_valid():
            form.save()
            return redirect('rule_list')
    else:
        form = RuleForm(instance=rule)
    return render(request, 'core/rule_form.html', {'form': form, 'title': f'Edytuj regułę: {rule.keywords}'})

@login_required
def delete_rule(request, pk):
    """
    Usuwa regułę kategoryzacji. Wymaga potwierdzenia (metoda POST).
    """
    rule = get_object_or_404(CategorizationRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        return redirect('rule_list')
    return render(request, 'core/confirm_delete.html', {'object': rule, 'type': 'regułę', 'cancel_url': 'rule_list'})
