import os
import urllib.request
import zipfile
import shutil
from pathlib import Path

# Tworzenie folderu fonts jeśli nie istnieje
if not os.path.exists('fonts'):
    os.makedirs('fonts')

# URL do archiwum z czcionkami
zip_url = 'https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip'
zip_path = 'fonts/dejavu-fonts.zip'

try:
    # Pobieranie archiwum
    print('Pobieranie archiwum z czcionkami...')
    urllib.request.urlretrieve(zip_url, zip_path)
    print('Pobrano archiwum pomyślnie!')
    
    # Rozpakowywanie archiwum
    print('Rozpakowywanie archiwum...')
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # Tworzymy tymczasowy folder do rozpakowania
        temp_dir = 'fonts/temp'
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        # Rozpakowujemy archiwum
        zip_ref.extractall(temp_dir)
        
        # Znajdujemy folder ttf w rozpakowanych plikach
        ttf_dir = next(Path(temp_dir).rglob('ttf'))
        
        # Kopiujemy potrzebne pliki
        shutil.copy2(os.path.join(ttf_dir, 'DejaVuSans.ttf'), 'fonts/DejaVuSans.ttf')
        shutil.copy2(os.path.join(ttf_dir, 'DejaVuSans-Bold.ttf'), 'fonts/DejaVuSans-Bold.ttf')
        
        # Usuwamy tymczasowe pliki
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        
    print('Czcionki zostały pomyślnie zainstalowane!')
    
except Exception as e:
    print(f'Wystąpił błąd: {str(e)}') 