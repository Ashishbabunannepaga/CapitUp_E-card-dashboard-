import os
import warnings

# --- SUPPRESS AI & C++ NOISE ---
os.environ["GLOG_minloglevel"] = "3"   
os.environ["KMP_WARNINGS"] = "0"       
warnings.filterwarnings("ignore")      

import streamlit as st
import fitz  # PyMuPDF
import cv2
import numpy as np
import pandas as pd
import logging
import psycopg2
import base64
import zipfile
from io import BytesIO
from psycopg2.extras import RealDictCursor
from paddleocr import PaddleOCR
from werkzeug.security import generate_password_hash, check_password_hash

# Import our robust Pydantic worker
from parser_worker import extract_metadata_from_text, CardMetadata

# --- STREAMLIT UI CONFIGURATION ---
st.set_page_config(page_title="Enterprise E-Card Portal", page_icon="🪪", layout="wide")

# --- DATABASE SECRETS LOAD ---
try:
    DB_CONFIG = dict(st.secrets["postgres"])
except KeyError:
    st.error("🚨 CRITICAL ERROR: Could not find [postgres] in Streamlit Secrets!")
    st.stop()

# --- CACHE THE AI ENGINE ---
@st.cache_resource(show_spinner="Loading AI Vision Engine... (First load takes a few seconds)")
def load_ocr_engine():
    logging.getLogger('ppocr').setLevel(logging.ERROR)
    return PaddleOCR(use_textline_orientation=True, lang='en')

# --- DATABASE FUNCTIONS (POSTGRESQL / SUPABASE) ---
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

def init_db():
    """Automatically ensures all tables exist in Supabase on startup."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY, username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
                
            CREATE TABLE IF NOT EXISTS ecards (
                id SERIAL PRIMARY KEY, emp_id VARCHAR(50) NOT NULL,
                pdf_data BYTEA NOT NULL, uploaded_by VARCHAR(50) NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
                
            CREATE TABLE IF NOT EXISTS card_members (
                id SERIAL PRIMARY KEY, emp_id VARCHAR(50) NOT NULL,
                name VARCHAR(255), policy_no VARCHAR(100), policy_type VARCHAR(100),
                card_no VARCHAR(100), relationship VARCHAR(50), age INT, valid_up_to VARCHAR(50));
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Failed to initialize Database: {e}")

def authenticate_user(username, password):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s;", (username,))
    user = cursor.fetchone()
    conn.close()
    return user and check_password_hash(user['password_hash'], password)

def create_user(username, password):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password_hash) VALUES (%s, %s);", 
                       (username, generate_password_hash(password)))
        conn.commit()
        conn.close()
        return True
    except psycopg2.IntegrityError:
        return False

def save_card_to_db(emp_id, pdf_bytes, username, family_members):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Save the actual PDF
    cursor.execute("DELETE FROM ecards WHERE emp_id = %s;", (emp_id,))
    cursor.execute("INSERT INTO ecards (emp_id, pdf_data, uploaded_by) VALUES (%s, %s, %s);",
                   (emp_id, psycopg2.Binary(pdf_bytes), username))
                   
    # 2. Save the extracted metadata for family members
    cursor.execute("DELETE FROM card_members WHERE emp_id = %s;", (emp_id,))
    for member in family_members:
        cursor.execute("""
            INSERT INTO card_members 
            (emp_id, name, policy_no, policy_type, card_no, relationship, age, valid_up_to) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (emp_id, member.name, member.policy_no, member.policy_type, 
              member.card_no, member.relationship, member.age, member.valid_up_to))
              
    conn.commit()
    conn.close()

def get_card_from_db(emp_id):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT pdf_data, uploaded_by, upload_date FROM ecards WHERE emp_id = %s;", (emp_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_members_from_db(emp_id=None):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    if emp_id:
        cursor.execute("SELECT * FROM card_members WHERE emp_id = %s ORDER BY relationship DESC;", (emp_id,))
    else:
        cursor.execute("SELECT * FROM card_members ORDER BY emp_id;")
    results = cursor.fetchall()
    conn.close()
    return results

