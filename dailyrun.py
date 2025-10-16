import streamlit as st
import PyPDF2
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import os
import io
import pandas as pd
from datetime import datetime
from collections import defaultdict

# Default email configuration (can be overridden in sidebar)
DEFAULT_EMAIL_SERVER = 'smtp.gmail.com'
DEFAULT_EMAIL_PORT = 587
DEFAULT_SENDER_EMAIL = 'your_email@example.com'
DEFAULT_SENDER_PASSWORD = 'your_app_password'  # Use app password for Gmail

# App title
st.title("Daily Run Sheet Splitter & Emailer")

# Sidebar for configuration
st.sidebar.header("Email Configuration")
sender_email = st.sidebar.text_input("Sender Email", value=DEFAULT_SENDER_EMAIL)
sender_password = st.sidebar.text_input("Sender Password", type="password", value="")
email_server = st.sidebar.text_input("Email Server", value=DEFAULT_EMAIL_SERVER)
email_port = st.sidebar.number_input("Email Port", value=DEFAULT_EMAIL_PORT)

# File uploaders
st.subheader("Upload Files")
uploaded_pdf = st.file_uploader("Choose the Run Sheet PDF", type="pdf", key="pdf")
uploaded_mapping = st.file_uploader("Upload Driver Mapping CSV (Run, Email)", type="csv", key="csv")

# Handle mapping upload
RUN_TO_EMAIL = {}
if uploaded_mapping is not None:
    try:
        df = pd.read_csv(uploaded_mapping)
        if 'Run' in df.columns and 'Email' in df.columns:
            RUN_TO_EMAIL = dict(zip(df['Run'].astype(str), df['Email'].astype(str)))
            st.success(f"Loaded {len(RUN_TO_EMAIL)} mappings from CSV.")
            st.dataframe(df.head())  # Show preview
        else:
            st.error("CSV must have columns 'Run' and 'Email'.")
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
else:
    # Fallback to text area if no CSV uploaded
    st.sidebar.header("Fallback Mapping (if no CSV)")
    run_emails_text = st.sidebar.text_area("Run to Email Mapping (JSON-like)", 
                                           value="{}", height=100)
    try:
        RUN_TO_EMAIL = eval(run_emails_text)
    except:
        st.sidebar.error("Invalid mapping format. Use dict like {'SCD0001': 'email@example.com'}")

