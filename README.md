# Zahir Shop — Digital Attendance System

Biometric attendance system using a **Suprema BioMini Slim 2** fingerprint scanner,
**Supabase** PostgreSQL cloud database, and a **Streamlit** web admin dashboard.

---

## Project Structure

```
├── database/
│   └── schema.sql          ← Run once in Supabase SQL Editor
├── local_client/           ← Python desktop app (runs on the shop laptop)
│   ├── main.py             ← Entry point (CustomTkinter UI)
│   ├── scanner.py          ← ctypes bridge for BS_SDK_V2.dll
│   ├── db.py               ← Cloud DB queries (psycopg2)
│   ├── audio.py            ← winsound feedback
│   ├── config.py           ← All constants & env-loaded secrets
│   ├── BS_SDK_V2.dll       ← Copy from your SDK folder (x64)
│   ├── libcrypto-1_1-x64.dll
│   ├── libssl-1_1-x64.dll
│   ├── .env                ← Your DATABASE_URL (from .env.example)
│   └── requirements.txt
└── web_dashboard/          ← Streamlit admin dashboard (GitHub → Streamlit Cloud)
    ├── app.py              ← Entry point
    ├── db.py               ← Shared DB connection
    ├── tabs/
    │   ├── analytics.py    ← Pie chart + line chart + KPI cards
    │   └── crud.py         ← Full CRUD portal
    ├── .streamlit/
    │   └── config.toml     ← Dark theme
    └── requirements.txt
```

---

## Step 1 — Set Up Supabase Database

1. Create a free project at [supabase.com](https://supabase.com)
2. Open **SQL Editor** → paste the entire content of `database/schema.sql` → **Run**
3. Copy your connection string:
   - Go to **Project Settings → Database → Connection string → URI**
   - It looks like: `postgresql://postgres:<password>@<host>:5432/postgres`

---

## Step 2 — Configure the Local Client

```powershell
cd "d:\Projects casual\Zahir shop attendence\local_client"

# Copy the example env file and fill in your Supabase URL
copy .env.example .env
# Edit .env → set DATABASE_URL=postgresql://postgres:...

# Install dependencies
pip install -r requirements.txt
```

Ensure these three files are in `local_client/`:
- `BS_SDK_V2.dll`
- `libcrypto-1_1-x64.dll`
- `libssl-1_1-x64.dll`

Run the desktop app:
```powershell
python main.py
```

### Enrollment Flow
1. Open **📋 Enrollment** tab
2. Fill in Name, CNIC, Phone, Address
3. Click **Enroll Finger** → place thumb on scanner twice
4. Employee is saved to Supabase with `enrollment_status = 'enrolled'`

### Attendance Flow
1. Open **✅ Attendance** tab
2. Click **▶ Start Attendance Loop**
3. Place any enrolled employee's thumb → system identifies, plays chime, logs status

**Status Rules (Shift starts 07:30 AM):**
| Minutes late | Status   |
|:---:|:---:|
| 0 – 15       | Present  |
| 16 – 60      | Late     |
| 61 – 240     | Half Day |

---

## Step 3 — Deploy Web Dashboard

```powershell
cd "d:\Projects casual\Zahir shop attendence\web_dashboard"
pip install -r requirements.txt

# Test locally
streamlit run app.py
```

**Deploy to Streamlit Community Cloud (free):**
1. Push the entire `web_dashboard/` folder to a GitHub repo
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo, branch, and set **Main file path** to `app.py`
4. In **Advanced settings → Secrets**, add:
   ```toml
   DATABASE_URL = "postgresql://postgres:<password>@<host>:5432/postgres?sslmode=require"
   ```
5. Click **Deploy** — your dashboard is live at a public URL

---

## ctypes DLL Integration — How It Works

```
Python int 42   →  c_uint32(42)          via .argtypes = [c_uint32]
Python output   ←  byref(c_uint32())     SDK writes back through the pointer
C struct        ←→ ctypes.Structure      _fields_ mirrors C header field-by-field
Byte buffer     ←→ create_string_buffer  For raw uint8_t* image data
Template stored    base64.b64encode(bytes(fp))  BS2Fingerprint → str for PostgreSQL
Template loaded    BS2Fingerprint.from_buffer_copy(b64decode(s))
```

---

## Security Notes

- `.env` and `.streamlit/secrets.toml` are in `.gitignore` — never commit them
- All SQL queries use parameterized statements (`%s`) — no SQL injection risk
- `sslmode=require` is enforced on all DB connections
