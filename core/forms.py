import re
from django import forms
from django.core.exceptions import ValidationError
from .models import User, Agreement, Lokal, MeterReading

class UserForm(forms.ModelForm):
    email = forms.EmailField(
        required=False, 
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['name', 'lastname', 'pesel', 'email', 'phone', 'role', 'is_admin']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'lastname': forms.TextInput(attrs={'class': 'form-control'}),
            'pesel': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
            'is_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            return name.title()
        return name

    def clean_lastname(self):
        lastname = self.cleaned_data.get('lastname')
        if lastname:
            return lastname.title()
        return lastname

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            qs = User.all_objects.filter(email__iexact=email)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Użytkownik z tym adresem e-mail już istnieje w systemie.")
        return email

    def clean_pesel(self):
        pesel = self.cleaned_data.get('pesel')
        if pesel:
            qs = User.all_objects.filter(pesel=pesel)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError("Użytkownik z tym numerem PESEL już istnieje w systemie.")
        return pesel

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not re.match(r'^\+?[\d\s-]{9,}$', phone):
            raise ValidationError("Wprowadź poprawny numer telefonu (dozwolone cyfry, spacje, myślniki i opcjonalny '+').")
        return phone

class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None, format=None):
        final_attrs = {'class': 'form-control'}
        if attrs:
            final_attrs.update(attrs)
        # Wymuszenie formatu YYYY-MM-DD, który jest wymagany przez input type="date" w HTML5
        super().__init__(attrs=final_attrs, format=format or '%Y-%m-%d')

class AgreementForm(forms.ModelForm):
    class Meta:
        model = Agreement
        exclude = ['is_active']
        widgets = {
            'user': forms.Select(attrs={'class': 'form-control'}),
            'lokal': forms.Select(attrs={'class': 'form-control'}),
            'signing_date': DateInput(),
            'start_date': DateInput(),
            'end_date': DateInput(),
            'rent_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'deposit_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
            'old_agreement': forms.Select(attrs={'class': 'form-control'}),
            'additional_info': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'number_of_occupants': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class LokalForm(forms.ModelForm):
    class Meta:
        model = Lokal
        fields = '__all__'
        widgets = {
            'unit_number': forms.TextInput(attrs={'class': 'form-control'}),
            'size_sqm': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

class MeterReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ['reading_date', 'value']
        widgets = {
            'reading_date': DateInput(),
            'value': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class CSVUploadForm(forms.Form):
    AI_CHOICES = [
        ('rule_only', 'Tylko reguły (bez AI)'),
        ('conflict_only', 'AI tylko przy konfliktach'),
        ('conflict_and_unprocessed', 'AI przy konfliktach i nieprzetworzonych'),
    ]

    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    ai_mode = forms.ChoiceField(
        choices=AI_CHOICES,
        initial='conflict_and_unprocessed',
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tryb AI',
        required=False,
    )
