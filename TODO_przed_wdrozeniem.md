# TODO przed wdrożeniem na produkcję

## ✅ Już zrobione
- [x] Brakująca autoryzacja w `edit_transaction`, `delete_transaction`, `save_categorization`, `categorize_transactions`
- [x] Ustawienia ciasteczek sesji (`HTTPONLY`, `SAMESITE`)

---

## 🔴 KRYTYCZNE — wymagane przed startem

- [ ] **`DEBUG = False`** — `Kamienica/settings.py:27`
- [ ] **`ALLOWED_HOSTS = ['twoja-domena.pl']`** — `Kamienica/settings.py:29`
- [ ] **Odkomentować `SESSION_COOKIE_SECURE = True` i `CSRF_COOKIE_SECURE = True`** — `Kamienica/settings.py:150-151` (wymaga HTTPS)
- [ ] **Skonfigurować HTTPS** na serwerze (wymagane przez powyższe)
- [ ] **Zmienić użytkownika bazy danych** — `settings.py:86` używa `root`, stworzyć dedykowanego usera MySQL z minimalnymi uprawnieniami

---

## 🟠 WYSOKIE — silnie zalecane

### Autoryzacja
- [ ] **`meter_consumption_report`** — brak filtrowania po lokalu dla zwykłego użytkownika — `core/views/meters.py:61`
- [ ] **`water_cost_summary_view`** — GET dostępny bez sprawdzenia uprawnień — `core/views/reports.py:124`

### Hasła
- [ ] **Naprawić `CustomPasswordValidator`** — logika `password.isalnum()` jest odwrócona — `core/validators.py:68`
  ```python
  # Zamienić na:
  import re
  SPECIAL_CHARS = r'[!@#$%^&*()\-_=+\[\]{};:\'",.<>?/\\|`~]'
  if not re.search(SPECIAL_CHARS, password):
      raise ValidationError("Hasło musi zawierać co najmniej jeden znak specjalny.")
  ```

### Email / reset hasła
- [ ] **Skonfigurować prawdziwy backend email** — `settings.py:140` ma `console.EmailBackend`, użytkownicy nie mogą resetować hasła
  ```python
  EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
  EMAIL_HOST = config('EMAIL_HOST')
  EMAIL_PORT = config('EMAIL_PORT', cast=int, default=587)
  EMAIL_USE_TLS = True
  EMAIL_HOST_USER = config('EMAIL_HOST_USER')
  EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD')
  ```

### Formularze
- [ ] **`email = required=False` → `required=True`** w `UserForm` — `core/forms.py:7` — użytkownik bez emaila nie może się zalogować

---

## 🟡 ŚREDNIE — zalecane

- [ ] **Rate limiting na logowaniu** — zainstalować `django-axes` lub `django-ratelimit`, zabezpieczyć `core/views/auth.py:11`
- [ ] **Paginacja** na liście transakcji — `core/views/transactions.py` (upload_csv), duże zbiory danych mogą zawiesić serwer
- [ ] **Niespójne zapytania email** — `core/views/lokals.py:20` używa `user__email=` zamiast `user__email__iexact=` (problem na Linux MySQL)
- [ ] **Walidacja `additional_costs >= 0`** w rozliczeniu — `core/views/agreements.py:169` (ujemne koszty mogą manipulować saldem)
- [ ] **Naprawić rekurencję w `get_annual_report_context`** — `core/services/reporting.py` — stack overflow dla starych umów
- [ ] **Dodać `STATIC_ROOT`** i uruchomić `collectstatic` przed wdrożeniem

---

## 🟢 NISKIE — nice to have

- [ ] **Nagłówki bezpieczeństwa** — zainstalować `django-csp` (Content-Security-Policy) + dodać do `settings.py`:
  ```python
  SECURE_CONTENT_TYPE_NOSNIFF = True
  SECURE_BROWSER_XSS_FILTER = True
  SECURE_HSTS_SECONDS = 31536000  # tylko gdy HTTPS
  ```
- [ ] **Zmienić URL admina** z domyślnego `/admin/` na niestandardowy w `Kamienica/urls.py`
- [ ] **Audit log** dla operacji usuwania/edycji transakcji (np. przez `simple_history` lub własny logger)
- [ ] **Walidacja rozmiaru pliku CSV** przed importem — `core/views/transactions.py:74`
- [ ] **Weryfikacja `.env` w `.gitignore`** — sprawdzić czy `SECRET_KEY` i `DB_PASSWORD` nie trafiły do repozytorium

---

## ⚙️ Deployment checklist (serwer)

- [ ] Serwer WWW (nginx / Apache) jako reverse proxy przed Gunicorn/uWSGI
- [ ] Certyfikat SSL (Let's Encrypt lub inny)
- [ ] Zmienne środowiskowe ustawione na serwerze (nie w pliku `.env` w katalogu projektu)
- [ ] `python manage.py migrate` po wdrożeniu
- [ ] `python manage.py collectstatic --noinput`
- [ ] Backup bazy danych przed każdą migracją
- [ ] Logi Django skierowane do pliku, nie konsoli
