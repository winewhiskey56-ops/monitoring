import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import pandas as pd

def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    # Для Streamlit Cloud (пути из прошлого шага)
    # options.binary_location = "/usr/bin/chromium"
    # service = Service("/usr/bin/chromedriver")
    # driver = webdriver.Chrome(service=service, options=options)
    
    # Для локального теста (раскомментируйте, если запускаете на ПК):
    from webdriver_manager.chrome import ChromeDriverManager
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    return driver

def search_lenta(wine_name):
    driver = get_driver()
    try:
        # Сначала заходим на главную, чтобы проставить куки
        driver.get("https://lenta.com/")
        time.sleep(2)
        
        # Устанавливаем куку города Оренбург (Slug для Ленты часто 'orenburg')
        driver.add_cookie({"name": "city", "value": "orenburg"})
        
        # Переходим к поиску
        search_url = f"https://lenta.com/search/?searchText={wine_name}"
        driver.get(search_url)
        time.sleep(4) # Даем время на прогрузку скриптов
        
        # Пробуем найти цену (используем более гибкий селектор)
        # Ищем текст, содержащий цифры в блоке цены
        price_elem = driver.find_element(By.CSS_SELECTOR, ".price-label__integer")
        return f"{price_elem.text} ₽"
    except Exception as e:
        return "Не найдено"
    finally:
        driver.quit()

def search_metro(wine_name):
    driver = get_driver()
    try:
        driver.get("https://online.metro-cc.ru/")
        time.sleep(2)
        
        # Для Metro кука региона (Оренбург обычно 68 или через slug)
        # Самый надежный способ - передать заголовок или найти кнопку выбора
        driver.add_cookie({"name": "metro_store_id", "value": "68"}) # ID магазина в Оренбурге
        
        driver.get(f"https://online.metro-cc.ru/search?q={wine_name}")
        time.sleep(4)
        
        # В Metro сложная структура, ищем актуальную цену
        price_elem = driver.find_element(By.CSS_SELECTOR, ".product-unit-prices__actual-wrapper .product-price__sum-rubles")
        return f"{price_elem.text} ₽"
    except:
        return "Не найдено"
    finally:
        driver.quit()

# --- Интерфейс остается прежним ---
st.title("🍷 Мониторинг: Оренбург")
# ... (код UI из прошлого сообщения)
