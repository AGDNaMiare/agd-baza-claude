from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import _fontdata
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import io
import os
from io import BytesIO
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.rl_config import register_reset
import reportlab.rl_config

# Wyłączamy domyślne czcionki i ustawiamy własne
register_reset()
reportlab.rl_config.warnOnMissingFontGlyphs = 0
_fontdata.STRIP_CONTROL = False
_fontdata.EXTENSIONS = []
_fontdata.DEFAULT_ENCODING = 'utf-8'
_fontdata.T1SearchPath = []
_fontdata.TTFSearchPath = []
_fontdata.CMapSearchPath = []
_fontdata.DefaultEncoding = 'utf-8'
_fontdata.defaultEncoding = 'utf-8'
_fontdata.standardFonts = []
_fontdata.standardFontAttributes = {}
_fontdata._fonts = {}

basedir = os.path.abspath(os.path.dirname(__file__))

# Rejestracja czcionek
font_dir = os.path.join(basedir, 'fonts')
if not os.path.exists(font_dir):
    os.makedirs(font_dir)

# Sprawdzamy czy pliki czcionek istnieją
for font_file in ['DejaVuSans.ttf', 'DejaVuSans-Bold.ttf']:
    font_path = os.path.join(font_dir, font_file)
    if not os.path.exists(font_path):
        raise FileNotFoundError(f"Brak wymaganego pliku czcionki: {font_path}")

# Rejestrujemy czcionki
pdfmetrics.registerFont(TTFont('DejaVuSans', os.path.join(font_dir, 'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', os.path.join(font_dir, 'DejaVuSans-Bold.ttf')))
registerFontFamily('DejaVuSans', normal='DejaVuSans', bold='DejaVuSans-Bold')

# Globalne zmienne dla czcionek
NORMAL_FONT = 'DejaVuSans'
BOLD_FONT = 'DejaVuSans-Bold'

# Wyłączamy domyślne czcionki w ReportLab
reportlab.rl_config.canvas_basefontname = NORMAL_FONT
reportlab.rl_config.defaultGraphicsFontName = NORMAL_FONT
reportlab.rl_config.ps2pdf_defaultFontName = NORMAL_FONT
reportlab.rl_config.pageCompression = 1
reportlab.rl_config.defaultPageSize = A4
reportlab.rl_config.defaultImageCaching = 0
reportlab.rl_config.T1SearchPath = []
reportlab.rl_config.TTFSearchPath = [font_dir]
reportlab.rl_config.CMapSearchPath = []

app = Flask(__name__)
app.config['SECRET_KEY'] = 'twoj-tajny-klucz-tutaj'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Modele
class ProductGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    products = db.relationship('Product', backref='group', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    customer_info = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500))
    group_id = db.Column(db.Integer, db.ForeignKey('product_group.id'), nullable=False)
    selected = db.Column(db.Boolean, default=False)
    stores = db.relationship('Store', secondary='store_products')

class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))

