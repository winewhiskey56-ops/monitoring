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

st.title("📊 Анализ закупочных цен")

fid = st.text_input("ID папки Google Диска:")
prod_in = st.text_area("Список товаров (каждый с новой строки):")

if st.button("Запустить поиск"):
    if not fid or "gcp_service_account" not in st.secrets:
        st.error("Проверьте ID папки или настройки Secrets!")
    else:
        # 1. Авторизация
        creds = Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]), 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)
        
        # 2. Сбор файлов
        q = f"'{fid}' in parents and trashed = false"
        items = service.files().list(q=q, fields="files(id, name)").execute().get('files', [])
        
        db_text = ""
        p_bar = st.progress(0)
        
        for idx, item in enumerate(items):
            # Скачивание файла
            req = service.files().get_media(fileId=item['id'])
            f_stream = io.BytesIO()
            downloader = MediaIoBaseDownload(f_stream, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            
            b = f_stream.getvalue()
            name = item['name'].lower()
            
            # Извлечение текста
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
                txt = f"Ошибка чтения {item['name']}"
                
            db_text += f"\nФайл: {item['name']}\n{txt}\n"
            p_bar.progress((idx + 1) / len(items))
            
        # 3. Запрос к ИИ
        if db_text:
            with st.spinner("ИИ анализирует..."):
                model = genai.GenerativeModel('gemini-1.5-flash')
                p = f"Найди цены для списка товаров:\n{prod_in}\n\nИспользуй текст накладных:\n{db_text}\n\nОтветь СТРОГО в формате JSON-массива без markdown разметки: " + "[{\"product\":\"...\",\"found_name\":\"...\",\"price\":0.0,\"invoice\":\"...\"}]"
                
                res = model.generate_content(p).text.strip()
                res = res.replace("```json", "").replace("
```", "")
                
                st.dataframe(pd.DataFrame(json.loads(res)), use_container_width=True)
