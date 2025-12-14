import csv
import io
from django.shortcuts import render, redirect
from .forms import CSVUploadForm
from .models import Transaction

def upload_csv(request):
    if request.method == 'POST':
        form = CSVUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8')
            io_string = io.StringIO(decoded_file)
            reader = csv.reader(io_string)
            next(reader)  # Skip header row
            for row in reader:
                # Assuming CSV format: date,description,amount,transaction_type
                Transaction.objects.create(
                    date=row[0],
                    description=row[1],
                    amount=row[2],
                    transaction_type=row[3]
                )
            return redirect('upload_csv')
    else:
        form = CSVUploadForm()
    
    transactions = Transaction.objects.all().order_by('-date')
    return render(request, 'finances/upload_csv.html', {'form': form, 'transactions': transactions})