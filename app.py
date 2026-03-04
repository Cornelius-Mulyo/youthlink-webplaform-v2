from pathlib import Path
from flask import (
    Flask, render_template, request, redirect, url_for,
    send_from_directory, abort, flash
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "change-this-secret"  # use env var in production

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Editable in-browser text files
EDITABLE_EXTS = {".txt", ".md", ".py", ".json", ".csv", ".html", ".css", ".js", ".yml", ".yaml"}

# Preview types
PREVIEW_TEXT_EXTS = EDITABLE_EXTS
PREVIEW_INLINE_EXTS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
    ".mp4", ".webm", ".mp3", ".wav"
}

# restrict uploads (None = allow any)
ALLOWED_UPLOAD_EXTS = None  # e.g. {".pdf", ".png", ".jpg", ".txt"}

# In-memory opportunity store (restarts clear this)
opportunities = []


def safe_file_path(filename: str) -> Path:
    """Sanitize filename and prevent path traversal."""
    name = secure_filename(filename)
    if not name:
        abort(400, "Invalid filename.")
    fp = (UPLOAD_DIR / name).resolve()
    if UPLOAD_DIR.resolve() not in fp.parents and fp != UPLOAD_DIR.resolve():
        abort(400, "Invalid file path.")
    return fp


def unique_filename(original_name: str) -> str:
    """Auto-rename to avoid overwriting: file(1).ext, file(2).ext, ..."""
    original_name = secure_filename(original_name)
    if not original_name:
        abort(400, "Invalid filename.")

    p = Path(original_name)
    stem, ext = p.stem, p.suffix
    candidate = original_name
    i = 1
    while (UPLOAD_DIR / candidate).exists():
        candidate = f"{stem}({i}){ext}"
        i += 1
    return candidate


@app.get("/")
def home():
    # Search + filter inputs
    q_raw = request.args.get("q", "")
    q = q_raw.strip().lower()
    selected_category = request.args.get("category", "").strip()

    # Categories for dropdown
    categories = sorted({o["category"] for o in opportunities if o.get("category")})

    # Apply search + filter
    filtered = opportunities
    if q:
        filtered = [
            o for o in filtered
            if q in o["title"].lower()
            or q in o["description"].lower()
            or q in o["category"].lower()
            or (o.get("filename") and q in o["filename"].lower())
        ]

    if selected_category:
        filtered = [o for o in filtered if o["category"] == selected_category]

    # File list for file manager section
    files = sorted([p.name for p in UPLOAD_DIR.iterdir() if p.is_file()])

    return render_template(
        "home.html",
        opportunities=filtered,
        q=q_raw,
        categories=categories,
        selected_category=selected_category,
        files=files,
        editable_exts=sorted(EDITABLE_EXTS),
    )


@app.route("/add", methods=["GET", "POST"])
def add_opportunity():
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        category = request.form["category"].strip()

        file = request.files.get("file")
        filename = None

        if file and file.filename:
            ext = Path(file.filename).suffix.lower()
            if ALLOWED_UPLOAD_EXTS is not None and ext not in ALLOWED_UPLOAD_EXTS:
                abort(400, f"Upload blocked. Allowed extensions: {sorted(ALLOWED_UPLOAD_EXTS)}")

            filename = unique_filename(file.filename)
            file.save(safe_file_path(filename))

        opportunities.append({
            "title": title,
            "description": description,
            "category": category,
            "filename": filename,
        })

        flash("Opportunity added!")
        return redirect(url_for("home"))

    return render_template("add.html")


@app.post("/upload")
def upload():
    """Upload a file from the home page file manager."""
    if "file" not in request.files:
        abort(400, "No file field in request.")

    f = request.files["file"]
    if not f or not f.filename:
        abort(400, "No selected file.")

    ext = Path(f.filename).suffix.lower()
    if ALLOWED_UPLOAD_EXTS is not None and ext not in ALLOWED_UPLOAD_EXTS:
        abort(400, f"Upload blocked. Allowed extensions: {sorted(ALLOWED_UPLOAD_EXTS)}")

    filename = unique_filename(f.filename)
    f.save(safe_file_path(filename))

    flash(f"Uploaded: {filename}")
    return redirect(url_for("home"))


@app.get("/download/<path:filename>")
def download(filename):
    fp = safe_file_path(filename)
    if not fp.exists():
        abort(404, "File not found.")
    return send_from_directory(UPLOAD_DIR, fp.name, as_attachment=True)


# -------- VIEW FEATURE --------

@app.get("/raw/<path:filename>")
def raw_file(filename):
    """Serve file inline for preview."""
    fp = safe_file_path(filename)
    if not fp.exists():
        abort(404, "File not found.")
    return send_from_directory(UPLOAD_DIR, fp.name, as_attachment=False)


@app.get("/view/<path:filename>")
def view_file(filename):
    fp = safe_file_path(filename)
    if not fp.exists():
        abort(404, "File not found.")

    ext = fp.suffix.lower()

    if ext in PREVIEW_TEXT_EXTS:
        try:
            content = fp.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            abort(400, "File is not UTF-8 text; cannot preview.")
        return render_template("view.html", filename=fp.name, kind="text", content=content)

    if ext in PREVIEW_INLINE_EXTS:
        return render_template("view.html", filename=fp.name, kind="inline", ext=ext)

    abort(400, "Preview not supported for this file type.")


# -------- DELETE FEATURE --------

@app.post("/delete/<path:filename>")
def delete_file(filename):
    fp = safe_file_path(filename)
    if not fp.exists():
        abort(404, "File not found.")

    fp.unlink()

    # Detach from opportunities (keep opportunities)
    for o in opportunities:
        if o.get("filename") == fp.name:
            o["filename"] = None

    flash(f"Deleted: {fp.name}")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)