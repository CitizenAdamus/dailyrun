# dailyrun
Daily RunSheets splitter with emailer
Install required libraries: pip install streamlit PyPDF2 pandas
Create a CSV for mappings: Columns 'Run' (e.g., SCD0001) and 'Email' (e.g., driver@example.com). Save as .csv.
Update the email configuration in the sidebar.
Run the app: streamlit run this_script.py
Open the provided local URL in your browser.
Upload the PDF and the mapping CSV, then click 'Process and Send Emails'.
