import os
import urllib.request
import shutil

# Tworzenie folderu fonts jeśli nie istnieje
if not os.path.exists('fonts'):
    os.makedirs('fonts')

# URLs do czcionek
fonts = {
    'DejaVuSans.ttf': 'https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip',
    'DejaVuSans-Bold.ttf': 'https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.zip'
}

# Pobieranie i rozpakowywanie archiwum
print('Pobieranie archiwum z czcionkami...')
zip_path = 'fonts/dejavu-fonts.zip'

try:
    urllib.request.urlretrieve(fonts['DejaVuSans.ttf'], zip_path)
    print('Pobrano archiwum pomyślnie!')
    
    # Tutaj należałoby rozpakować archiwum i skopiować potrzebne pliki
    print('Proszę rozpakuj ręcznie archiwum dejavu-fonts.zip z folderu fonts')
    print('i skopiuj pliki DejaVuSans.ttf i DejaVuSans-Bold.ttf do folderu fonts')
except Exception as e:
    print(f'Błąd podczas pobierania archiwum: {str(e)}') 