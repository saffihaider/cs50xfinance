import os

from cs50 import SQL
from math import trunc
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    rows = db.execute("SELECT name, shares FROM stocks WHERE user_id = :user_id", user_id=session["user_id"])
    table = []
    cash = db.execute("SELECT cash FROM users WHERE id = (?)",
                        (session["user_id"]))[0]["cash"]
    assets = cash
    for row in rows:
        symbol = row["name"].upper()
        name = lookup(symbol)["name"]
        shares = row["shares"]
        value = round(lookup(symbol)["price"], 2)
        total = round(float(value) * int(shares), 2)
        assets += total
        temp = [symbol, name, shares, value, total]
        table.append(temp)
    return render_template("index.html", table=table, cash='%.2f'%(cash), assets = '%.2f'%(assets))

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "GET":
        return render_template("settings.html")
    if request.method == "POST":
        password = request.form.get("pass")
        passconf = request.form.get("passconf")

        if password != passconf:
            return apology("Passwords do not match")

        newpass = generate_password_hash(password)
        dbpass = db.execute("UPDATE users SET hash = :hashed WHERE id = :user_id", hashed=newpass, user_id=session["user_id"])

        return redirect("/")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    else:
        symbol = request.form.get("symbol").upper()
        if not symbol or lookup(symbol) == None:
            return apology("Invalid stock symbol")

        price = lookup(symbol)["price"]
        shares = request.form.get("shares")
        cash = db.execute("SELECT cash FROM users WHERE id = (?)",
                        (session["user_id"]))[0]["cash"]
        stockvalue = round(float(price) * int(shares), 2)

        if stockvalue > cash:
            return apology("You do not have enough cash!")
        cash -= stockvalue
        trans = "BUY"
        time = datetime.now()

        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

        db.execute("INSERT INTO history (symbol, shares, price, type, user_id, time) VALUES (?,?,?,?,?,?)", symbol, shares, price, trans, session["user_id"], time)

        if len(db.execute("SELECT name FROM stocks WHERE user_id = :userid AND name = :name", userid=session["user_id"], name=symbol)) == 0:
            db.execute("INSERT INTO stocks (user_id, name, shares) VALUES (?,?,?)", session["user_id"], symbol, shares)
        else:
            currentshares = int(db.execute("SELECT shares FROM stocks WHERE user_id = :user_id AND name = :name", user_id=session["user_id"], name=symbol)[0]["shares"])
            newshares = currentshares + int(shares)
            db.execute("UPDATE stocks SET shares=:newshares WHERE user_id = :user_id AND name = :name", newshares=newshares, user_id=session["user_id"], name=symbol)
        return redirect("/")


@app.route("/history")
@login_required
def history():
    data = db.execute("SELECT * FROM history WHERE user_id = :user_id", user_id=session["user_id"])
    history = []
    for row in data:
        tmp = [row["symbol"], row["shares"], row["price"], row["type"], row["time"]]
        history.append(tmp)
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == "GET":
        return render_template("quote.html")

    else:
        symbol = request.form.get("symbol").upper()
        if lookup(symbol) == None:
            return apology("Invalid stock symbol")
        value = lookup(symbol)["price"]
        name = lookup(symbol)["name"]
        return render_template("quoted.html", symbol=symbol, value=value, name=name)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    if request.method == "POST":

        #Error checking
        if request.form.get("password") != request.form.get("passwordconf"):
            return apology("Passwords do not match", 403)
        username = request.form.get("username")
        if not username:
            return apology("Username cannot be empty")
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if len(rows) != 0:
            return apology("Username already taken")

        hashpass = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash, cash) VALUES (?,?,?)", username, hashpass, 10000)

        return redirect("/")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        stocks = []
        rows = db.execute("SELECT name FROM stocks WHERE user_id = :user_id", user_id=session["user_id"])
        for row in rows:
            stocks.append(row["name"])
        return render_template("sell.html", stocks=stocks)
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        if len(db.execute("SELECT name FROM stocks WHERE name = :name", name=symbol)) == 0:
            return apology("Select a valid stock symbol")
        if shares == "" or int(shares) <= 0:
            return apology("Shares cannot be blank")

        currentshares = int(db.execute("SELECT shares FROM stocks WHERE user_id = :user_id AND name = :name", user_id = session["user_id"], name=symbol)[0]["shares"])
        if int(shares) > int(currentshares):
            return apology("You do not own enough shares")

        price = lookup(symbol)["price"]
        value = round(int(shares) * float(price), 2)
        trans = "SELL"
        time = datetime.now()
        currentshares -= int(shares)
        db.execute("INSERT INTO history (symbol, shares, price, type, user_id, time) VALUES (?,?,?,?,?,?)", symbol, shares, price, trans, session["user_id"], time)

        cash = float(db.execute("SELECT cash FROM users WHERE id = (?)", (session["user_id"]))[0]["cash"])
        cash += value
        db.execute("UPDATE users SET cash = :cash WHERE id = :user_id", cash=cash, user_id=session["user_id"])

        if currentshares == 0:
            db.execute("DELETE FROM stocks WHERE name = :name AND user_id = :user_id", name=symbol, user_id=session["user_id"])
        else:
            db.execute("UPDATE stocks SET shares = :current WHERE name = :name AND user_id = :user_id", current=currentshares, name=symbol, user_id=session["user_id"])
        return redirect("/")



def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
