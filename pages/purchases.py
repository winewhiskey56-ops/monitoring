import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

st.title("📊 Интеллектуальный анализ закупочных цен")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("В Secrets не найден GEMINI_API_KEY!")

folder_id = st.text_input("ID папки Google Диска со счетами:")
products_input = st.text_area("Введите список товаров (каждый товар с новой строки):", height=200)

if st.button("Запустить анализ цен"):
    if not folder_id:
        st.warning("Пожалуйста, введите ID папки.")
    elif "gcp_service_account" not in st.secrets:
        st.error("В Secrets не найден блок [gcp_service_account]!")
    else:
        try:
            # 1. Авторизация в Google Диflow
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = Credentials.from_service_account_info(creds_dict, scopes=['[https://www.googleapis.com/auth/drive.readonly](https://www.googleapis.com/auth/drive.readonly)'])
            service = build('drive', 'v3', credentials=creds)
            
            # 2. Получение списка файлов из папки
            query = f"'{folder_id}' in parents and trashed = false"
            results = service.files().list(q=query, fields="files(id, name)").execute()
            items = results.get('files', [])
            
            if not items:
                st.warning("В указанной папке не найдено файлов.")
            else:
                all_text_data = []
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # 3. Скачивание файлов и чтение Excel / PDF / TXT
                for idx, item in enumerate(items):
                    f_id = item['id']
                    f_name = item['name']
                    status_text.info(f"Обработка ({idx+1}/{len(items)}): {f_name}")
                    
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
                            text_content = "\n".join([df.to_string(index=False) for df in df_dict.values()])
                        elif lower_name.endswith('.pdf'):
                            reader = PdfReader(io.BytesIO(file_bytes))
                            text_content = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
                        else:
                            text_content = file_bytes.decode('utf-8', errors='ignore')
                    except Exception as e:
                        text_content = f"Ошибка чтения контента: {e}"
                        
                    all_text_data.append(f"=== НАКЛАДНОЙ ФАЙЛ: {f_name} ===\n{text_content}\n")
                    progress_bar.progress((idx + 1) / len(items))
                
                status_text.success("Все накладные успешно собраны!")
                
                # 4. Передача собранного массива текстов в Gemini за один раз
                full_invoices_text = "\n".join(all_text_data)
                if full_invoices_text.strip():
                    with st.spinner("ИИ сопоставляет позиции алкоголя и вытаскивает цены..."):
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        
                        prompt = (
                            "Ты — профессиональный менеджер по закупкам.\n"
                            "Найди актуальные закупочные цены для списка товаров из предоставленных текстов накладных.\n"
                            "Используй умный гибкий поиск (названия могут немного отличаться, объемы 0.7 и 0.75 аналогичны).\n\n"
                            "СПИСОК ТОВАРОВ ДЛЯ ПРОВЕРКИ:\n" + str(products_input) + "\n\n"
                            "ТЕКСТ НАКЛАДНЫХ С ДИСКА:\n" + str(full_invoices_text) + "\n\n"
                            "Выдай ответ СТРОГО в формате JSON-массива объектов, без markdown разметки (без слов ```json в начале).\n"
                            "Структура ответа:\n"
                            "[\n"
                            "  {\"product\": \"из списка\", \"found_name\": \"из накладной\", \"price\": 100.0, \"invoice\": \"файл.xlsx\", \"status\": \"Найдено\"}\n"
                            "]"
                        )
                        
                        response = model.generate_content(prompt)
                        clean_text = response.text.strip().replace("```json", "").replace("```", "")
                        
                        result_data = json.loads(clean_text)
                        st.dataframe(pd.DataFrame(result_data), use_container_width=True)
                        
        except Exception as top_err:
            st.error(f"Произошла общая ошибка выполнения: {top_err}")
