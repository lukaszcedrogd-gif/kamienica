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
        fields = ['name', 'lastname', 'pesel', 'email', 'phone', 'role']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'lastname': forms.TextInput(attrs={'class': 'form-control'}),
            'pesel': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-control'}),
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

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not re.match(r'^\+?[\d\s-]{9,}$', phone):
            raise ValidationError("Wprowadź poprawny numer telefonu (dozwolone cyfry, spacje, myślniki i opcjonalny '+').")
        return phone

class DateInput(forms.DateInput):
    input_type = 'date'

class AgreementForm(forms.ModelForm):
    class Meta:
        model = Agreement
        fields = '__all__'
        widgets = {
            'signing_date': DateInput(),
            'start_date': DateInput(),
            'end_date': DateInput(),
        }

class LokalForm(forms.ModelForm):
    class Meta:
        model = Lokal
        fields = '__all__'
        widgets = {
            'unit_number': forms.TextInput(attrs={'class': 'form-control'}),
            'size_sqm': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'meter_count_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
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
    csv_file = forms.FileField()
