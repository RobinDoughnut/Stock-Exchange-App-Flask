import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():

    user_id = session["user_id"]
    # Users stock amount
    stocks = db.execute(
        "SELECT symbol, price, SUM(shares) as total_shares FROM transactions WHERE user_id = ? GROUP BY symbol", user_id)

    # Users cash amount
    cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]

    # initialize
    total = cash

    # iterate stock and add price
    for stock in stocks:
        total += stock["price"] * stock["total_shares"]

    return render_template("index.html", stocks=stocks, cash=cash, total=total, usd=usd)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("Please provide stock symbol")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Must provide valid share amount")

        quote = lookup(symbol)
        if quote is None:
            return apology("symbol not found")

        price = quote["price"]
        total_cost = int(shares) * price
        cash = db.execute("SELECT cash FROM users WHERE id = :user_id", user_id=session["user_id"])[0]["cash"]

        if cash < total_cost:
            return apology("Not enough cash to buy stocks")

        # Update users table
        db.execute("UPDATE users SET cash = cash - :total_cost WHERE id = :user_id",
                   total_cost=total_cost, user_id=session["user_id"])

        # Add purchase history table
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, timestamp) VALUES (:user_id, :symbol, :shares, :price, CURRENT_TIMESTAMP)",
                   user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

        flash(f"Bought {shares} shares of {symbol} for {usd(total_cost)}!")
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # Query database for user's transactions, ordered by most recent
    transactions = db.execute(
        "SELECT * FROM transactions WHERE user_id= :user_id ORDER BY timestamp DESC", user_id=session["user_id"])

    # render transactions properly
    return render_template("history.html", transactions=transactions)


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
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
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
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        quote = lookup(symbol)
        if not quote:
            return apology("invalid symbol", 400)
        return render_template("quote.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirm password was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # Ensure password and confirm password matches
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("confirm password does not match", 400)

        # Check database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Confirm if username exists in users
        if len(rows) != 0:
            return apology("Username already exists", 400)

        # Insert user in table
        db.execute("INSERT INTO users(username, hash) VALUES (?, ?)", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Get latest row with new user
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user logged in
        session["user_id"] = rows[0]["id"]

        return redirect("/")

    # By get method
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    stocks = db.execute(
        "SELECT symbol, SUM(shares) as total_shares FROM transactions WHERE user_id = :user_id GROUP BY symbol HAVING total_shares > 0", user_id=session["user_id"])

    # when form is submitted
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        shares = request.form.get("shares")
        if not symbol:
            return apology("Symbol not valid")
        elif not shares or not shares.isdigit() or int(shares) <= 0:
            return apology("Provide valid amount of shares in integer")
        else:
            shares = int(shares)

        for stock in stocks:
            if stock["symbol"] == symbol:
                if stock["total_shares"] < shares:
                    return apology("not enough shares")
                else:
                    # Find quote amount
                    quote = lookup(symbol)
                    if quote is None:
                        return apology("symbol not found")
                    price = quote["price"]
                    total_sale = price * shares

                 # Update users table
                    db.execute("UPDATE users SET cash = cash + :total_sale WHERE id = :user_id",
                               total_sale=total_sale, user_id=session["user_id"])

                 # Add the sale to history table
                    db.execute("INSERT INTO transactions (user_id, symbol, shares, price, timestamp) VALUES (:user_id, :symbol, :shares, :price, CURRENT_TIMESTAMP)",
                               user_id=session["user_id"], symbol=symbol, shares=shares, price=price)

                    if shares == 1:
                        flash(f"Sold {shares} share of {symbol} for {usd(total_sale)}!")
                    else:
                        flash(f"Sold {shares} shares of {symbol} for {usd(total_sale)}!")

                    return redirect("/")

        return apology("Symbol not found")

    # When users visit
    else:
        return render_template("sell.html", stocks=stocks)


@app.route("/password", methods=["GET", "POST"])
def password():

    if request.method == "POST":
        # get session user_id
        user_id = session["user_id"]
        # give old password
        old_password = request.form.get('old-password')
        new_password = request.form.get('new-password')
        confirm_password = request.form.get('confirm-new-password')

        # fetch old password from user
        db_pass = db.execute("SELECT hash FROM users WHERE id = ?", session["user_id"])

        # check old pass
        if not check_password_hash(db_pass[0]["hash"], old_password):
            return apology("Old password is incorrect.", 400)

        elif new_password != confirm_password:
            return apology("New passwords do not match.", 400)
        else:
            # Update new password into table
            db.execute("UPDATE users SET hash = ? WHERE id = ?", generate_password_hash(request.form.get("new-password")), user_id)
            flash("Password changed successfully.")
            return redirect("/")
    else:
        return render_template("password.html")
