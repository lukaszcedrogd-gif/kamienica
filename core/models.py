from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords
from .validators import validate_pesel

# --- Custom Manager for Soft Delete ---
class ActiveManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

# --- 1. Użytkownicy ---
class User(models.Model):
    ROLE_CHOICES = [
        ('wlasciciel', 'Właściciel'),
        ('lokator', 'Lokator'),
        ('byly_lokator', 'Były Lokator'),
        ('budynek', 'Budynek'),
    ]
   
    name = models.CharField("Imię", max_length=100)
    lastname = models.CharField("Nazwisko", max_length=100)
    # UWAGA: unique=True na polach null=True może zachowywać się różnie w zależności od bazy danych.
    # W PostgreSQL, NULLe nie są traktowane jako równe sobie, więc można mieć wiele NULLi.
    # Warto rozważyć własną logikę walidacji unikalności dla wartości nie-NULL.
    pesel = models.CharField(
        "PESEL", 
        max_length=11, 
        unique=True, 
        null=True, 
        blank=True,
        validators=[validate_pesel]
    )
    passport_number = models.CharField("Nr Paszportu", max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField("Adres e-mail", unique=True)
    phone = models.CharField("Telefon", max_length=30, blank=True)
    role = models.CharField("Rola", max_length=50, choices=ROLE_CHOICES)
    is_active = models.BooleanField("Aktywny", default=True)

    # Managers
    objects = ActiveManager()
    all_objects = models.Manager()

    # History
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Użytkownik"
        verbose_name_plural = "Użytkownicy"
        
    def __str__(self):
        return f"{self.name} {self.lastname} ({self.get_role_display()})"

# --- 2. Lokale ---
class Lokal(models.Model):
    unit_number = models.CharField("Numer mieszkania", max_length=10, unique=True, help_text="Np. '3a', '12'")
    size_sqm = models.DecimalField("Wielkość (m²)", max_digits=11, decimal_places=2)
    description = models.TextField("Opis zawartości", blank=True, help_text="Opis wyposażenia, stanu lokalu.")
    is_active = models.BooleanField("Aktywny", default=True)

    # Managers
    objects = ActiveManager()
    all_objects = models.Manager()

    # History
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Lokal"
        verbose_name_plural = "Lokale"
        
    def __str__(self):
        return f"Lokal nr {self.unit_number} ({self.size_sqm} m²)"

# --- 3. Umowy ---
class Agreement(models.Model):
    TYPE_CHOICES = [
        ('umowa', 'Umowa'),
        ('aneks', 'Aneks'),
    ]

    user = models.ForeignKey(User, verbose_name="Użytkownik (Lokator)", on_delete=models.PROTECT, related_name="agreements")
    lokal = models.ForeignKey(Lokal, verbose_name="Lokal", on_delete=models.PROTECT, related_name="agreements")
    
    signing_date = models.DateField("Data zawarcia")
    start_date = models.DateField("Data rozpoczęcia najmu")
    end_date = models.DateField("Data zakończenia najmu", null=True, blank=True)
    
    rent_amount = models.DecimalField("Kwota czynszu (nominalna)", max_digits=10, decimal_places=2)
    deposit_amount = models.DecimalField("Kwota kaucji", max_digits=10, decimal_places=2, null=True, blank=True)
    
    type = models.CharField("Rodzaj", max_length=20, choices=TYPE_CHOICES, default='umowa')
    old_agreement = models.ForeignKey(
        'self', 
        verbose_name="Stara umowa (dla aneksów)", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="aneks_agreements"
    )
    
    additional_info = models.TextField("Informacje dodatkowe", blank=True)
    number_of_occupants = models.IntegerField("Liczba osób zamieszkujących")
    is_active = models.BooleanField("Aktywny", default=True)

    # Managers
    objects = ActiveManager()
    all_objects = models.Manager()

    # History
    history = HistoricalRecords()

    class Meta:
        verbose_name = "Umowa"
        verbose_name_plural = "Umowy"
        
    def __str__(self):
        return f"{self.get_type_display()} dla lokalu {self.lokal.unit_number} ({self.user})"

# --- 4. Harmonogram Czynszów ---
class RentSchedule(models.Model): 
    agreement = models.ForeignKey(Agreement, verbose_name="Umowa", on_delete=models.CASCADE, related_name="rent_schedule")
    year_month = models.DateField("Miesiąc płatności", help_text="Dotyczy miesiąca, np. 2025-01-01")
    due_amount = models.DecimalField("Kwota do zapłaty", max_digits=10, decimal_places=2)
    description = models.CharField("Opis", max_length=255, blank=True, help_text="Np. 'Korekta za połowę miesiąca'")

    class Meta:
        verbose_name = "Harmonogram Czynszu"
        verbose_name_plural = "Harmonogramy Czynszów"
        unique_together = ('agreement', 'year_month')

    def __str__(self):
        return f"{self.agreement} - {self.year_month.strftime('%Y-%m')} - {self.due_amount} PLN"

# --- 5. Liczniki ---
class Meter(models.Model):
    METER_TYPE_CHOICES = [
        ('cold_water', 'Woda zimna'),
        ('hot_water', 'Woda ciepła'),
        ('electricity', 'Energia elektryczna'),
        ('gas', 'Gaz'),
        ('heat', 'Energia cieplna'),
    ]
    STATUS_CHOICES = [
        ('aktywny', 'Aktywny'),
        ('nieaktywny', 'Nieaktywny'),
    ]

    serial_number = models.CharField("Numer seryjny", max_length=50, unique=True)
    type = models.CharField("Typ licznika", max_length=50, choices=METER_TYPE_CHOICES)
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='aktywny')
    
    lokal = models.ForeignKey(
        Lokal, 
        verbose_name="Lokal", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="meters"
    )
    local_meter_number = models.IntegerField("Nr licznika w mieszkaniu", null=True, blank=True, help_text="Np. [1, 2] dla wody")

    class Meta:
        verbose_name = "Licznik"
        verbose_name_plural = "Liczniki"
        
    def __str__(self):
        if self.lokal:
            return f"{self.get_type_display()} ({self.serial_number}) - Lokal {self.lokal.unit_number}"
        return f"{self.get_type_display()} ({self.serial_number}) - Ogólny"
    
