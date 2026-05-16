import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

st.title("🔍 Быстрый поиск закупочной цены")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("В Secrets не найден GEMINI_API_KEY!")

FOLDER_ID = st.secrets.get("google_folder_id") or st.secrets.get("folder_id")

if not FOLDER_ID:
    st.error("Ошибка: В st.secrets не найден ID папки")

product_search = st.text_input("Введите название товара для проверки цены:")

if st.button("Найти цену в накладных"):
    if not product_search:
        st.warning("Пожалуйста, введите название товара.")
    elif not FOLDER_ID:
        st.error("Невозможно запустить поиск без ID папки.")
    elif "gcp_service_account" not in st.secrets:
        st.error("В Secrets не найден блок [gcp_service_account]!")
    else:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=['https://www.googleapis.com/auth/drive.readonly'])
            service = build('drive', 'v3', credentials=creds)
            
            query = "'" + str(FOLDER_ID) + "' in parents and trashed = false"
            results = service.files().list(q=query, fields="files(id, name)").execute()
            items = results.get('files', [])
            
            if not items:
                st.warning("В вашей папке на Google Диске пока нет файлов.")
            else:
                all_text_data = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for idx, item in enumerate(items):
                    f_id = item['id']
                    f_name = item['name']
                    status_text.info("Проверяю документ: " + str(f_name))
                    
                    request = service.files().get_media(fileId=f_id)
                    file_stream = io.BytesIO()
                    downloader = MediaIoBaseDownload(file_stream, request)
                    done = False
                    while not done:
                        _, done = downloader.next_chunk()
                        
                    file_bytes = file_stream.getvalue()
                    lower_name = f_name.lower()
                    text_content = ""
                    
                    try:
                        if lower_name.endswith('.xlsx') or lower_name.endswith('.xls'):
                            df_dict = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
                            sheets_text = []
                            for df in df_dict.values():
                                sheets_text.append(df.to_string(index=False))
                            text_content = "\n".join(sheets_text)
                        elif lower_name.endswith('.pdf'):
                            reader = PdfReader(io.BytesIO(file_bytes))
                            pdf_text = []
                            for page in reader.pages:
                                if page.extract_text():
                                    pdf_text.append(page.extract_text())
                            text_content = "\n".join(pdf_text)
                        else:
                            text_content = file_bytes.decode('utf-8', errors='ignore')
                    except Exception:
                        text_content = ""
                        
                    all_text_data.append("=== ФАЙЛ: " + str(f_name) + " ===\n" + str(text_content) + "\n")
                    progress_bar.progress((idx + 1) / len(items))
                
                status_text.empty()
                progress_bar.empty()
                
                full_invoices_text = "\n".join(all_text_data)
                if full_invoices_text.strip():
                    with st.spinner("ИИ сканирует архивы..."):
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = "Ты менеджер базы данных. Найди упоминания товара и его цену в текстах документов.\n"
                        prompt += "Искомый товар: " + str(product_search) + "\n\n"
                        prompt += "ТЕКСТЫ НАКЛАДНЫХ:\n" + str(full_invoices_text) + "\n\n"
                        prompt += "Если товар найден в нескольких файлах, выведи все упоминания (историю цен).\n"
                        prompt += "Ответь строго в формате JSON-массива объектов с ключами product, found_name, price, invoice, status. Не используй markdown разметку."
                        
                        response = model.generate_content(prompt)
                        clean_text = response.text.strip().replace("```json", "").replace("
```", "")
                        
                        result_data = json.loads(clean_text)
                        if result_data:
                            st.success("История цен по запросу: " + str(product_search))
                            st.dataframe(pd.DataFrame(result_data), use_container_width=True)
                        else:
                            st.info("Позиция с таким названием не обнаружена в загруженных накладных.")
                            
        except Exception as top_err:
            st.error("Ошибка выполнения поиска: " + str(top_err))
