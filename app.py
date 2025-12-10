from flask import Flask , render_template , url_for ,redirect , flash , request, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin , LoginManager , login_user , login_required , current_user , logout_user
from flask_wtf import FlaskForm
from wtforms import StringField , PasswordField , SubmitField , DateField
from wtforms.validators import InputRequired, Length , ValidationError
from werkzeug.security import check_password_hash , generate_password_hash
from datetime import datetime
from api import fetch_employee_data
from apar_api import check_employee
import os
import re

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://flask_app:flask@localhost:5432/app01'
app.config['SECRET_KEY'] = "supersecretkey"
PDF_DIRECTORY = "./pdfs" 
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def user_loader(user_id):
    return db.session.get(User, int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer , primary_key=True)
    username = db.Column(db.String(20),unique=True , nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Employee(db.Model):
    cdac_emp_id = db.Column(db.String(255), primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    dept = db.Column(db.String(255), nullable=False)
    designation = db.Column(db.String(255), nullable=False)
    dob = db.Column(db.String , nullable=False)
    doj = db.Column(db.String, nullable=False)
    mobile_no = db.Column(db.String(255), nullable=False)
    father_name = db.Column(db.String(255))
    dossier_no = db.Column(db.String(255), nullable=False)

class PreviousAPAR(db.Model):
    id = db.Column(db.Integer , primary_key=True)
    cdac_emp_id = db.Column(db.String(255), db.ForeignKey('employee.cdac_emp_id'))
    name = db.Column(db.String, nullable=False)
    apar_status = db.Column(db.Text)
    # year = db.Column(db.String(255), nullable=True)
    date_from = db.Column(db.Date , nullable=False)
    date_to = db.Column(db.Date , nullable=False)
    grade = db.Column(db.String)
    grade_label =db.Column(db.String)
    reporting_officer = db.Column(db.String)
    reviewing_officer = db.Column(db.String)

class PDFMetadata(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dossier_number = db.Column(db.String(20))
    apar_employee_name = db.Column(db.String(100))
    employee_id = db.Column(db.String(20))
    name = db.Column(db.String(100))
    current_designation = db.Column(db.String(100))
    filename = db.Column(db.String(200), unique=True, nullable=False)

def parse_filename(filename):
    # Remove .pdf extension and split by hyphen
    base_name = os.path.splitext(filename)[0]
    parts = re.split(r'[-_]', base_name)
    
    # Extract dossier number (first part, may include suffixes like A, A-1)
    dossier_number = parts[0].strip()
    if not dossier_number.isdigit():
        # Handle cases like "6471-A" or "6398-A-1"
        match = re.match(r'(\d+)([A-Za-z-0-9]*)$', dossier_number)
        if match:
            dossier_number = match.group(1) + (match.group(2) if match.group(2) else "")
    
    # Extract APAR employee name (remaining parts, joined and cleaned)
    apar_name_parts = [part for part in parts[1:] if part]
    apar_employee_name = " ".join(apar_name_parts).replace("pdf", "").replace("(2)", "").strip()
    
    return dossier_number, apar_employee_name

def populate_database():
    if not os.path.exists(PDF_DIRECTORY):
        os.makedirs(PDF_DIRECTORY)
        return
    
    for filename in os.listdir(PDF_DIRECTORY):
        if filename.lower().endswith(".pdf"):
            file_path = os.path.join(PDF_DIRECTORY, filename)
            dossier_number, apar_employee_name = parse_filename(filename)
            
            # Check if record exists
            existing_record = PDFMetadata.query.filter_by(filename=filename).first()
            if existing_record:
                existing_record.dossier_number = dossier_number
                existing_record.apar_employee_name = apar_employee_name
            else:
                new_record = PDFMetadata(
                    dossier_number=dossier_number,
                    apar_employee_name=apar_employee_name,
                    filename=filename
                )
                db.session.add(new_record)
    db.session.commit()

class RegisterForms(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(
        min=4, max=20)], render_kw={"placeholder":"username"})  
    password = PasswordField(validators=[InputRequired(), Length(
        min=4, max=20)], render_kw={"placeholder":"password"})
    submit = SubmitField("Register")
    def validate_username(self, username):
        existing_user_username = User.query.filter_by(username=username.data).first()
        if existing_user_username:
            raise ValidationError(
                "username already exist. Please change username"
            )

class LoginForms(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(
        min=4, max=20)], render_kw={"placeholder":"username"})  
    password = PasswordField(validators=[InputRequired(), Length(
        min=4, max=20)], render_kw={"placeholder":"password"})
    submit = SubmitField("Login")

class EmployeeForms(FlaskForm):
    cdac_emp_id = StringField("CDAC Employee ID", validators=[InputRequired(), Length(
        min=4, max=20)], render_kw={"placeholder":"CDAC EMPLOYEE ID"})
    name = StringField("Employee name", render_kw={'readonly':True, "placeholder":"Employee name"})
    dept = StringField("Department", render_kw={'readonly':True, "placeholder":"Department"})
    designation = StringField("Designation", render_kw={'readonly':True, "placeholder":"Designation"})
    dob = StringField("Date of Birth", render_kw={'readonly':True, "placeholder":"Date of Birth"})
    doj = StringField("Date of Joining",render_kw={'readonly':True, "placeholder":"Date of Joining"})
    mobile_no = StringField("Mobile Number", render_kw={'readonly':True, "placeholder":"Mobile Number"})
    father_name = StringField("Father Name", render_kw={'readonly':True, "placeholder":"Father name"})
    dossier_no = StringField("Dossier" , validators=[InputRequired(),Length(
        min=1, max=20)], render_kw={"placeholder":"Dossier"})
    submit = SubmitField("Save")

class APARForms(FlaskForm):
    cdac_emp_id = StringField("CDAC Employee ID", render_kw={"placeholder":"CDAC EMPLOYEE ID"})
    name = StringField("Employee name", render_kw={'readonly':True, "placeholder":"Employee name"})
    apar_status = StringField("APAR Status", render_kw={'readonly':True, "placeholder":"APAR Status"})
    # year = StringField("Year", render_kw={'readonly':True, "placeholder":"Year"})
    date_from = DateField("Date From", render_kw={'readonly':True, "placeholder":"Date From"}, format="%d-%b-%Y")
    date_to = DateField("Date To", render_kw={'readonly':True, "placeholder":"Date To"}, format="%d-%b-%Y")
    grade = StringField("Grade", render_kw={'readonly':True, "placeholder":"Grade"})
    grade_label = StringField("Grade Label", render_kw={'readonly':True, "placeholder":"Grade Label"})
    reporting_officer = StringField("Reporting Officer", render_kw={'readonly':True , "placeholder":"Reporting Officer"})
    reviewing_officer = StringField("Reviewing Officer", render_kw={'readonly':True , "placeholder":"Reviewing Officer"})
    submit = SubmitField("Save")

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForms()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid username or password", "login")
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET','POST'])
def register():
    form = RegisterForms()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(username=form.username.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/dashboard', methods=['GET' , 'POST'])
@login_required
def dashboard():
    page =request.args.get('page',1 ,type=int)
    search = request.args.get('search', '', type=str)
    sort_by = request.args.get('sort_by', 'name', type=str)
    order = request.args.get('order', 'asc', type=str)
    
    query = Employee.query
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            db.or_(
                Employee.cdac_emp_id.ilike(search_pattern),
                Employee.name.ilike(search_pattern),
                Employee.dept.ilike(search_pattern),
                Employee.dossier_no.ilike(search_pattern)
            )
        )

    if hasattr(Employee, sort_by):
        column = getattr(Employee, sort_by)
        if order == 'desc':
            column = column.desc()
        else:
            column = column.asc()
        query = query.order_by(column)
    # query = Employee.query.order_by(Employee.cdac_emp_id.asc())
    pagination = query.paginate(page=page, per_page=10)
    employees = pagination.items
    return render_template('dashboard.html', employees=employees, pagination=pagination, sort_by=sort_by, order=order,search=search)

@app.route('/employee', methods=['GET' , 'POST'])
@login_required
def employee():
    form = EmployeeForms()
    apar_form = APARForms()
    emp_id = request.args.get('cdac_emp_id')
    action = request.args.get('action')
    all_apars = []
    apar_response = None
    show_employee = False
    if emp_id:
        if action == "sahas":
            emp_data = fetch_employee_data(emp_id)
            if emp_data and 'Data' in emp_data and emp_data['Data']:
                emp_info = emp_data['Data'][0]
                form.cdac_emp_id.data = emp_id
                form.name.data = emp_info.get('name')
                form.dept.data = emp_info.get('department')
                form.designation.data = emp_info.get('designation')
                form.dob.data = emp_info.get("date_of_birth")
                form.doj.data = emp_info.get("date_of_joining")
                form.mobile_no.data = emp_info.get('mobile_number')
                form.father_name.data = emp_info.get('father_name')
                show_employee = True
            else:
                flash("Employee data not found or invalid response from API", "danger")
        elif action == "apar":
            apar_data = check_employee(emp_id)
            if apar_data and apar_data.get("success") == '1':
                # flash("Employee ID found", "success")                
                for record in apar_data["data"]:
                    apar_entry = {
                        "cdac_emp_id": emp_id,
                        "name": record.get("employee"),
                        "reporting_officer": record.get("reporting_officer"),
                        "reviewing_officer": record.get("reviewing_officer"),
                        "apar_status": record.get("status"),
                        "grade": record.get("grade"),
                        "grade_label": record.get("grade_label"),
                        "date_from": datetime.strptime(record.get("date_from"), "%Y-%m-%d"),
                        "date_to": datetime.strptime(record.get("date_to"), "%Y-%m-%d")
                    }
                    all_apars.append(apar_entry)
            else :
                flash("Employee ID not found","danger")

    if request.method == "POST" and request.form.get("save_apar"):
        for record in all_apars:
            existing = PreviousAPAR.query.filter_by(
                cdac_emp_id=emp_id,
                date_from=record["date_from"],
                date_to=record["date_to"]
            ).first()
            if not existing:
                new_apar = PreviousAPAR(**record)
                db.session.add(new_apar)
        db.session.commit()
        flash("APAR records saved successfully!", "success")
        return redirect(url_for("dashboard", cdac_emp_id=emp_id, action="apar"))

    if form.validate_on_submit():
        existing_emp = Employee.query.filter_by(cdac_emp_id=form.cdac_emp_id.data).first()
        if existing_emp:
            flash("Employee already in database!", "danger")
            return redirect(url_for("employee"))
        else:
            new_emp = Employee(
                cdac_emp_id=form.cdac_emp_id.data,
                name=form.name.data,
                dept=form.dept.data,
                designation=form.designation.data,
                mobile_no=form.mobile_no.data,
                dob=form.dob.data,
                doj=form.doj.data,
                father_name=form.father_name.data,
                dossier_no=form.dossier_no.data
            )
            db.session.add(new_emp)
            db.session.commit()
            flash("Employee Added Successfully!", "success")
            return redirect(url_for("employee"))
    return render_template('employee.html',form=form , apar_form=apar_form, apar_list=all_apars , show_employee = show_employee)

@app.route('/logout', methods=['GET' , 'POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route("/index", methods=["GET"])
@login_required
def index():
    # Get search queries from request
    dossier_query = request.args.get("dossier", "").lower()
    apar_query = request.args.get("apar", "").lower()
    emp_id_query = request.args.get("emp_id", "").lower()
    name_query = request.args.get("name", "").lower()
    designation_query = request.args.get("designation", "").lower()
    filename_query = request.args.get("filename", "").lower()
    sort_by = request.args.get("sort_by", "dossier_number")
    sort_order = request.args.get("sort_order", "asc")
    page =request.args.get('page',1 ,type=int)

    # Query database with filters
    query = PDFMetadata.query
    if dossier_query:
        query = query.filter(db.func.lower(PDFMetadata.dossier_number).like(f"%{dossier_query}%"))
    if apar_query:
        query = query.filter(db.func.lower(PDFMetadata.apar_employee_name).like(f"%{apar_query}%"))
    if emp_id_query:
        query = query.filter(db.func.lower(PDFMetadata.employee_id).like(f"%{emp_id_query}%"))
    if name_query:
        query = query.filter(db.func.lower(PDFMetadata.name).like(f"%{name_query}%"))
    if designation_query:
        query = query.filter(db.func.lower(PDFMetadata.current_designation).like(f"%{designation_query}%"))
    if filename_query:
        query = query.filter(db.func.lower(PDFMetadata.filename).like(f"%{filename_query}%"))

    # Apply sorting
    if sort_order == "desc":
        query = query.order_by(getattr(PDFMetadata, sort_by).desc())
    else:
        query = query.order_by(getattr(PDFMetadata, sort_by).asc())
    pagination = query.paginate(page=page, per_page=10)
    pdf_records = pagination.items

    # pdf_records = query.all()
    return render_template("index.html", pdf_records=pdf_records, sort_by=sort_by, sort_order=sort_order, pagination=pagination)

@app.route("/view/<filename>")
@login_required
def view_pdf(filename):
    file_path = os.path.join(PDF_DIRECTORY, filename)
    if not os.path.exists(file_path) or not filename.lower().endswith(".pdf"):
        abort(404)
    return send_file(file_path, mimetype="application/pdf")

@app.route("/download/<filename>")
@login_required
def download_pdf(filename):
    file_path = os.path.join(PDF_DIRECTORY, filename)
    if not os.path.exists(file_path) or not filename.lower().endswith(".pdf"):
        abort(404)
    return send_file(file_path, as_attachment=True)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.route("/detail")
@login_required
def detail():
    emp_id = request.args.get("cdac_emp_id")
    if not emp_id:
        flash("Employee ID is required", "danger")
        return redirect(url_for("dashboard"))

    emp = db.session.get(Employee, emp_id)
    if not emp:
        flash("Employee not found", "danger")
        return redirect(url_for("dashboard"))

    apars = PreviousAPAR.query.filter_by(cdac_emp_id=emp_id).all() 
    pdfs = PDFMetadata.query.filter_by(dossier_number=emp.dossier_no).all()
    return render_template("view_emp.html", emp=emp, apars=apars , pdfs=pdfs)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # Create database tables
        populate_database()  # Populate database with PDF metadata
    app.run(host="0.0.0.0", port=5000, debug=False)