# --- 6. Odczyty Liczników ---
class MeterReading(models.Model): 
    meter = models.ForeignKey(Meter, verbose_name="Licznik", on_delete=models.CASCADE, related_name="readings")
    reading_date = models.DateField("Data odczytu")
    value = models.DecimalField("Wartość odczytu (m³, kWh)", max_digits=10, decimal_places=3)

    class Meta:
        verbose_name = "Odczyt Licznika"
        verbose_name_plural = "Odczyty Liczników"
        ordering = ['-reading_date']
        
    def __str__(self):
        return f"Odczyt {self.meter.serial_number} z dnia {self.reading_date} = {self.value}"

# --- 7. Reguły Naliczania Opłat (dawniej Koszty Stałe) ---
class FixedCost(models.Model):
    CALCULATION_METHOD_CHOICES = [
        ('per_person', 'Od osoby'),
        ('fixed_amount', 'Stała kwota (dla całej nieruchomości)'),
        ('per_unit', 'Za jednostkę (np. m³ wody)'),
    ]

    name = models.CharField("Nazwa reguły", max_length=150)
    calculation_method = models.CharField("Metoda obliczeń", max_length=50, choices=CALCULATION_METHOD_CHOICES)
    
    # Pola dla różnych metod obliczeń
    amount = models.DecimalField("Wartość", max_digits=10, decimal_places=4, help_text="Kwota od osoby, stała kwota lub cena za jednostkę")
    
    # Powiązanie z typem mediów (dla metody 'per_unit')
    meter_type = models.CharField(
        "Typ licznika (dla opłat 'za jednostkę')", 
        max_length=50, 
        choices=Meter.METER_TYPE_CHOICES, 
        null=True, 
        blank=True
    )

    effective_date = models.DateField("Data wejścia w życie", default=timezone.now)

    class Meta:
        verbose_name = "Reguła Naliczania Opłat"
        verbose_name_plural = "Reguły Naliczania Opłat"
        ordering = ['-effective_date']
        
    def __str__(self):
        return f"Reguła: {self.name} od {self.effective_date.strftime('%Y-%m-%d')}"