# Tabela łącząca sklepy z produktami
store_products = db.Table('store_products',
    db.Column('store_id', db.Integer, db.ForeignKey('store.id'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'), primary_key=True)
)

# Model użytkownika
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Dekorator do sprawdzania czy użytkownik jest zalogowany
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Proszę się zalogować, aby uzyskać dostęp.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Trasy logowania
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Zalogowano pomyślnie!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Nieprawidłowa nazwa użytkownika lub hasło.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Wylogowano pomyślnie!', 'success')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # Sprawdzamy czy istnieje już jakiś użytkownik
    if User.query.first() is not None:
        flash('Rejestracja jest obecnie wyłączona.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Ta nazwa użytkownika jest już zajęta.', 'error')
            return redirect(url_for('register'))
        
        user = User(username=username, is_admin=True)  # Pierwszy użytkownik jest adminem
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        flash('Konto zostało utworzone! Możesz się teraz zalogować.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Trasy
@app.route('/')
@login_required
def index():
    sort_by = request.args.get('sort_by', 'name')
    
    try:
        if sort_by == 'group':
            # Sortowanie po grupie, a następnie po nazwie produktu
            groups = ProductGroup.query.order_by(ProductGroup.name).all()
        else:
            # Sortowanie po nazwie produktu
            products = Product.query.order_by(Product.name).all()
            # Grupuj produkty według ich grup
            groups = {}
            for product in products:
                if product.group not in groups:
                    groups[product.group] = []
                groups[product.group].append(product)
            groups = [group for group in ProductGroup.query.all() if group in groups]
        
        stores = Store.query.all()
        all_groups = ProductGroup.query.order_by(ProductGroup.name).all()
        return render_template('index.html', groups=all_groups, stores=stores, current_sort=sort_by)
    except Exception as e:
        flash('Wystąpił błąd podczas ładowania danych!', 'error')
        print(f"Błąd: {str(e)}")
        return render_template('index.html', groups=[], stores=[], current_sort=sort_by)

@app.route('/add_group', methods=['POST'])
@login_required
def add_group():
    try:
        name = request.form.get('name')
        if not name:
            flash('Nazwa grupy jest wymagana!', 'error')
            return redirect(url_for('index'))
        
        group = ProductGroup(name=name)
        db.session.add(group)
        db.session.commit()
        flash('Grupa została dodana pomyślnie!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas dodawania grupy!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    name = request.form.get('name')
    description = request.form.get('description')
    customer_info = request.form.get('customer_info')
    price = float(request.form.get('price'))
    group_id = int(request.form.get('group_id'))
    image_url = request.form.get('image_url')
    store_ids = request.form.getlist('store_ids')
    
    product = Product(
        name=name, 
        description=description,
        customer_info=customer_info,
        price=price, 
        group_id=group_id,
        image_url=image_url
    )
    
    db.session.add(product)
    
    # Dodawanie powiązań ze sklepami
    if store_ids:
        stores = Store.query.filter(Store.id.in_(store_ids)).all()
        product.stores.extend(stores)
    
    db.session.commit()
    flash('Produkt został dodany!', 'success')
    return redirect(url_for('index'))

@app.route('/add_store', methods=['POST'])
@login_required
def add_store():
    name = request.form.get('name')
    address = request.form.get('address')
    
    store = Store(name=name, address=address)
    db.session.add(store)
    db.session.commit()
    flash('Sklep został dodany!', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_product/<int:product_id>')
@login_required
def toggle_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.selected = not product.selected
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/generate_pdf')
@login_required
def generate_pdf():
    try:
        print("Rozpoczynam generowanie PDF...")
        selected_products = Product.query.filter_by(selected=True).all()
        print(f"Znaleziono {len(selected_products)} wybranych produktów")
        
        # Sprawdzamy dostępne czcionki przed utworzeniem canvas
        print(f"Zarejestrowane czcionki: {pdfmetrics.getRegisteredFontNames()}")
        
        # Tworzenie PDF z wymuszonymi ustawieniami
        response = BytesIO()
        print("Tworzę canvas...")
        
        # Tworzymy canvas z wymuszonymi ustawieniami
        c = canvas.Canvas(response, pagesize=A4, initialFontName=NORMAL_FONT, initialFontSize=12)
        c._fontname = NORMAL_FONT  # Wymuszamy użycie naszej czcionki
        c._font = None  # Resetujemy cache czcionki
        print("Canvas utworzony pomyślnie")
        
        # Ustawiamy czcionkę i sprawdzamy czy się udało
        print(f"Ustawiam czcionkę {BOLD_FONT}...")
        c.setFont(BOLD_FONT, 16)
        print("Czcionka ustawiona pomyślnie")
        
        # Rysujemy tytuł
        c.drawString(50, 750, "Lista wybranych produktów")
        print("Tytuł narysowany")
        
        y = 700  # Początkowa pozycja Y
        total_price = 0
        
        # Grupujemy produkty według grup
        products_by_group = {}
        for product in selected_products:
            if product.group.name not in products_by_group:
                products_by_group[product.group.name] = []
            products_by_group[product.group.name].append(product)
        
        # Iterujemy po grupach
        for group_name, products in products_by_group.items():
            print(f"Przetwarzam grupę: {group_name}")
            
            # Sprawdzamy czy zostało wystarczająco miejsca na stronie
            if y < 100:
                c.showPage()
                y = 750
                c._fontname = NORMAL_FONT  # Wymuszamy użycie naszej czcionki po każdej nowej stronie
                c._font = None  # Resetujemy cache czcionki
                c.setFont(BOLD_FONT, 16)
            
            # Nazwa grupy
            c.setFont(BOLD_FONT, 14)
            c.drawString(50, y, group_name)
            y -= 30
            
            # Produkty w grupie
            c.setFont(NORMAL_FONT, 12)
            for product in products:
                print(f"Przetwarzam produkt: {product.name}")
                
                if y < 100:
                    c.showPage()
                    y = 750
                    c._fontname = NORMAL_FONT  # Wymuszamy użycie naszej czcionki po każdej nowej stronie
                    c._font = None  # Resetujemy cache czcionki
                    c.setFont(NORMAL_FONT, 12)
                
                c.drawString(70, y, f"{product.name} - {product.price:.2f} zł")
                y -= 20
                
                if product.description:
                    c.drawString(90, y, f"Opis produktu: {product.description}")
                    y -= 20
                
                if product.customer_info:
                    c.drawString(90, y, f"Informacje dla klienta: {product.customer_info}")
                    y -= 20
                
                total_price += product.price
                y -= 10
        
        # Suma
        c.setFont(BOLD_FONT, 14)
        c.drawString(50, y, f"Suma: {total_price:.2f} zł")
        
        print("Finalizuję PDF...")
        c.save()
        response.seek(0)
        print("PDF wygenerowany pomyślnie")
        
        return send_file(
            response,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'produkty_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
        
    except Exception as e:
        import traceback
        print(f"Błąd podczas generowania PDF: {type(e).__name__}")
        print(f"Szczegóły błędu: {str(e)}")
        print("Traceback:")
        print(traceback.format_exc())
        flash('Wystąpił błąd podczas generowania PDF!', 'error')
        return redirect(url_for('index'))

@app.route('/edit_group/<int:group_id>', methods=['POST'])
@login_required
def edit_group(group_id):
    try:
        group = ProductGroup.query.get_or_404(group_id)
        name = request.form.get('name')
        if not name:
            flash('Nazwa grupy jest wymagana!', 'error')
            return redirect(url_for('index'))
        
        group.name = name
        db.session.commit()
        flash('Grupa została zaktualizowana!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas aktualizacji grupy!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/edit_store/<int:store_id>', methods=['POST'])
@login_required
def edit_store(store_id):
    try:
        store = Store.query.get_or_404(store_id)
        name = request.form.get('name')
        address = request.form.get('address')
        
        if not name:
            flash('Nazwa sklepu jest wymagana!', 'error')
            return redirect(url_for('index'))
        
        store.name = name
        store.address = address
        db.session.commit()
        flash('Sklep został zaktualizowany!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas aktualizacji sklepu!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/edit_product/<int:product_id>', methods=['POST'])
@login_required
def edit_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        name = request.form.get('name')
        description = request.form.get('description')
        customer_info = request.form.get('customer_info')
        price = float(request.form.get('price'))
        group_id = int(request.form.get('group_id'))
        image_url = request.form.get('image_url')
        store_ids = request.form.getlist('store_ids')
        
        if not name:
            flash('Nazwa produktu jest wymagana!', 'error')
            return redirect(url_for('index'))
        
        product.name = name
        product.description = description
        product.customer_info = customer_info
        product.price = price
        product.group_id = group_id
        product.image_url = image_url
        
        # Aktualizacja powiązań ze sklepami
        product.stores = []
        if store_ids:
            stores = Store.query.filter(Store.id.in_(store_ids)).all()
            product.stores.extend(stores)
        
        db.session.commit()
        flash('Produkt został zaktualizowany!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas aktualizacji produktu!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/get_group/<int:group_id>')
@login_required
def get_group(group_id):
    group = ProductGroup.query.get_or_404(group_id)
    return {'id': group.id, 'name': group.name}

@app.route('/get_store/<int:store_id>')
@login_required
def get_store(store_id):
    store = Store.query.get_or_404(store_id)
    return {'id': store.id, 'name': store.name, 'address': store.address}

@app.route('/get_product/<int:product_id>')
@login_required
def get_product(product_id):
    product = Product.query.get_or_404(product_id)
    return {
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'customer_info': product.customer_info,
        'price': product.price,
        'group_id': product.group_id,
        'image_url': product.image_url,
        'store_ids': [store.id for store in product.stores]
    }

@app.route('/delete_group/<int:group_id>', methods=['POST'])
@login_required
def delete_group(group_id):
    try:
        group = ProductGroup.query.get_or_404(group_id)
        if group.products:
            flash('Nie można usunąć grupy, która zawiera produkty!', 'error')
            return redirect(url_for('index'))
        
        db.session.delete(group)
        db.session.commit()
        flash('Grupa została usunięta!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas usuwania grupy!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/delete_store/<int:store_id>', methods=['POST'])
@login_required
def delete_store(store_id):
    try:
        store = Store.query.get_or_404(store_id)
        # Usuwamy powiązania ze sklepem
        store.products = []
        db.session.delete(store)
        db.session.commit()
        flash('Sklep został usunięty!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas usuwania sklepu!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

@app.route('/delete_product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        flash('Produkt został usunięty!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas usuwania produktu!', 'error')
        print(f"Błąd: {str(e)}")
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False) 