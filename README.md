# 🪪 Enterprise E-Card Extraction & Management Portal

An AI-powered, highly secure web application designed to process, split, and extract structured data from bulk Employee Health Insurance PDFs. 

Built with **Streamlit**, **PaddleOCR**, **OpenCV**, and **PostgreSQL (Supabase)**, this system automates the tedious process of categorizing hundreds of e-cards into a searchable, relational database.

---

## 🌟 Key Features

*   **Computer Vision Cropping:** Uses OpenCV to safely slice e-cards by detecting physical card boundaries (white-space gaps), ensuring text is *never* cut in half.
*   **Dual-Engine AI Extraction:** Uses `PyMuPDF` for lightning-fast native text extraction, automatically falling back to **PaddleOCR (AI)** for scanned or flattened image-based pages.
*   **Pydantic Data Validation:** Parses and validates extracted text into structured family details (Name, Age, Relationship, Policy No, Card No).
*   **PostgreSQL Database:** Stores generated split PDFs natively as `BYTEA` blobs and stores family metadata relationally.
*   **Zero-Disk Architecture:** Creates bulk ZIP files entirely in the server's RAM using `io.BytesIO`, completely preventing disk bloat.
*   **Immune to Browser Blocks:** Uses `PyMuPDF` to render PDF previews as crisp PNG images, bypassing strict browser Content Security Policies (CSP) that block `iframe` PDFs.

---

## 🛠️ Technology Stack

*   **Frontend/UI:** Streamlit
*   **Computer Vision:** OpenCV (`opencv-python-headless`)
*   **PDF Parsing/Rendering:** PyMuPDF (`fitz`)
*   **Optical Character Recognition:** PaddlePaddle & PaddleOCR
*   **Data Structuring:** Pydantic & Pandas
*   **Database:** PostgreSQL (Supabase) & `psycopg2-binary`
*   **Security:** `werkzeug.security` (Password Hashing)

---

## 📂 Repository Structure

```text
├── app.py                 # Main Streamlit application & UI routing
├── parser_worker.py       # Pydantic data validation & Regex extraction logic
├── requirements.txt       # Python dependencies
├── packages.txt           # Linux system drivers (for Cloud Deployment)
├── .gitignore             # Security rules to prevent credential leaks
└── README.md              # Project documentation




## 💻 Local Setup & Installation

**1. Clone the repository**
```bash
git clone https://github.com/YOUR_USERNAME/CapitUp_E-card-dashboard-.git
cd CapitUp_E-card-dashboard-
```

**2. Install Dependencies**
```bash
pip install -r requirements.txt
```

**3. Setup Database Secrets**
Create a hidden folder named `.streamlit` in the root directory, and inside it, create a file named `secrets.toml`. Add your Supabase IPv4 connection pooling details:
```toml
[postgres]
host = "aws-0-ap-south-1.pooler.supabase.com"  # Must use the IPv4 pooler
port = "6543"                                  # Pooler port (Transaction mode)
user = "postgres.your_project_id"
password = "your_database_password"
dbname = "postgres"
```

**4. Run the Application**
```bash
streamlit run app.py
```
*(Note: The `init_db()` function will automatically generate all necessary PostgreSQL tables on the first run. No manual SQL required!)*

---

## ☁️ Cloud Deployment (Streamlit Community Cloud)

When deploying to a Linux-based cloud environment (like Streamlit Cloud), the system requires specific C++ drivers for OpenCV to function natively without crashing.

1. Ensure your repository includes a `packages.txt` file containing exactly:
   ```text
   libgl1
   libglib2.0-0t64
   ```
2. Set your **Python Version to 3.11** (PaddleOCR does not currently support Python 3.12 or 3.13).
3. Set your Database credentials in the Streamlit Cloud **Advanced Settings -> Secrets** menu before hitting Deploy.

---

## 📘 Standard Operating Procedure (For HR & Ops Teams)

### 1. Uploading & Processing Bulk E-Cards (Tab 1)
Use this tab when you receive a large, merged PDF containing hundreds of e-cards.
* Drag and drop the master PDF into the upload box.
* Click **🚀 Process & Save to Database**.
* **Wait for processing:** The AI will scan, crop, and read every card.
* **Download Bulk ZIP:** Once complete, click the **📥 Download All Split PDFs (ZIP)** button to download a perfectly organized folder of individual PDFs to your computer.

### 2. Searching for an Employee (Tab 2)
Use this tab when an employee requests a copy of their specific E-Card.
* Enter the exact **Employee ID** into the search bar (e.g., `1118`).
* The system will display the **Family Enrolled Table** (spouse, children, specific Card Numbers) and a **Live Preview** of the physical E-Card.
* Click the red **📥 Download** button to save the E-Card locally and email it to the employee.

### 3. Directory & Analytics (Tab 3)
Use this tab to audit the database or find an employee whose ID you forgot.
* **Global Search:** Type a name (e.g., "Mahesh") into the search bar to instantly find their Employee ID.
* **Filtering:** Use the dropdowns to filter the entire database by **Relationship** (e.g., show only "Spouses") or by **Policy Type**.
* Click on any column header to sort the data alphabetically or numerically.

---

## ⚠️ Troubleshooting

*   **Missing Cards:** If an e-card was too blurry or corrupted for the AI to read, it will be saved in the system under the ID `UNIDENTIFIED`. You can search for `UNIDENTIFIED` in Tab 2 to manually review these cards.
*   **Deployment Crash (`libGL.so.1` or `libgthread`):** Ensure you are using `opencv-python-headless` in `requirements.txt` and have the `packages.txt` file properly pushed to GitHub containing `libgl1` and `libglib2.0-0t64`.



