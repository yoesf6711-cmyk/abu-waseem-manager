from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, abort
import sqlite3, os
from datetime import datetime
from contextlib import closing
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret")
DB = os.environ.get("DB_PATH", "business.db")

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def manager_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        if session.get("user_role") != "مدير":
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def log_movement(action, section, amount=0, details="", employee_id=None):
    try:
        with db() as conn:
            conn.execute("""
            INSERT INTO movement_log(date_time,user_id,employee_id,action,section,amount,details)
            VALUES(?,?,?,?,?,?,?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session.get("user_id"),
                employee_id or session.get("employee_id"),
                action, section, float(amount or 0), details
            ))
            conn.commit()
    except Exception:
        pass

def current_employee_id():
    return session.get("employee_id")

def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS employees(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            commission_rate REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS products(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            barcode TEXT UNIQUE,
            purchase_price REAL NOT NULL DEFAULT 0,
            sale_price REAL NOT NULL DEFAULT 0,
            stock REAL NOT NULL DEFAULT 0,
            min_stock REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            product_id INTEGER NOT NULL,
            employee_id INTEGER,
            qty REAL NOT NULL,
            sale_price REAL NOT NULL,
            cost_price REAL NOT NULL,
            profit REAL NOT NULL,
            commission REAL NOT NULL,
            payment_method TEXT,
            notes TEXT,
            FOREIGN KEY(product_id) REFERENCES products(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS repairs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            customer TEXT,
            device TEXT NOT NULL,
            issue TEXT,
            technician_id INTEGER,
            amount REAL NOT NULL,
            parts_cost REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL,
            commission REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'جاري',
            notes TEXT,
            FOREIGN KEY(technician_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS subscribers(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            plan TEXT,
            monthly_fee REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'فعال',
            debt REAL NOT NULL DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS network_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            payment_method TEXT
        );

        CREATE TABLE IF NOT EXISTS debts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            party TEXT NOT NULL,
            section TEXT NOT NULL,
            debt_type TEXT NOT NULL,
            amount REAL NOT NULL,
            paid REAL NOT NULL DEFAULT 0,
            due_date TEXT,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS balance_batches(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            provider TEXT,
            purchase_total REAL NOT NULL,
            sales_total REAL NOT NULL,
            profit REAL NOT NULL,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS service_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            service_type TEXT NOT NULL,
            description TEXT,
            cost REAL NOT NULL DEFAULT 0,
            sale REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL DEFAULT 0,
            employee_id INTEGER,
            commission REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            opening_balance REAL NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS account_transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            FOREIGN KEY(account_id) REFERENCES accounts(id)
        );


        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'موظف',
            employee_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS movement_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_time TEXT NOT NULL,
            user_id INTEGER,
            employee_id INTEGER,
            action TEXT NOT NULL,
            section TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            details TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS sim_sales(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            customer TEXT,
            phone_number TEXT,
            company TEXT,
            composite_material_cost REAL NOT NULL DEFAULT 0,
            sale_price REAL NOT NULL DEFAULT 0,
            profit REAL NOT NULL DEFAULT 0,
            employee_id INTEGER,
            commission REAL NOT NULL DEFAULT 0,
            payment_method TEXT,
            notes TEXT,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );

        CREATE TABLE IF NOT EXISTS payouts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            notes TEXT,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );
        """)
        # إنشاء حساب مدير افتراضي عند أول تشغيل
        if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            conn.execute(
                "INSERT INTO users(username,password_hash,role,is_active) VALUES(?,?,?,1)",
                ("admin", generate_password_hash("123456"), "مدير")
            )
        conn.commit()

@app.template_filter("money")
def money(v):
    try:
        return f"{float(v):,.0f}"
    except:
        return "0"

