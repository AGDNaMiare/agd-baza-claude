from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
import io
import os
from io import BytesIO
from fpdf import FPDF
from fpdf.enums import XPos, YPos

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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'twoj-tajny-klucz-tutaj')

# Konfiguracja bazy danych
if os.environ.get('DATABASE_URL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://')
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfiguracja dla produkcji
if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_HTTPONLY'] = True

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
    image_url = db.Column(db.String(500))
    group_id = db.Column(db.Integer, db.ForeignKey('product_group.id'), nullable=False)
    selected = db.Column(db.Boolean, default=False)
    stores = db.relationship('Store', secondary='store_products')
    
    def get_price_for_store(self, store_id):
        """Pobiera cenę produktu dla konkretnego sklepu"""
        result = db.session.execute(
            db.select(store_products.c.price)
            .where(store_products.c.product_id == self.id)
            .where(store_products.c.store_id == store_id)
        ).scalar_one_or_none()
        return result if result is not None else 0.0

class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(200))

# Tabela łącząca sklepy z produktami
store_products = db.Table('store_products',
    db.Column('store_id', db.Integer, db.ForeignKey('store.id'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('product.id'), primary_key=True),
    db.Column('price', db.Float, nullable=True)
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

# Dekorator do sprawdzania czy użytkownik jest adminem
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Proszę się zalogować, aby uzyskać dostęp.', 'error')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Brak uprawnień administratora.', 'error')
            return redirect(url_for('index'))
            
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
    if User.query.first() is None:
        # Jeśli nie ma żadnego użytkownika, pozwalamy na utworzenie pierwszego admina
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
            
            flash('Konto administratora zostało utworzone! Możesz się teraz zalogować.', 'success')
            return redirect(url_for('login'))
        
        return render_template('register.html')
    else:
        # Jeśli są już użytkownicy, sprawdzamy czy próbuje dodać admin
        if 'user_id' not in session:
            flash('Rejestracja jest możliwa tylko przez administratora.', 'error')
            return redirect(url_for('login'))
        
        current_user = User.query.get(session['user_id'])
        if not current_user or not current_user.is_admin:
            flash('Tylko administrator może dodawać nowych użytkowników.', 'error')
            return redirect(url_for('index'))
        
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            is_admin = request.form.get('is_admin') == 'true'
            
            if User.query.filter_by(username=username).first():
                flash('Ta nazwa użytkownika jest już zajęta.', 'error')
                return redirect(url_for('register'))
            
            user = User(username=username, is_admin=is_admin)
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            flash('Nowy użytkownik został dodany pomyślnie!', 'success')
            return redirect(url_for('index'))
        
        return render_template('register.html', admin_mode=True)

# Trasy
@app.route('/')
@login_required
def index():
    sort_by = request.args.get('sort_by', 'name')
    current_user = User.query.get(session['user_id'])
    
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
        return render_template('index.html', 
                            groups=all_groups, 
                            stores=stores, 
                            current_sort=sort_by,
                            current_user=current_user)
    except Exception as e:
        flash('Wystąpił błąd podczas ładowania danych!', 'error')
        print(f"Błąd: {str(e)}")
        return render_template('index.html', 
                            groups=[], 
                            stores=[], 
                            current_sort=sort_by,
                            current_user=current_user)

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
    try:
        name = request.form.get('name')
        description = request.form.get('description')
        customer_info = request.form.get('customer_info')
        group_id = int(request.form.get('group_id'))
        image_url = request.form.get('image_url')
        store_ids = request.form.getlist('store_ids')
        
        # Pobieramy ceny dla każdego sklepu
        store_prices = {}
        for store_id in store_ids:
            price_key = f'price_{store_id}'
            if price_key in request.form and request.form.get(price_key):
                store_prices[int(store_id)] = float(request.form.get(price_key))
        
        product = Product(
            name=name, 
            description=description,
            customer_info=customer_info,
            group_id=group_id,
            image_url=image_url
        )
        
        db.session.add(product)
        db.session.flush()  # Aby uzyskać ID produktu
        
        # Dodajemy powiązania ze sklepami i cenami
        for store_id in store_ids:
            store_id = int(store_id)
            price = store_prices.get(store_id, 0.0)
            
            # Dodajemy wpis do tabeli łączącej z ceną
            db.session.execute(
                store_products.insert().values(
                    store_id=store_id,
                    product_id=product.id,
                    price=price
                )
            )
        
        db.session.commit()
        flash('Produkt został dodany!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Wystąpił błąd podczas dodawania produktu!', 'error')
        print(f"Błąd: {str(e)}")
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
        
        # Upewniamy się, że czcionki są zarejestrowane
        font_dir = os.path.join(basedir, 'fonts')
        normal_font_path = os.path.join(font_dir, 'DejaVuSans.ttf')
        bold_font_path = os.path.join(font_dir, 'DejaVuSans-Bold.ttf')
        
        if not os.path.exists(normal_font_path) or not os.path.exists(bold_font_path):
            raise FileNotFoundError(f"Brak wymaganych plików czcionek w katalogu {font_dir}")
        
        # Tworzenie PDF z wymuszonymi ustawieniami
        response = BytesIO()
        print("Tworzę PDF...")
        
        # Tworzymy własną klasę PDF z obsługą czcionek
        class PDF(FPDF):
            def __init__(self):
                super().__init__()
                # Dodajemy czcionki
                self.add_font('DejaVuSans', '', normal_font_path)
                self.add_font('DejaVuSans-Bold', '', bold_font_path)
                
            def bullet_text(self, txt, indent=10, bullet="•"):
                self.set_x(self.get_x() + indent)
                self.cell(5, 5, bullet, align='C')
                self.set_x(self.get_x() + 5)
                self.multi_cell(0, 5, txt)
                self.ln(2)
                
            def normal_text(self, txt, indent=10):
                self.set_x(self.get_x() + indent)
                self.multi_cell(0, 5, txt)
                self.ln(2)
        
        # Importujemy stałe dla pozycjonowania
        from fpdf.enums import XPos, YPos
        
        pdf = PDF()
        pdf.add_page()
        
        # Ustawiamy marginesy
        pdf.set_margins(20, 20, 20)
        
        # Ustawiamy czcionkę
        pdf.set_font('DejaVuSans-Bold', size=18)
        
        # Rysujemy tytuł
        pdf.cell(0, 15, "Lista wybranych produktów", align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)
        
        # Pobieramy wszystkie wybrane produkty bez grupowania
        for product in selected_products:
            # Sprawdzamy czy zostało wystarczająco miejsca na stronie
            if pdf.get_y() > 250:
                pdf.add_page()
                pdf.set_font('DejaVuSans', size=12)
            
            # Nazwa produktu
            pdf.set_font('DejaVuSans-Bold', size=12)
            pdf.cell(0, 8, f"{product.name}", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Sklepy, w których dostępny jest produkt wraz z ceną
            if product.stores:
                pdf.set_x(30)
                pdf.set_font('DejaVuSans', size=10)
                pdf.cell(0, 6, "Dostępny w sklepach:", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                for store in product.stores:
                    price = product.get_price_for_store(store.id)
                    store_text = f"{store.name}"
                    if store.address:
                        store_text += f" ({store.address})"
                    store_text += f" - Cena: {price:.2f} zł"
                    pdf.bullet_text(store_text, indent=35)
            else:
                # Jeśli produkt nie jest przypisany do żadnego sklepu
                pdf.set_x(30)
                pdf.set_font('DejaVuSans', size=10)
                pdf.cell(0, 6, "Produkt nie jest przypisany do żadnego sklepu", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            
            # Opis produktu
            if product.description:
                pdf.set_font('DejaVuSans', size=10)
                pdf.set_x(30)
                pdf.cell(0, 6, "Opis produktu:", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                lines = product.description.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('-'):
                        # Jeśli linia zaczyna się od myślnika, używamy punktora
                        pdf.bullet_text(line[1:].strip(), indent=35)
                    else:
                        # W przeciwnym razie używamy zwykłego tekstu
                        pdf.normal_text(line, indent=35)
            
            # Informacje dla klienta
            if product.customer_info:
                pdf.set_font('DejaVuSans', size=10)
                pdf.set_x(30)
                pdf.cell(0, 6, "Informacje dla klienta:", align='L', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                lines = product.customer_info.split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('-'):
                        # Jeśli linia zaczyna się od myślnika, używamy punktora
                        pdf.bullet_text(line[1:].strip(), indent=35)
                    else:
                        # W przeciwnym razie używamy zwykłego tekstu
                        pdf.normal_text(line, indent=35)
            
            pdf.ln(5)
        
        pdf.output(response)
        response.seek(0)
        
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
        group_id = int(request.form.get('group_id'))
        image_url = request.form.get('image_url')
        store_ids = request.form.getlist('store_ids')
        
        # Pobieramy ceny dla każdego sklepu
        store_prices = {}
        for store_id in store_ids:
            price_key = f'price_{store_id}'
            if price_key in request.form and request.form.get(price_key):
                store_prices[int(store_id)] = float(request.form.get(price_key))
        
        product.name = name
        product.description = description
        product.customer_info = customer_info
        product.group_id = group_id
        product.image_url = image_url
        
        # Usuwamy wszystkie istniejące powiązania ze sklepami
        db.session.execute(
            store_products.delete().where(store_products.c.product_id == product_id)
        )
        
        # Dodajemy nowe powiązania ze sklepami i cenami
        for store_id in store_ids:
            store_id = int(store_id)
            price = store_prices.get(store_id, 0.0)
            
            # Dodajemy wpis do tabeli łączącej z ceną
            db.session.execute(
                store_products.insert().values(
                    store_id=store_id,
                    product_id=product.id,
                    price=price
                )
            )
        
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
    
    # Pobieramy ceny dla wszystkich sklepów produktu
    store_prices = {}
    for store in product.stores:
        price = product.get_price_for_store(store.id)
        store_prices[store.id] = price
    
    return jsonify({
        'id': product.id,
        'name': product.name,
        'description': product.description,
        'customer_info': product.customer_info,
        'group_id': product.group_id,
        'image_url': product.image_url,
        'store_ids': [store.id for store in product.stores],
        'store_prices': store_prices
    })

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

@app.route('/search_products')
@login_required
def search_products():
    query = request.args.get('query', '').strip().lower()
    if not query:
        return jsonify([])
    
    # Wyszukiwanie produktów zawierających podaną frazę w nazwie (case-insensitive)
    products = Product.query.filter(db.func.lower(Product.name).contains(query)).all()
    
    results = []
    for product in products:
        # Pobierz ceny dla wszystkich sklepów tego produktu
        store_prices = {}
        for store in product.stores:
            # Pobierz cenę z tabeli łączącej używając metody get_price_for_store
            price = product.get_price_for_store(store.id)
            store_prices[store.id] = {
                'store_name': store.name,
                'price': price
            }
        
        results.append({
            'id': product.id,
            'name': product.name,
            'description': product.description,
            'customer_info': product.customer_info,
            'image_url': product.image_url,
            'selected': product.selected,
            'group': {
                'id': product.group.id,
                'name': product.group.name
            } if product.group else None,
            'store_prices': store_prices
        })
    
    return jsonify(results)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False) 