from django.forms import modelform_factory
from django.shortcuts import render, redirect, get_object_or_404

from ..decorators import require_admin
from ..models import CategorizationRule


@require_admin
def rule_list(request):
    rules = CategorizationRule.objects.all().order_by('keywords')
    return render(request, 'core/rule_list.html', {'rules': rules})


@require_admin
def edit_rule(request, pk):
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


@require_admin
def delete_rule(request, pk):
    rule = get_object_or_404(CategorizationRule, pk=pk)
    if request.method == 'POST':
        rule.delete()
        return redirect('rule_list')
    return render(request, 'core/confirm_delete.html', {'object': rule, 'type': 'regułę', 'cancel_url': 'rule_list'})