# --- EXTRACTION LOGIC ---
def detect_card_boundaries(page):
    try:
        pix = page.get_pixmap(dpi=150)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)
        _, thresh = cv2.threshold(blurred, 240, 255, cv2.THRESH_BINARY_INV)
        
        row_sums = np.sum(thresh, axis=1)
        gaps = np.where(row_sums < (thresh.shape[1] * 0.05))[0] 

        height = pix.h
        split_y = [0]
        for i in range(1, len(gaps)):
            if gaps[i] - gaps[i-1] > 20: 
                split_y.append(gaps[i])
        split_y.append(height)

        rects = []
        for i in range(len(split_y)-1):
            y1, y2 = split_y[i], split_y[i+1]
            if y2 - y1 > 150:  
                rects.append(fitz.Rect(0, y1 * (page.rect.height / height), page.rect.width, y2 * (page.rect.height / height)))
        if not rects: raise ValueError()
        return rects
    except:
        h3 = page.rect.height / 3
        return [fitz.Rect(0, 0, page.rect.width, h3), fitz.Rect(0, h3, page.rect.width, h3*2), fitz.Rect(0, h3*2, page.rect.width, page.rect.height)]

# --- INITIALIZE DATABASE ON STARTUP ---
init_db()

# --- LOGIN & REGISTRATION SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔐 E-Card System Portal")
        st.markdown("Please log in or register to access the database.")
        
        tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register New User"])
        
        with tab_login:
            with st.form("login_form"):
                st.subheader("Login to your account")
                user_input = st.text_input("Username")
                pass_input = st.text_input("Password", type="password")
                if st.form_submit_button("Login", width="stretch", type="primary"):
                    if authenticate_user(user_input, pass_input):
                        st.session_state.logged_in = True
                        st.session_state.username = user_input
                        st.rerun()
                    else:
                        st.error("❌ Invalid Credentials. Please try again.")
                        
        with tab_register:
            with st.form("register_form"):
                st.subheader("Create a new account")
                new_user = st.text_input("Choose a Username")
                new_pass = st.text_input("Choose a Password", type="password")
                confirm_pass = st.text_input("Confirm Password", type="password")
                if st.form_submit_button("Register Account", width="stretch", type="primary"):
                    if not new_user or not new_pass:
                        st.warning("⚠️ Please fill in all fields.")
                    elif new_pass != confirm_pass:
                        st.error("❌ Passwords do not match!")
                    elif len(new_pass) < 6:
                        st.error("⚠️ Password must be at least 6 characters long.")
                    elif create_user(new_user, new_pass):
                        st.success("✅ Account created successfully! Please switch to the Login tab.")
                    else:
                        st.error("⚠️ Username already exists.")
    st.stop() 

