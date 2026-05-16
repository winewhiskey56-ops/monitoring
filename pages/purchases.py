import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

st.title("📊 Анализ цен")
fid = st.text_input("ID папки:")
prod_in = st.text_area("Список товаров:")

if st.button("Поиск"):
    if fid and "gcp_service_account" in st.secrets:
        creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=['https://www.googleapis.com/auth/drive.readonly'])
        service = build('drive', 'v3', credentials=creds)
        items = service.files().list(q=f"'{fid}' in parents and trashed = false", fields="files(id, name)").execute().get('files', [])
        db_text = ""
        p_bar = st.progress(0)
        for idx, item in enumerate(items):
            req = service.files().get_media(fileId=item['id'])
            f_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(f_stream, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            b = f_stream.getvalue()
            name = item['name'].lower()
            txt = ""
            try:
                if name.endswith('.xlsx') or name.endswith('.xls'):
                    dfs = pd.read_excel(io.BytesIO(b), sheet_name=None)
                    txt = "\n".join([df.to_string() for df in dfs.values()])
                elif name.endswith('.pdf'):
                    txt = "\n".join([p.extract_text() for p in PdfReader(io.BytesIO(b)).pages if p.extract_text()])
                else:
                    txt = b.decode('utf-8', errors='ignore')
            except:
                txt = "Ошибка"
            db_text += f"\nФайл: {item['name']}\n{txt}\n"
            p_bar.progress((idx + 1) / len(items))
        if db_text:
            with st.spinner("ИИ думает..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                p = f"Найди цены для списка товаров:\n{prod_in}\n\nНакладные:\n{db_text}\n\nОтветь в формате JSON массива объектов с ключами product, found_name, price, invoice, status"
                res = model.generate_content(p).text.strip().replace("```json", "").replace("
```", "")
                st.dataframe(pd.DataFrame(json.loads(res)), use_container_width=True)
