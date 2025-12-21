import csv
import io
import datetime
from decimal import Decimal, InvalidOperation
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect
from .forms import CSVUploadForm
from core.models import FinancialTransaction

def upload_csv(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            try:
                decoded_file = csv_file.read().decode('windows-1250')
            except UnicodeDecodeError:
                decoded_file = csv_file.read().decode('utf-8')

            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string, delimiter=';')

            header_found = False
            for row in reader:
                # Skip until header is found
                if not header_found:
                    if row and row[0] == "Data transakcji":
                        header_found = True
                    continue

                # Stop at footer
                if row and row[0].startswith("Dokument ma charakter informacyjny"):
                    break
                
                # Process data rows
                if len(row) > 8: # Ensure all required columns exist
                    try:
                        date_str = row[0].strip()
                        parsed_date = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                        
                        amount_str = row[8].replace(',', '.').strip()
                        if not amount_str:
                            continue

                        try:
                            amount = Decimal(amount_str)
                        except InvalidOperation:
                            continue

                        # Determine transaction type for the new model
                        transaction_core_type = 'czynsz' if amount > 0 else 'inne'
                        
                        lookup_params = {
                            'posting_date': parsed_date.date(),
                            'description': row[3].strip(),
                            'amount': amount
                        }
                        
                        if not FinancialTransaction.objects.filter(**lookup_params).exists():
                            FinancialTransaction.objects.create(
                                **lookup_params,
                                type=transaction_core_type
                            )
                    except (ValidationError, ValueError, IndexError):
                        # Silently skip rows that fail validation or parsing
                        continue
                        
            return redirect('upload_csv')
    else:
        form = CSVUploadForm()
    
    transactions = FinancialTransaction.objects.all().order_by('-posting_date')
    return render(request, 'finances/upload_csv.html', {'form': form, 'transactions': transactions})