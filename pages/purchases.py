import streamlit as st
import io
import json
import pandas as pd
from pypdf import PdfReader
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import google.generativeai as genai

# Принудительно отключаем влияние Streamlit Magic на логические функции
def run_invoices_processor():
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("Нет GEMINI_API_KEY в Secrets")
        return
        
    st.title("📊 Анализ цен")
    
    folder_input_id = st.text_input("ID папки Google Диска:", key="folder_id_input")
    raw_products_list = st.text_area("Список товаров для поиска:", key="products_text_input")
    
    if st.button("Запустить поиск позиций"):
        if not folder_input_id:
            st.error("Укажите ID папки")
            return
            
        if "gcp_service_account" not in st.secrets:
            st.error("В Secrets нет gcp_service_account")
            return

        # 1. Авторизация в Google Drive
        try:
            gcp_creds = Credentials.from_service_account_info(
                dict(st.secrets["gcp_service_account"]), 
                scopes=['https://www.googleapis.com/auth/drive.readonly']
            )
            drive_client = build('drive', 'v3', credentials=gcp_creds)
        except Exception as auth_err:
            st.error(f"Ошибка подключения к Google: {auth_err}")
            return

        # 2. Получение списка файлов
        try:
            drive_query = f"'{folder_input_id}' in parents and trashed = false"
            files_request = drive_client.files().list(q=drive_query, fields="files(id, name)").execute()
            found_files = files_request.get('files', [])
        except Exception as list_err:
            st.error(f"Ошибка получения списка файлов: {list_err}")
            return

        if not found_files:
            st.warning("Файлы в папке не найдены.")
            return

        compiled_invoices_data = []
        download_progress = st.progress(0)
        
        # 3. Скачивание и извлечение текста
        for idx, file_item in enumerate(found_files):
            file_id = file_item['id']
            file_name = file_item['name']
            
            try:
                media_request = drive_client.files().get_media(fileId=file_id)
                binary_stream = io.BytesIO()
                file_downloader = MediaIoBaseDownload(binary_stream, media_request)
                
                download_finished = False
                while not download_finished:
                    _, download_finished = file_downloader.next_chunk()
                
                file_bytes_content = binary_stream.getvalue()
                lower_file_name = file_name.lower()
                extracted_text = ""

                if lower_file_name.endswith('.xlsx') or lower_file_name.endswith('.xls'):
                    excel_sheets = pd.read_excel(io.BytesIO(file_bytes_content), sheet_name=None)
                    extracted_text = "\n".join([sheet_df.to_string() for sheet_df in excel_sheets.values()])
                elif lower_file_name.endswith('.pdf'):
                    extracted_text = "\n".join([pdf_page.extract_text() for pdf_page in PdfReader(io.BytesIO(file_bytes_content)).pages if pdf_page.extract_text()])
                else:
                    extracted_text = file_bytes_content.decode('utf-8', errors='ignore')
                
                # Сохраняем структурировано, завернув в безопасный словарь
                compiled_invoices_data.append(f"Документ: {file_name}\n{extracted_text}\n---")
            except Exception as read_err:
                compiled_invoices_data.append(f"Ошибка чтения файла {file_name}: {read_err}")
                
            download_progress.progress((idx + 1) / len(found_files))

        # 4. Отправка собранного контента в ИИ
        full_text_payload = "\n".join(compiled_invoices_data)
        
        if len(full_text_payload.strip()) > 0:
            with st.spinner("ИИ сопоставляет номенклатуру..."):
                try:
                    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
                    ai_model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    ai_prompt = (
                        "Ты профессиональный закупщик. Найди цены для списка номенклатуры.\n"
                        "Список для поиска:\n" + str(raw_products_list) + "\n\n"
                        "Данные документов:\n" + str(full_text_payload) + "\n\n"
                        "Ответь исключительно в формате JSON массива объектов без markdown разметки. "
                        "Ключи: product, found_name, price, invoice, status"
                    )
                    
                    ai_response = ai_model.generate_content(ai_prompt)
                    clean_json_string = ai_response.text.strip().replace("```json", "").replace("
```", "")
                    
                    parsed_results = json.loads(clean_json_string)
                    result_dataframe = pd.DataFrame(parsed_results)
                    st.dataframe(result_dataframe, use_container_width=True)
                except Exception as ai_err:
                    st.error(f"Ошибка обработки ИИ: {ai_err}")

# Запуск изолированной функции
run_invoices_processor()
