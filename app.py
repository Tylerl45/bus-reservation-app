import os
import random
import string

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

# ------------------
# Flask + Database setup
# ------------------
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, "reservations.db")

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "change_this_secret_key"  # change if you want

db = SQLAlchemy(app)


# ------------------
# Models (match schema.sql)
# ------------------
class Reservation(db.Model):
    __tablename__ = "reservations"
    id = db.Column(db.Integer, primary_key=True)
    passengerName = db.Column(db.String, nullable=False)
    seatRow = db.Column(db.Integer, nullable=False)
    seatColumn = db.Column(db.Integer, nullable=False)
    eTicketNumber = db.Column(db.String, nullable=False, unique=True)
    created = db.Column(
        db.DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class Admin(db.Model):
    __tablename__ = "admins"
    username = db.Column(db.String, primary_key=True)
    password = db.Column(db.String, nullable=False)


# ------------------
# Helpers
# ------------------
def get_cost_matrix():
    """
    Returns 12 x 4 matrix of prices.
    Each row has [100, 75, 50, 100].
    """
    return [[100, 75, 50, 100] for _ in range(12)]


def generate_reservation_code(length: int = 8) -> str:
    """Random reservation code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def build_seating_chart(reservations):
    """
    Build simple text-based seating chart using O/X.
    O = open seat, X = reserved seat.
    """
    seats = [["O" for _ in range(4)] for _ in range(12)]
    for r in reservations:
        row_idx = r.seatRow - 1
        col_idx = r.seatColumn - 1
        if 0 <= row_idx < 12 and 0 <= col_idx < 4:
            seats[row_idx][col_idx] = "X"

    lines = []
    for i, row in enumerate(seats, start=1):
        lines.append(f"Row {i:2}: " + " ".join(row))
    return "\n".join(lines)


def calculate_price_for_seat(row, col):
    matrix = get_cost_matrix()
    return matrix[row - 1][col - 1]


def calculate_total_sales(reservations):
    """Compute total based on cost matrix and each reserved seat."""
    total = 0
    for r in reservations:
        total += calculate_price_for_seat(r.seatRow, r.seatColumn)
    return total


# ------------------
# Routes
# ------------------
@app.route("/")
def index():
    """Main menu page."""
    return render_template("index.html")


@app.route("/reserve", methods=["GET", "POST"])
def reserve_seat():
    """
    Student reservation flow.
    """
    error = None
    success = None

    reservations = Reservation.query.all()
    seating = build_seating_chart(reservations)

    if request.method == "POST":
        first_name = request.form["first_name"].strip()
        last_name = request.form["last_name"].strip()
        passenger_name = f"{first_name} {last_name}"

        try:
            seat_row = int(request.form["seat_row"])
            seat_column = int(request.form["seat_column"])
        except (KeyError, ValueError):
            error = "Seat row and column must be numbers."
            return render_template(
                "reserve.html", error=error, success=success, seating=seating
            )

        # validate seat range
        if not (1 <= seat_row <= 12 and 1 <= seat_column <= 4):
            error = "Invalid seat selection. Row must be 1–12 and column 1–4."
        else:
            # check if seat is already taken
            existing = Reservation.query.filter_by(
                seatRow=seat_row, seatColumn=seat_column
            ).first()
            if existing:
                error = "That seat is already reserved. Please pick another."
            else:
                code = generate_reservation_code()
                new_res = Reservation(
                    passengerName=passenger_name,
                    seatRow=seat_row,
                    seatColumn=seat_column,
                    eTicketNumber=code,
                )
                db.session.add(new_res)
                db.session.commit()

                reservations = Reservation.query.all()
                seating = build_seating_chart(reservations)

                price = calculate_price_for_seat(seat_row, seat_column)
                success = (
                    f"Reservation confirmed for {passenger_name}! "
                    f"Code: {code}, Seat: Row {seat_row}, Column {seat_column}, "
                    f"Price: ${price:.2f}"
                )

    return render_template(
        "reserve.html", error=error, success=success, seating=seating
    )


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """
    Admin login flow.
    """
    error = None
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()

        admin = Admin.query.filter_by(username=username, password=password).first()
        if admin:
            session["admin_username"] = admin.username
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid username or password."

    return render_template("login.html", error=error)


@app.route("/admin")
def admin_dashboard():
    """
    Admin dashboard: seating chart, reservations, total sales.
    """
    if "admin_username" not in session:
        return redirect(url_for("admin_login"))

    reservations = Reservation.query.all()
    seating = build_seating_chart(reservations)
    total_sales = calculate_total_sales(reservations)

    # attach each reservation with its calculated price
    reservations_with_price = []
    for r in reservations:
        price = calculate_price_for_seat(r.seatRow, r.seatColumn)
        reservations_with_price.append((r, price))

    return render_template(
        "admin.html",
        seating=seating,
        total_sales=total_sales,
        reservations_with_price=reservations_with_price,
    )


@app.route("/admin/delete/<int:res_id>", methods=["POST"])
def delete_reservation(res_id):
    """Delete a reservation."""
    if "admin_username" not in session:
        return redirect(url_for("admin_login"))

    res = Reservation.query.get(res_id)
    if res:
        db.session.delete(res)
        db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    """Log out admin."""
    session.pop("admin_username", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    # host=0.0.0.0 for Docker use too
    app.run(debug=True, host="0.0.0.0")