# --- 8. Transakcje Finansowe ---
class FinancialTransaction(models.Model):
    user = models.ForeignKey(
        User, 
        verbose_name="Użytkownik", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="transactions"
    )
    lokal = models.ForeignKey(
        Lokal, 
        verbose_name="Lokal", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="transactions"
    )
    
    
    amount = models.DecimalField("Kwota [+/-]", max_digits=10, decimal_places=2, help_text="Wpłata (przychód) to kwota dodatnia, wypłata (koszt) to kwota ujemna.")
    posting_date = models.DateField("Data księgowania", default=timezone.now) 
    description = models.TextField("Opis", blank=True)
    contractor = models.CharField("Kontrahent", max_length=255, blank=True, null=True)
    transaction_id = models.CharField("ID Transakcji", max_length=255, unique=True, null=True, blank=True)

    TITLE_CHOICES = [
        ('czynsz', 'czynsz'),
        ('oplaty', 'opłaty'),
        ('oplata_bankowa', 'opłata bankowa'),
        ('energia_klatka', 'energia klatka'),
        ('energia_m8', 'energię M8'),
        ('na_potrzeby_kamienicy', 'na potrzeby kamienicy'),
        ('naprawy_remonty', 'naprawy/remonty'),
        ('oplata_za_wode', 'opłata za wodę'),
        ('wywoz_smieci', 'wywóz śmieci'),
        ('sprzatanie', 'sprzątanie'),
        ('ogrodnik', 'ogrodnik'),
        ('ubezpieczenie', 'ubezpieczenie'),
        ('internet_telefon', 'internet/telefon'),
        ('elektryk', 'elektryk'),
        ('kominiarz', 'kominiarz'),
        ('piece_co', 'piece co'),
        ('podatek', 'podatek'),
        ('oplata_nie_stanowiaca_kosztu', 'opłata nie stanowiąca kosztu'),
    ]
    title = models.CharField("Tytułem", max_length=100, choices=TITLE_CHOICES, blank=True, null=True)

    class Meta:
        verbose_name = "Transakcja Finansowa"
        verbose_name_plural = "Transakcje Finansowe"
        ordering = ['-posting_date']

    def __str__(self):
        return f"Transakcja {self.amount} PLN ({self.posting_date.strftime('%Y-%m-%d')})"

    @property
    def is_split_payment(self):
        return self.transaction_id and '_split' in self.transaction_id

# --- 9. Reguły Kategoryzacji ---
class CategorizationRule(models.Model):
    keywords = models.CharField("Słowa kluczowe (oddzielone przecinkami)", max_length=255)
    title = models.CharField("Tytuł", max_length=100, choices=FinancialTransaction.TITLE_CHOICES)

    class Meta:
        verbose_name = "Reguła kategoryzacji"
        verbose_name_plural = "Reguły kategoryzacji"

    def __str__(self):
        return f"'{self.keywords}' -> '{self.get_title_display()}'"
        
# --- 10. Reguły Przypisania Lokalu (Nowe) ---
class LokalAssignmentRule(models.Model):
    keywords = models.CharField("Słowa kluczowe / Nr konta", max_length=255, help_text="Np. nazwisko, fragment opisu, numer konta bankowego")
    lokal = models.ForeignKey(Lokal, verbose_name="Przypisany Lokal", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Reguła przypisania lokalu"
        verbose_name_plural = "Reguły przypisania lokalu"

    def __str__(self):
        return f"'{self.keywords}' -> {self.lokal}"

# --- 11. Fotografie Lokalu ---
class LocalPhoto(models.Model):
    lokal = models.ForeignKey(Lokal, verbose_name="Lokal", on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(verbose_name="Zdjęcie", upload_to='lokale_photos/')
    photo_date = models.DateField("Data wykonania zdjęcia", default=timezone.now)
    description = models.CharField("Opis zdjęcia", max_length=255, blank=True)

    class Meta:
        verbose_name = "Zdjęcie Lokalu"
        verbose_name_plural = "Zdjęcia Lokalu"
        
    def __str__(self):
        return f"Zdjęcie dla {self.lokal.unit_number} z dnia {self.photo_date}"

# --- 12. Naliczenia Miesięczne ---
class MonthlyCharge(models.Model):
    agreement = models.ForeignKey(Agreement, verbose_name="Umowa", on_delete=models.CASCADE, related_name="monthly_charges")
    month_year = models.DateField("Miesiąc naliczenia", help_text="Pierwszy dzień miesiąca, którego dotyczy naliczenie, np. 2025-01-01")

    # Składniki naliczenia
    rent = models.DecimalField("Czynsz", max_digits=10, decimal_places=2)
    fixed_fees = models.DecimalField("Opłaty stałe (np. śmieci)", max_digits=10, decimal_places=2)
    water_cost = models.DecimalField("Koszt wody", max_digits=10, decimal_places=2, default=0)
    
    total_charge = models.DecimalField("Suma naliczenia", max_digits=10, decimal_places=2)
    
    # Dodatkowe informacje
    description = models.TextField("Opis/Notatki do naliczenia", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Naliczenie Miesięczne"
        verbose_name_plural = "Naliczenia Miesięczne"
        unique_together = ('agreement', 'month_year') # Zapewnia jedno naliczenie na umowę na miesiąc
        ordering = ['-month_year', 'agreement']

    def save(self, *args, **kwargs):
        # Automatyczne obliczanie sumy
        self.total_charge = self.rent + self.fixed_fees + self.water_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Naliczenie dla {self.agreement} za {self.month_year.strftime('%Y-%m')} - {self.total_charge} PLN"

    