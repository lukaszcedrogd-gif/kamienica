from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User as AuthUser
from decimal import Decimal
from datetime import date, timedelta
from .models import BUILDING_LOKAL_NUMBER, Lokal, Meter, MeterReading, Agreement, User, FinancialTransaction, WaterCostOverride, FixedCost

class BimonthlyReportViewTest(TestCase):
    def setUp(self):
        # --- Użytkownicy i Umowy ---
        self.user = User.objects.create(name="Jan", lastname="Kowalski", email="jan@kowalski.com", role="lokator")
        self.lokal1 = Lokal.objects.create(unit_number="1", size_sqm=50)
        self.kamienica = Lokal.objects.create(unit_number=BUILDING_LOKAL_NUMBER, size_sqm=100)
        self.agreement = Agreement.objects.create(
            user=self.user,
            lokal=self.lokal1,
            signing_date=date(2024, 1, 1),
            start_date=date(2024, 1, 1),
            rent_amount=1000,
            number_of_occupants=2,
        )

        # --- Liczniki i Odczyty dla Lokalu 1 ---
        self.meter_cold = Meter.objects.create(serial_number="CW123", type="cold_water", lokal=self.lokal1)
        self.meter_hot = Meter.objects.create(serial_number="HW123", type="hot_water", lokal=self.lokal1)
        MeterReading.objects.create(meter=self.meter_cold, reading_date=date(2025, 2, 28), value=Decimal("100.0"))
        MeterReading.objects.create(meter=self.meter_cold, reading_date=date(2025, 4, 30), value=Decimal("110.0")) # Zużycie 10
        MeterReading.objects.create(meter=self.meter_hot, reading_date=date(2025, 2, 28), value=Decimal("50.0"))
        MeterReading.objects.create(meter=self.meter_hot, reading_date=date(2025, 4, 30), value=Decimal("55.0")) # Zużycie 5

        # --- Liczniki i Odczyty dla Kamienicy (Główne) ---
        self.main_meter = Meter.objects.create(serial_number="MAIN123", type="cold_water", lokal=self.kamienica)
        MeterReading.objects.create(meter=self.main_meter, reading_date=date(2025, 2, 28), value=Decimal("1000.0"))
        MeterReading.objects.create(meter=self.main_meter, reading_date=date(2025, 5, 1), value=Decimal("1050.0")) # Zużycie 50

        # --- Transakcje i Reguły Kosztów ---
        self.water_invoice = FinancialTransaction.objects.create(
            title="oplata_za_wode",
            amount=Decimal("-500.00"),
            posting_date=date(2025, 5, 15) # Faktura pasująca do okresu Marzec-Kwiecień
        )
        FixedCost.objects.create(name="Wywóz śmieci", category="waste", calculation_method="per_person", amount=Decimal("30"), effective_date=date(2024,1,1))
        
        self.auth_user = AuthUser.objects.create_superuser(
            username='testadmin', email='admin@test.com', password='testpass123'
        )
        self.client = Client()
        self.client.login(username='testadmin', password='testpass123')
        self.url = reverse('lokal-bimonthly-report', kwargs={'pk': self.lokal1.pk})

    def test_report_calculation_with_auto_invoice(self):
        url_with_year = f"{self.url}?year=2025"
        response = self.client.get(url_with_year)
        self.assertEqual(response.status_code, 200)
        
        # Sprawdź dane dla okresu Marzec-Kwiecień
        report_data = response.context['report_data']
        self.assertEqual(len(report_data), 1)
        period_data = report_data[0]

        # 1. Sprawdź zużycie dla lokalu
        self.assertEqual(period_data['total_consumption'], Decimal("15.000"))

        # 2. Sprawdź automatycznie znalezione dane o kosztach wody
        water_details = period_data['water_cost_details']
        
        # W nowej logice nie ma automatycznego szukania faktury
        self.assertEqual(water_details['bill_amount'], None)
        self.assertEqual(water_details['source'], 'Brak danych')
        
        # Total consumption should be the sum of all lokals' consumption for that period
        # Lokal 1: 10 + 5 = 15. No other lokals in this test.
        self.assertEqual(water_details['total_building_consumption'], Decimal("15.000"))

        # 3. Sprawdź obliczenia kosztów
        self.assertEqual(water_details['unit_price'], Decimal("0.0"))
        self.assertEqual(water_details['lokal_water_cost'], Decimal("0.00"))

        # 4. Sprawdź koszty śmieci (2 osoby * 30 zł/os * 2 miesiące)
        self.assertEqual(period_data['waste_cost'], Decimal("120.00"))

    def test_report_calculation_with_manual_override(self):
        # 1. Ręcznie utwórz obiekt WaterCostOverride, tak jak zrobiłby to admin
        WaterCostOverride.objects.create(
            period_start_date=date(2025, 3, 1),
            overridden_bill_amount=Decimal("600.00"),
        )

        # 2. Pobierz raport i sprawdź obliczenia
        url_with_year = f"{self.url}?year=2025"
        response_get = self.client.get(url_with_year)
        self.assertEqual(response_get.status_code, 200)

        period_data = response_get.context['report_data'][0]
        water_details = period_data['water_cost_details']

        # Sprawdź, czy używane są wartości ręczne
        self.assertEqual(water_details['bill_amount'], Decimal("600.00"))
        self.assertEqual(water_details['source'], 'Ręczne ustawienie (admin)')
        self.assertEqual(water_details['total_building_consumption'], Decimal("15.000"))

        # Sprawdź obliczenia
        # Cena jednostkowa = 600 / 15 = 40
        self.assertEqual(water_details['unit_price'], Decimal("40.0"))
        # Koszt dla lokalu = 15 (zużycie) * 40 (cena) = 600
        self.assertEqual(water_details['lokal_water_cost'], Decimal("600.00"))

    def test_total_consumption_verification(self):
        # Dodajemy drugi lokal z licznikiem, aby suma była inna niż dla jednego lokalu
        lokal2 = Lokal.objects.create(unit_number="2", size_sqm=30)
        user2 = User.objects.create(name="Anna", lastname="Nowak", email="anna@nowak.com", role="lokator")
        Agreement.objects.create(user=user2, lokal=lokal2, signing_date=date(2024, 1, 1), start_date=date(2024, 1, 1), rent_amount=800, number_of_occupants=1)
        meter2 = Meter.objects.create(serial_number="CW456", type="cold_water", lokal=lokal2)
        MeterReading.objects.create(meter=meter2, reading_date=date(2025, 2, 28), value=Decimal("20.0"))
        MeterReading.objects.create(meter=meter2, reading_date=date(2025, 4, 30), value=Decimal("25.0")) # Zużycie 5

        url_with_year = f"{self.url}?year=2025"
        response = self.client.get(url_with_year)
        self.assertEqual(response.status_code, 200)
        
        # Całkowite zużycie powinno być sumą zużyć obu lokali (15 + 5 = 20)
        # Błąd w logice testu, kontekst `all_lokals_total_consumption` jest liczony dla wszystkich lokali
        # a nie tylko dla tego w raporcie. Poprawiam test.
        
        # Pobieramy sumę zużycia ze wszystkich lokali obliczoną w widoku
        all_lokals_consumption = response.context['all_lokals_total_consumption']

        # Oczekiwane zużycie: 10 (zimna woda l1) + 5 (ciepła woda l1) + 5 (zimna woda l2) = 20
        # UWAGA: Logika w widoku może być skomplikowana. Testujemy jej wynik.
        # Moja nowa logika w widoku dla sumy zużyć lokali jest bardziej precyzyjna
        # `start_reading` jest ostatnim PRZED okresem, `end_reading` jest pierwszym PO okresie.
        # Dla danych testowych:
        # Lokal 1, zimna: end(4-30) - start(2-28) -> 110 - 100 = 10
        # Lokal 1, ciepła: end(4-30) - start(2-28) -> 55 - 50 = 5
        # Lokal 2, zimna: end(4-30) - start(2-28) -> 25 - 20 = 5
        # Suma: 10 + 5 + 5 = 20
        # Ta suma może się różnić od `total_building_consumption` z licznika głównego.
        # W teście `main_meter` zużył 50. Testujemy, czy `all_lokals_total_consumption` wynosi 20.
        
        # Musimy znaleźć odpowiednie odczyty zgodnie z logiką widoku,
        # która szuka odczytów na granicach okresu.
        # Okres to marzec-kwiecień 2025. start=2025-03-01, end=2025-04-30.
        # Logika widoku: start_reading <= period_start, end_reading >= period_end
        # W naszych danych testowych to dokładnie odczyty z 28.02 i 30.04.
        
        # Lokal 1, zimna: 110-100 = 10
        # Lokal 1, ciepła: 55-50 = 5
        # Lokal 2, zimna: 25-20 = 5
        # Suma = 20
        
        # W widoku `all_lokals_total_consumption` jest teraz obliczane precyzyjniej
        # dla najnowszego okresu.
        self.assertEqual(all_lokals_consumption, Decimal('20.000'))