def scalar(query, params=()):
    with db() as conn:
        row = conn.execute(query, params).fetchone()
        return row[0] if row else 0


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        with db() as conn:
            user = conn.execute("SELECT * FROM users WHERE username=? AND is_active=1",(username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["user_role"] = user["role"]
            session["employee_id"] = user["employee_id"]
            log_movement("تسجيل دخول","النظام",0,f"المستخدم: {username}",user["employee_id"])
            return redirect(url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة")
    return render_template("login.html")

@app.route("/logout")
def logout():
    if session.get("user_id"):
        log_movement("تسجيل خروج","النظام",0,f"المستخدم: {session.get('username')}")
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def dashboard():
    stats = {
        "stock_value": scalar("SELECT COALESCE(SUM(stock*purchase_price),0) FROM products"),
        "sales_profit": scalar("SELECT COALESCE(SUM(profit),0) FROM sales"),
        "repair_profit": scalar("SELECT COALESCE(SUM(profit),0) FROM repairs"),
        "network_income": scalar("SELECT COALESCE(SUM(CASE WHEN type='دخل' THEN amount ELSE 0 END),0) FROM network_transactions"),
        "network_expense": scalar("SELECT COALESCE(SUM(CASE WHEN type='مصروف' THEN amount ELSE 0 END),0) FROM network_transactions"),
        "receivables": scalar("SELECT COALESCE(SUM(amount-paid),0) FROM debts WHERE debt_type='لنا'"),
        "payables": scalar("SELECT COALESCE(SUM(amount-paid),0) FROM debts WHERE debt_type='علينا'"),
        "subscribers": scalar("SELECT COUNT(*) FROM subscribers WHERE status='فعال'"),
        "sales_commission": scalar("SELECT COALESCE(SUM(commission),0) FROM sales"),
        "repair_commission": scalar("SELECT COALESCE(SUM(commission),0) FROM repairs"),
        "service_profit": scalar("SELECT COALESCE(SUM(profit),0) FROM service_transactions"),
        "service_commission": scalar("SELECT COALESCE(SUM(commission),0) FROM service_transactions"),
        "balance_profit": scalar("SELECT COALESCE(SUM(profit),0) FROM balance_batches"),
        "sim_profit": scalar("SELECT COALESCE(SUM(profit),0) FROM sim_sales"),
        "sim_commission": scalar("SELECT COALESCE(SUM(commission),0) FROM sim_sales"),
    }
    stats["network_net"] = stats["network_income"] - stats["network_expense"]
    stats["partner_share"] = stats["network_net"] * 0.5
    stats["shop_net_profit"] = (
        stats["sales_profit"] - stats["sales_commission"] +
        stats["repair_profit"] - stats["repair_commission"] +
        stats["service_profit"] - stats["service_commission"] +
        stats["balance_profit"] +
        stats["sim_profit"] - stats["sim_commission"]
    )
    stats["business_net_profit"] = stats["shop_net_profit"] + (stats["network_net"] * 0.5)
    with db() as conn:
        emp_filter = session.get("employee_id") if session.get("user_role") != "مدير" else None
        if emp_filter:
            recent_sales = conn.execute("""SELECT s.*,p.name product,e.name employee
            FROM sales s JOIN products p ON p.id=s.product_id
            LEFT JOIN employees e ON e.id=s.employee_id
            WHERE s.employee_id=? ORDER BY s.id DESC LIMIT 8""",(emp_filter,)).fetchall()
        else:
            recent_sales = conn.execute("""SELECT s.*,p.name product,e.name employee
            FROM sales s JOIN products p ON p.id=s.product_id
            LEFT JOIN employees e ON e.id=s.employee_id
            ORDER BY s.id DESC LIMIT 8""").fetchall()
        low_stock = conn.execute("SELECT * FROM products WHERE stock <= min_stock ORDER BY stock ASC LIMIT 8").fetchall()
    return render_template("dashboard.html", stats=stats, recent_sales=recent_sales, low_stock=low_stock)

@app.route("/employees", methods=["GET","POST"])
@manager_required
def employees():
    if request.method == "POST":
        with db() as conn:
            cur = conn.execute("INSERT INTO employees(name,role,commission_rate) VALUES(?,?,?)",
                         (request.form["name"], request.form["role"], float(request.form.get("commission_rate",0))))
            employee_id = cur.lastrowid
            username = request.form.get("username","").strip()
            password = request.form.get("password","").strip()
            if username and password:
                conn.execute("""INSERT INTO users(username,password_hash,role,employee_id,is_active)
                VALUES(?,?,?,?,1)""",(username,generate_password_hash(password),"موظف",employee_id))
            conn.commit()
        log_movement("إضافة موظف","الموظفون",0,f"{request.form['name']} - {request.form['role']}",employee_id)
        flash("تمت إضافة الموظف")
        return redirect(url_for("employees"))
    month = request.args.get("month", datetime.now().strftime("%Y-%m"))
    with db() as conn:
        rows = conn.execute("SELECT * FROM employees ORDER BY id DESC").fetchall()
        settlements = conn.execute("""
        SELECT e.id,e.name,e.role,
          COALESCE((SELECT SUM(commission) FROM sales s WHERE s.employee_id=e.id AND substr(s.date,1,7)=?),0) +
          COALESCE((SELECT SUM(commission) FROM repairs r WHERE r.technician_id=e.id AND substr(r.date,1,7)=?),0) +
          COALESCE((SELECT SUM(commission) FROM service_transactions t WHERE t.employee_id=e.id AND substr(t.date,1,7)=?),0)
          AS earned,
          COALESCE((SELECT SUM(amount) FROM payouts p WHERE p.employee_id=e.id AND p.month=?),0) AS paid
        FROM employees e ORDER BY e.name
        """,(month,month,month,month)).fetchall()
    return render_template("employees.html", rows=rows, settlements=settlements, month=month)

@app.post("/payout")
@manager_required
def payout():
    with db() as conn:
        conn.execute("INSERT INTO payouts(employee_id,month,amount,date,notes) VALUES(?,?,?,?,?)",
                     (request.form["employee_id"],request.form["month"],float(request.form["amount"]),
                      request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),request.form.get("notes")))
        conn.commit()
    log_movement("تسليم موظف","الموظفون",float(request.form["amount"]),f"شهر {request.form['month']}",request.form["employee_id"])
    flash("تم تسجيل التسليم للموظف")
    return redirect(url_for("employees", month=request.form["month"]))

@app.route("/products", methods=["GET","POST"])
@login_required
def products():
    if request.method == "POST":
        barcode = request.form.get("barcode") or datetime.now().strftime("%y%m%d%H%M%S")
        with db() as conn:
            conn.execute("""INSERT INTO products(name,category,barcode,purchase_price,sale_price,stock,min_stock)
            VALUES(?,?,?,?,?,?,?)""",(request.form["name"],request.form["category"],barcode,
            float(request.form["purchase_price"]),float(request.form["sale_price"]),
            float(request.form["stock"]),float(request.form.get("min_stock",0))))
            conn.commit()
        log_movement("إضافة صنف","المخزون",float(request.form["purchase_price"])*float(request.form["stock"]),request.form["name"])
        flash("تمت إضافة الصنف للمخزون")
        return redirect(url_for("products"))
    q = request.args.get("q","")
    with db() as conn:
        rows = conn.execute("SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? ORDER BY id DESC",
                            (f"%{q}%",f"%{q}%")).fetchall()
    return render_template("products.html", rows=rows, q=q)

@app.route("/sales", methods=["GET","POST"])
@login_required
def sales():
    if request.method == "POST":
        product_id=int(request.form["product_id"]); qty=float(request.form["qty"]); sale_price=float(request.form["sale_price"])
        employee_id=(current_employee_id() if session.get("user_role")!="مدير" else (request.form.get("employee_id") or None))
        with db() as conn:
            p=conn.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
            if not p or p["stock"] < qty:
                flash("الكمية غير متوفرة")
                return redirect(url_for("sales"))
            rate=0
            if employee_id:
                e=conn.execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
                rate=float(e["commission_rate"]) if e else 0
            profit=(sale_price-float(p["purchase_price"]))*qty
            commission=max(profit,0)*rate/100
            conn.execute("""INSERT INTO sales(date,product_id,employee_id,qty,sale_price,cost_price,profit,commission,payment_method,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",(request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
            product_id,employee_id,qty,sale_price,p["purchase_price"],profit,commission,
            request.form.get("payment_method"),request.form.get("notes")))
            conn.execute("UPDATE products SET stock=stock-? WHERE id=?",(qty,product_id))
            conn.commit()
        log_movement("بيع","المبيعات",sale_price*qty,f"الصنف رقم {product_id} - كمية {qty}",employee_id)
        flash("تم تسجيل البيع واحتساب العمولة")
        return redirect(url_for("sales"))
    with db() as conn:
        products=conn.execute("SELECT * FROM products WHERE stock>0 ORDER BY name").fetchall()
        employees=conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
        rows=conn.execute("""SELECT s.*,p.name product,e.name employee FROM sales s
        JOIN products p ON p.id=s.product_id LEFT JOIN employees e ON e.id=s.employee_id
        ORDER BY s.id DESC LIMIT 100""").fetchall()
    return render_template("sales.html", products=products, employees=employees, rows=rows)

@app.route("/repairs", methods=["GET","POST"])
@login_required
def repairs():
    if request.method == "POST":
        technician_id=(current_employee_id() if session.get("user_role")!="مدير" else (request.form.get("technician_id") or None))
        amount=float(request.form["amount"]); parts=float(request.form.get("parts_cost",0)); profit=amount-parts
        rate=0
        with db() as conn:
            if technician_id:
                e=conn.execute("SELECT * FROM employees WHERE id=?",(technician_id,)).fetchone()
                rate=float(e["commission_rate"]) if e else 50
            commission=max(profit,0)*rate/100
            conn.execute("""INSERT INTO repairs(date,customer,device,issue,technician_id,amount,parts_cost,profit,commission,status,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
            request.form.get("customer"),request.form["device"],request.form.get("issue"),technician_id,
            amount,parts,profit,commission,request.form.get("status","جاري"),request.form.get("notes")))
            conn.commit()
        log_movement("صيانة","الصيانة",amount,f"{request.form['device']} - {request.form.get('customer','')}",technician_id)
        flash("تم تسجيل الصيانة واحتساب حصة الفني")
        return redirect(url_for("repairs"))
    with db() as conn:
        employees=conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
        rows=conn.execute("""SELECT r.*,e.name technician FROM repairs r
        LEFT JOIN employees e ON e.id=r.technician_id ORDER BY r.id DESC LIMIT 100""").fetchall()
    return render_template("repairs.html", employees=employees, rows=rows)

@app.route("/network", methods=["GET","POST"])
@login_required
def network():
    if request.method == "POST":
        kind=request.form["kind"]
        with db() as conn:
            if kind=="subscriber":
                conn.execute("""INSERT INTO subscribers(name,phone,plan,monthly_fee,status,debt,notes)
                VALUES(?,?,?,?,?,?,?)""",(request.form["name"],request.form.get("phone"),request.form.get("plan"),
                float(request.form.get("monthly_fee",0)),request.form.get("status","فعال"),
                float(request.form.get("debt",0)),request.form.get("notes")))
            else:
                conn.execute("""INSERT INTO network_transactions(date,type,amount,description,payment_method)
                VALUES(?,?,?,?,?)""",(request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
                request.form["type"],float(request.form["amount"]),request.form.get("description"),
                request.form.get("payment_method")))
            conn.commit()
        log_movement("حركة شبكة","الشبكة",float(request.form.get("amount",0) or 0),request.form.get("description") or request.form.get("name",""))
        flash("تم الحفظ في قسم الشبكة")
        return redirect(url_for("network"))
    with db() as conn:
        subscribers=conn.execute("SELECT * FROM subscribers ORDER BY id DESC LIMIT 100").fetchall()
        tx=conn.execute("SELECT * FROM network_transactions ORDER BY id DESC LIMIT 100").fetchall()
        totals=conn.execute("""SELECT
        COALESCE(SUM(CASE WHEN type='دخل' THEN amount ELSE 0 END),0) income,
        COALESCE(SUM(CASE WHEN type='مصروف' THEN amount ELSE 0 END),0) expense
        FROM network_transactions""").fetchone()
    return render_template("network.html", subscribers=subscribers, tx=tx, totals=totals)

@app.route("/debts", methods=["GET","POST"])
@manager_required
def debts():
    if request.method=="POST":
        with db() as conn:
            conn.execute("""INSERT INTO debts(date,party,section,debt_type,amount,paid,due_date,notes)
            VALUES(?,?,?,?,?,?,?,?)""",(request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
            request.form["party"],request.form["section"],request.form["debt_type"],
            float(request.form["amount"]),float(request.form.get("paid",0)),
            request.form.get("due_date"),request.form.get("notes")))
            conn.commit()
        log_movement("إضافة دين","الديون",float(request.form["amount"]),f"{request.form['party']} - {request.form['section']}")
        flash("تم تسجيل الدين")
        return redirect(url_for("debts"))
    with db() as conn:
        rows=conn.execute("SELECT * FROM debts ORDER BY id DESC").fetchall()
    return render_template("debts.html", rows=rows)

@app.post("/debt/payment/<int:debt_id>")
@manager_required
def debt_payment(debt_id):
    amount=float(request.form["amount"])
    with db() as conn:
        conn.execute("UPDATE debts SET paid=MIN(amount,paid+?) WHERE id=?",(amount,debt_id))
        conn.commit()
    log_movement("دفعة دين","الديون",amount,f"الدين رقم {debt_id}")
    flash("تم تسجيل الدفعة")
    return redirect(url_for("debts"))

@app.route("/services", methods=["GET","POST"])
@login_required
def services():
    if request.method=="POST":
        st=request.form["service_type"]
        if st=="رصيد يومي":
            purchase=float(request.form.get("cost",0)); sales=float(request.form.get("sale",0))
            with db() as conn:
                conn.execute("INSERT INTO balance_batches(date,provider,purchase_total,sales_total,profit,notes) VALUES(?,?,?,?,?,?)",
                (request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),request.form.get("description"),
                 purchase,sales,sales-purchase,request.form.get("notes")))
                conn.commit()
        else:
            cost=float(request.form.get("cost",0)); sale=float(request.form.get("sale",0)); profit=sale-cost
            employee_id=(current_employee_id() if session.get("user_role")!="مدير" else (request.form.get("employee_id") or None))
            rate=0
            with db() as conn:
                if employee_id:
                    e=conn.execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
                    rate=float(e["commission_rate"]) if e else 0
                commission=max(profit,0)*rate/100
                conn.execute("""INSERT INTO service_transactions(date,service_type,description,cost,sale,profit,employee_id,commission)
                VALUES(?,?,?,?,?,?,?,?)""",(request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
                st,request.form.get("description"),cost,sale,profit,employee_id,commission))
                conn.commit()
        log_movement("خدمة","الخدمات",float(request.form.get("sale",0) or 0),request.form.get("service_type",""))
        flash("تم تسجيل العملية")
        return redirect(url_for("services"))
    with db() as conn:
        employees=conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
        rows=conn.execute("""SELECT t.*,e.name employee FROM service_transactions t
        LEFT JOIN employees e ON e.id=t.employee_id ORDER BY t.id DESC LIMIT 100""").fetchall()
        balance=conn.execute("SELECT * FROM balance_batches ORDER BY id DESC LIMIT 100").fetchall()
    return render_template("services.html", employees=employees, rows=rows, balance=balance)

@app.route("/accounts", methods=["GET","POST"])
@manager_required
def accounts():
    if request.method=="POST":
        kind=request.form["kind"]
        with db() as conn:
            if kind=="account":
                conn.execute("INSERT INTO accounts(name,account_type,opening_balance) VALUES(?,?,?)",
                             (request.form["name"],request.form["account_type"],float(request.form.get("opening_balance",0))))
            else:
                conn.execute("INSERT INTO account_transactions(date,account_id,type,amount,description) VALUES(?,?,?,?,?)",
                             (request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
                              request.form["account_id"],request.form["type"],float(request.form["amount"]),
                              request.form.get("description")))
            conn.commit()
        log_movement("حركة حساب","المحافظ والبنوك",float(request.form.get("amount",0) or 0),request.form.get("description") or request.form.get("name",""))
        flash("تم الحفظ")
        return redirect(url_for("accounts"))
    with db() as conn:
        accounts=conn.execute("""SELECT a.*,
        opening_balance + COALESCE(SUM(CASE WHEN t.type='إيداع' THEN t.amount ELSE -t.amount END),0) balance
        FROM accounts a LEFT JOIN account_transactions t ON t.account_id=a.id
        GROUP BY a.id ORDER BY a.id DESC""").fetchall()
        tx=conn.execute("""SELECT t.*,a.name account FROM account_transactions t
        JOIN accounts a ON a.id=t.account_id ORDER BY t.id DESC LIMIT 100""").fetchall()
    return render_template("accounts.html", accounts=accounts, tx=tx)


@app.route("/sim-sales", methods=["GET","POST"])
@login_required
def sim_sales():
    if request.method == "POST":
        employee_id = current_employee_id() if session.get("user_role") != "مدير" else (request.form.get("employee_id") or None)
        material = float(request.form.get("composite_material_cost",0))
        sale_price = float(request.form.get("sale_price",0))
        profit = sale_price - material
        rate = 0
        with db() as conn:
            if employee_id:
                e = conn.execute("SELECT * FROM employees WHERE id=?",(employee_id,)).fetchone()
                rate = float(e["commission_rate"]) if e else 0
            commission = max(profit,0) * rate / 100
            conn.execute("""INSERT INTO sim_sales(date,customer,phone_number,company,
            composite_material_cost,sale_price,profit,employee_id,commission,payment_method,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(
                request.form.get("date") or datetime.now().strftime("%Y-%m-%d"),
                request.form.get("customer"),request.form.get("phone_number"),
                request.form.get("company"),material,sale_price,profit,employee_id,
                commission,request.form.get("payment_method"),request.form.get("notes")
            ))
            conn.commit()
        log_movement("بيع خط","الخطوط",sale_price,
                     f"{request.form.get('company','')} - مادة مركبة {material}",employee_id)
        flash("تم تسجيل بيع الخط وخصم قيمة المادة المركبة")
        return redirect(url_for("sim_sales"))
    with db() as conn:
        employees = conn.execute("SELECT * FROM employees WHERE role IN ('موظف مبيعات','مبيعات + فني صيانة') ORDER BY name").fetchall()
        if session.get("user_role") == "مدير":
            rows = conn.execute("""SELECT s.*,e.name employee FROM sim_sales s
            LEFT JOIN employees e ON e.id=s.employee_id ORDER BY s.id DESC LIMIT 200""").fetchall()
        else:
            rows = conn.execute("""SELECT s.*,e.name employee FROM sim_sales s
            LEFT JOIN employees e ON e.id=s.employee_id WHERE s.employee_id=?
            ORDER BY s.id DESC LIMIT 200""",(current_employee_id(),)).fetchall()
    return render_template("sim_sales.html", employees=employees, rows=rows)

@app.route("/movements")
@manager_required
def movements():
    q = request.args.get("q","")
    with db() as conn:
        rows = conn.execute("""SELECT m.*,u.username,e.name employee
        FROM movement_log m LEFT JOIN users u ON u.id=m.user_id
        LEFT JOIN employees e ON e.id=m.employee_id
        WHERE m.action LIKE ? OR m.section LIKE ? OR m.details LIKE ?
        ORDER BY m.id DESC LIMIT 1000""",(f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
    return render_template("movements.html", rows=rows, q=q)

@app.route("/users", methods=["GET","POST"])
@manager_required
def users():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        with db() as conn:
            conn.execute("""INSERT INTO users(username,password_hash,role,employee_id,is_active)
            VALUES(?,?,?,?,1)""",(username,generate_password_hash(password),
            request.form["role"],request.form.get("employee_id") or None))
            conn.commit()
        log_movement("إضافة مستخدم","المستخدمون",0,username,request.form.get("employee_id") or None)
        flash("تم إنشاء المستخدم")
        return redirect(url_for("users"))
    with db() as conn:
        rows = conn.execute("""SELECT u.*,e.name employee FROM users u
        LEFT JOIN employees e ON e.id=u.employee_id ORDER BY u.id DESC""").fetchall()
        employees = conn.execute("SELECT * FROM employees ORDER BY name").fetchall()
    return render_template("users.html", rows=rows, employees=employees)

@app.post("/users/<int:user_id>/password")
@manager_required
def user_password(user_id):
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?",
                     (generate_password_hash(request.form["password"]),user_id))
        conn.commit()
    log_movement("تغيير كلمة مرور","المستخدمون",0,f"المستخدم رقم {user_id}")
    flash("تم تغيير كلمة المرور")
    return redirect(url_for("users"))

@app.route("/barcode/<int:product_id>")
@login_required
def barcode(product_id):
    with db() as conn:
        p=conn.execute("SELECT * FROM products WHERE id=?",(product_id,)).fetchone()
    return render_template("barcode.html", p=p)

@app.route("/api/product/<code>")
@login_required
def api_product(code):
    with db() as conn:
        p=conn.execute("SELECT * FROM products WHERE barcode=?",(code,)).fetchone()
    return jsonify(dict(p) if p else {})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)), debug=False)