if uploaded_pdf is not None and len(RUN_TO_EMAIL) > 0:
    # Save uploaded PDF temporarily
    with open("temp_upload.pdf", "wb") as f:
        f.write(uploaded_pdf.getbuffer())
    PDF_PATH = "temp_upload.pdf"
    
    if st.button("Process and Send Emails"):
        with st.spinner("Processing PDF..."):
            # Extract text to identify runs
            text_per_page = []
            with open(PDF_PATH, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page_num in range(len(reader.pages)):
                    page = reader.pages[page_num]
                    text_per_page.append(page.extract_text())
            
            # Identify runs (fixed to handle repeated headers per run)
            runs = {}
            start_pages = []
            for page_num, text in enumerate(text_per_page):
                if 'Run: SCD' in text:
                    # Extract run number
                    run_lines = [line for line in text.split('\n') if 'Run: SCD' in line]
                    if run_lines:
                        run_line = run_lines[0]
                        run_num = run_line.split('Run: ')[1].split()[0].strip()
                        # Only add if not already seen (avoids duplicates from page headers)
                        if run_num not in runs:
                            # Extract operator name
                            operator_lines = [line for line in text.split('\n') if 'Operator name:' in line]
                            operator = operator_lines[0].split(':')[1].strip() if operator_lines else 'Unknown'
                            runs[run_num] = {'start_page': page_num, 'operator': operator}
                            start_pages.append((run_num, page_num))
            
            # Sort start_pages
            start_pages.sort(key=lambda x: x[1])
            st.success(f"Identified {len(runs)} runs: {list(runs.keys())}")
            
            if len(start_pages) == 0:
                st.error("No runs detected in PDF. Check the file format.")
            else:
                # Create output dir
                OUTPUT_DIR = 'split_runs'
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                
                # Split PDF into individual run files
                split_pdfs = {}
                with open(PDF_PATH, 'rb') as file:
                    reader = PyPDF2.PdfReader(file)
                    total_pages = len(reader.pages)
                    
                    for i, (run_num, start) in enumerate(start_pages):
                        if i < len(start_pages) - 1:
                            next_start = start_pages[i+1][1]
                            end = next_start
                        else:
                            end = total_pages
                        writer = PyPDF2.PdfWriter()
                        for p in range(start, end):
                            writer.add_page(reader.pages[p])
                        
                        output_path = os.path.join(OUTPUT_DIR, f'{run_num}_run.pdf')
                        with open(output_path, 'wb') as output_file:
                            writer.write(output_file)
                        split_pdfs[run_num] = output_path
                        st.write(f"Split {run_num}: pages {start+1} to {end} ({end - start} pages)")
                
                # Group runs by email (driver)
                email_to_runs = defaultdict(list)
                for run_num, run_pdf in split_pdfs.items():
                    if run_num in RUN_TO_EMAIL:
                        email = RUN_TO_EMAIL[run_num]
                        email_to_runs[email].append((run_num, run_pdf))
                
                # Merge PDFs per driver and send emails
                if sender_email and sender_password:
                    sent_count = 0
                    failed_count = 0
                    date_str = datetime.now().strftime('%Y/%m/%d')
                    
                    for email, run_list in email_to_runs.items():
                        # Merge PDFs
                        merged_writer = PyPDF2.PdfWriter()
                        run_names = []
                        for run_num, run_pdf in run_list:
                            with open(run_pdf, 'rb') as f:
                                run_reader = PyPDF2.PdfReader(f)
                                merged_writer.append_pages_from_reader(run_reader)
                            run_names.append(run_num)
                        
                        merged_path = os.path.join(OUTPUT_DIR, f'combined_{email.replace("@", "_")}.pdf')
                        with open(merged_path, 'wb') as output_file:
                            merged_writer.write(output_file)
                        
                        # Prepare email
                        subject = f"Your Combined Run Sheets ({', '.join(run_names)}) - {date_str}"
                        body = f"Dear Driver,\n\nPlease find attached your combined run sheets for {', '.join(run_names)}.\n\nBest regards,\nAdmin"
                        
                        msg = MIMEMultipart()
                        msg['From'] = sender_email
                        msg['To'] = email
                        msg['Subject'] = subject
                        
                        msg.attach(MIMEText(body, 'plain'))
                        
                        with open(merged_path, 'rb') as attachment:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(attachment.read())
                        
                        encoders.encode_base64(part)
                        part.add_header(
                            'Content-Disposition',
                            f'attachment; filename= {"Combined_Run_Sheets_" + date_str.replace("/", "_") + ".pdf"}'
                        )
                        msg.attach(part)
                        
                        try:
                            server = smtplib.SMTP(email_server, email_port)
                            server.starttls()
                            server.login(sender_email, sender_password)
                            text = msg.as_string()
                            server.sendmail(sender_email, email, text)
                            server.quit()
                            st.success(f"Combined email sent to {email} ({len(run_list)} runs)")
                            sent_count += 1
                        except Exception as e:
                            st.error(f"Failed to send email to {email} ({len(run_list)} runs): {e}")
                            failed_count += 1
                        
                        # Clean up merged file
                        os.remove(merged_path)
                    
                    # Handle runs without email
                    unassigned_runs = [r for r in split_pdfs if r not in RUN_TO_EMAIL]
                    if unassigned_runs:
                        st.warning(f"No email configured for runs: {unassigned_runs}")
                    
                    st.info(f"Processed {len(split_pdfs)} runs across {len(email_to_runs)} drivers, sent {sent_count} emails, {failed_count} failed.")
                else:
                    st.warning("Please configure sender email and password to send emails.")
                
                # Option to download individual splits or combined (but since combined are temp, show individuals)
                with st.expander("Download Individual Split Files"):
                    for run_num, pdf_path in split_pdfs.items():
                        with open(pdf_path, "rb") as f:
                            st.download_button(
                                label=f"Download {run_num}_run.pdf",
                                data=f.read(),
                                file_name=f"{run_num}_run.pdf",
                                mime="application/pdf"
                            )
        
        # Cleanup
        if os.path.exists(PDF_PATH):
            os.remove(PDF_PATH)
            if os.path.exists(OUTPUT_DIR):
                for file in os.listdir(OUTPUT_DIR):
                    os.remove(os.path.join(OUTPUT_DIR, file))
                os.rmdir(OUTPUT_DIR)