# --- MAIN APPLICATION PORTAL ---
st.sidebar.title(f"👤 Welcome, {st.session_state.username}")
if st.sidebar.button("Logout", type="primary", width="stretch"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

st.title("🪪 Enterprise E-Card Database Portal")
main_tab1, main_tab2, main_tab3 = st.tabs(["📤 Upload & Process", "🔍 Search E-Card", "📊 Candidate Directory"])

ocr_engine = load_ocr_engine()

# --- TAB 1: UPLOAD AND SPLIT ---
with main_tab1:
    st.markdown("Upload a master PDF. Cards will be split, parsed, pushed to Supabase, and grouped into a ZIP file.")
    
    if 'zip_data' not in st.session_state:
        st.session_state.zip_data = None
    if 'processed_count' not in st.session_state:
        st.session_state.processed_count = 0

    pdf_file = st.file_uploader("Upload Master E-Card PDF", type=["pdf"])

    if pdf_file and st.button("🚀 Process & Save to Database", type="primary", width="stretch"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        doc = fitz.open(stream=pdf_file.getbuffer(), filetype="pdf")
        total_pages = len(doc)
        employee_data = {}       
        employee_metadata = {}   
        
        for page_num in range(total_pages):
            status_text.text(f"Scanning Page {page_num + 1} of {total_pages}...")
            progress_bar.progress((page_num) / total_pages)
            page = doc[page_num]
            
            for rect in detect_card_boundaries(page):
                raw_text = page.get_text("text", clip=rect)
                
                if "Emp" not in raw_text:
                    try:
                        pix = page.get_pixmap(clip=rect, dpi=300)
                        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                        res = ocr_engine.ocr(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), cls=False)
                        if res and res[0]:
                            raw_text += " \n " + " ".join([line[1][0] for line in res[0]])
                    except: pass
                
                parsed_data = extract_metadata_from_text(raw_text)
                emp_id = parsed_data.emp_id
                
                if emp_id:
                    if emp_id not in employee_data: 
                        employee_data[emp_id] = []
                        employee_metadata[emp_id] = []
                    employee_data[emp_id].append((page_num, rect))
                    employee_metadata[emp_id].append(parsed_data)

        status_text.text("Saving structured data to Supabase and building ZIP file...")
        
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for emp_id, locations in employee_data.items():
                out_pdf = fitz.open()
                for (page_num, rect) in locations:
                    out_pdf.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    out_pdf[-1].set_cropbox(rect)
                
                pdf_bytes = out_pdf.tobytes()
                save_card_to_db(emp_id, pdf_bytes, st.session_state.username, employee_metadata[emp_id])
                
                safe_filename = "".join([c for c in emp_id if c.isalnum()]) or "UNIDENTIFIED"
                zip_file.writestr(f"{safe_filename}_ECard.pdf", pdf_bytes)
                out_pdf.close()
                
        st.session_state.zip_data = zip_buffer.getvalue()
        st.session_state.processed_count = len(employee_data)
            
        progress_bar.progress(1.0)
        status_text.success(f"✅ Extracted and organized data for {len(employee_data)} Employees!")

    if st.session_state.zip_data:
        st.divider()
        st.success(f"🎉 Ready to download! ({st.session_state.processed_count} categorized PDFs packaged)")
        st.download_button(
            label="📥 Download All Split PDFs (ZIP)",
            data=st.session_state.zip_data,
            file_name="Categorized_ECards.zip",
            mime="application/zip",
            type="primary",
            width="stretch"
        )

# --- TAB 2: SEARCH & RETRIEVE ---
with main_tab2:
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_id = st.text_input("Enter Employee ID:", label_visibility="collapsed", placeholder="e.g. 1118")
    with col_btn:
        search_clicked = st.button("🔍 Search Database", width="stretch")
    
    if search_clicked and search_id:
        result = get_card_from_db(search_id.upper())
        members = get_members_from_db(search_id.upper())
        
        if result:
            st.success(f"✅ Card uploaded by: {result['uploaded_by']} on {result['upload_date'].strftime('%Y-%m-%d')}")
            
            if members:
                st.subheader(f"👨‍👩‍👧 Family Enrolled (Total: {len(members)})")
                df_members = pd.DataFrame(members).drop(columns=['id', 'emp_id'], errors='ignore')
                st.dataframe(df_members, hide_index=True, width="stretch")
            
            pdf_bytes = bytes(result['pdf_data'])
            st.download_button(label=f"📥 Download {search_id.upper()}'s E-Card", data=pdf_bytes, file_name=f"{search_id.upper()}.pdf", mime="application/pdf", type="primary")

            st.divider()
            st.subheader("👁️ Live E-Card Preview")
            
            # Open the PDF securely from memory
            preview_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            # Render each page as a crisp, high-definition image
            for page_num in range(len(preview_doc)):
                page = preview_doc[page_num]
                pix = page.get_pixmap(dpi=150)  # 150 DPI for crystal clear text
                img_bytes = pix.tobytes("png")
                
                # Display the image flawlessly using Streamlit's native image viewer
                st.image(img_bytes, caption=f"Card Preview (Page {page_num + 1})", use_column_width=True)
                
            preview_doc.close()

# --- TAB 3: DIRECTORY & FILTERS ---
with main_tab3:
    st.markdown("### 🗂️ Global Candidate Directory")
    
    all_members = get_members_from_db()
    
    if not all_members:
        st.info("No data available yet. Please upload and process a PDF in Tab 1.")
    else:
        df_all = pd.DataFrame(all_members).drop(columns=['id'], errors='ignore')
        
        col_f1, col_f2, col_f3 = st.columns(3)
        search_term = col_f1.text_input("🔍 Search Name or Emp ID:")
        relationships = df_all['relationship'].dropna().unique().tolist()
        rel_filter = col_f2.multiselect("👥 Filter by Relationship:", options=relationships, default=[])
        policies = df_all['policy_type'].dropna().unique().tolist()
        pol_filter = col_f3.multiselect("📄 Filter by Policy Type:", options=policies, default=[])
        
        filtered_df = df_all.copy()
        if search_term:
            filtered_df = filtered_df[filtered_df['name'].str.contains(search_term, case=False, na=False) | filtered_df['emp_id'].str.contains(search_term, case=False, na=False)]
        if rel_filter: filtered_df = filtered_df[filtered_df['relationship'].isin(rel_filter)]
        if pol_filter: filtered_df = filtered_df[filtered_df['policy_type'].isin(pol_filter)]
            
        st.metric(label="Total Profiles Found", value=len(filtered_df))
        st.dataframe(
            filtered_df, hide_index=True, width="stretch",
            column_config={
                "emp_id": st.column_config.TextColumn("Employee ID"),
                "name": st.column_config.TextColumn("Full Name"),
                "age": st.column_config.NumberColumn("Age"),
                "policy_no": st.column_config.TextColumn("Policy Number"),
                "card_no": st.column_config.TextColumn("Card Number")
            }
        )
