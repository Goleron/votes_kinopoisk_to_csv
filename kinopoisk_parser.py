from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import csv
import time
import re
import logging
from urllib.parse import urljoin

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('kinopoisk_parser.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def init_driver():
    """Инициализация веб-драйвера с настройками"""
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--start-maximized")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        return driver
    except Exception as e:
        logger.error(f"Ошибка инициализации драйвера: {str(e)}")
        raise

def handle_captcha(driver):
    """Обработка капчи с ручным подтверждением"""
    if "captcha" in driver.page_source.lower():
        logger.warning("\n=== ВНИМАНИЕ: ОБНАРУЖЕНА КАПЧА ===")
        logger.warning("1. Введите капчу в ОТКРЫТОМ БРАУЗЕРЕ")
        logger.warning("2. Убедитесь, что загрузилась нужная страница")
        logger.warning("3. ТОЛЬКО ПОСЛЕ ЭТОГО нажмите Enter здесь\n")
        input("Нажмите Enter ТОЛЬКО когда страница полностью загрузится...")
        
        if "captcha" in driver.page_source.lower():
            logger.error("\nКапча не пройдена! Страница все еще показывает капчу.")
            return False
        return True
    return True

def login_to_kinopoisk(driver, user_url):
    """Ручной вход в аккаунт Кинопоиска"""
    try:
        logger.info("Начинаю процесс авторизации...")
        driver.get("https://www.kinopoisk.ru/")
        time.sleep(2)

        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти')]"))
        )
        login_button.click()
        time.sleep(2)

        logger.info("1. Введите данные для входа через Яндекс в открытом браузере")
        logger.info("2. После входа перейдите на страницу с вашими оценками")
        logger.info("3. Когда страница с оценками загрузится, нажмите Enter в терминале")
        input("Нажмите Enter, когда будете на странице с оценками...")

        if "votes" in driver.current_url:
            logger.info("Вы на странице с оценками. Авторизация подтверждена!")
            return True
        else:
            logger.error(f"Вы не на странице с оценками! Текущий URL: {driver.current_url}")
            logger.error("Перейдите на страницу с оценками и попробуйте снова.")
            return False
    except Exception as e:
        logger.error(f"Ошибка при авторизации: {str(e)}")
        return False

def get_user_rating_from_film_page(driver, film_id):
    """Получение оценки пользователя со страницы фильма"""
    try:
        film_url = f'https://www.kinopoisk.ru/film/{film_id}/'
        driver.get(film_url)
        time.sleep(2)
        
        if not handle_captcha(driver):
            logger.error(f"Не удалось пройти капчу для фильма {film_id}")
            return "-----"
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        button_content = soup.find('div', class_='style_buttonContent__nLsNw')
        if button_content:
            value_span = button_content.find('span', class_='styles_value__dffT9')
            if value_span and value_span.get_text(strip=True).isdigit():
                return value_span.get_text(strip=True)
        
        logger.warning(f"Оценка пользователя не найдена для фильма {film_id}")
        return "-----"
    except Exception as e:
        logger.error(f"Ошибка при парсинге страницы фильма {film_id}: {str(e)}")
        return "-----"

def parse_film_item(item, driver):
    """Парсинг одного элемента с фильмом"""
    try:
        info = item.find('div', class_='info')
        if not info:
            return None

        name_rus = info.find('div', class_='nameRus').get_text(strip=True) if info.find('div', class_='nameRus') else "-----"
        name_eng = info.find('div', class_='nameEng').get_text(strip=True) if info.find('div', class_='nameEng') else "-----"
        rating_div = info.find('div', class_='rating')
        kp_rating = rating_div.find('b').get_text(strip=True) if rating_div and rating_div.find('b') else "-----"
        date = item.find('div', class_='date').get_text(strip=True) if item.find('div', class_='date') else "-----"
        film_link = info.find('a')['href'] if info.find('a') and 'href' in info.find('a').attrs else ""
        film_url = urljoin('https://www.kinopoisk.ru', film_link) if film_link else ""
        film_id = re.search(r'/film/(\d+)/', film_link).group(1) if film_link else "-----"

        user_rating = "-----"
        if film_id != "-----":
            user_rating = get_user_rating_from_film_page(driver, film_id)

        return {
            '№': item.find('div', class_='num').get_text(strip=True) if item.find('div', class_='num') else "-----",
            'Название (рус)': name_rus,
            'Название (англ)': name_eng,
            'Рейтинг КП': kp_rating,
            'Оценка пользователя': user_rating,
            'Дата оценки': date,
            'Ссылка': film_url,
            'ID фильма': film_id
        }
    except Exception as e:
        logger.error(f"Ошибка парсинга элемента: {str(e)}")
        return None

def parse_ratings_page(driver):
    """Парсинг страницы с оценками"""
    try:
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table.historyVotes"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        ratings = []
        
        if "нет оценок" in soup.get_text().lower():
            return []

        for item in soup.select('div.profileFilmsList div.item, div.profileFilmsList div.item.even'):
            film_data = parse_film_item(item, driver)
            if film_data:
                ratings.append(film_data)
        
        return ratings if ratings else []
        
    except Exception as e:
        logger.error(f"Ошибка парсинга страницы: {str(e)}")
        return None

def save_to_csv(data, filename):
    """Сохранение данных в CSV"""
    try:
        if not data:
            logger.warning("Нет данных для сохранения")
            return False
            
        with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
            logger.info(f"Успешно сохранено {len(data)} записей в {filename}")
            return True
    except Exception as e:
        logger.error(f"Ошибка сохранения CSV: {str(e)}")
        return False

def parse_user_ratings(user_url, output_file='kinopoisk_ratings.csv'):
    """Основная функция парсинга"""
    driver = None
    try:
        driver = init_driver()
        
        if not login_to_kinopoisk(driver, user_url):
            logger.error("Не удалось войти в аккаунт или перейти на страницу с оценками. Прерываю парсинг.")
            return
        
        match = re.search(r'user/(\d+)/', user_url)
        if not match:
            logger.error("Неверный URL. Убедитесь, что он содержит ID пользователя.")
            return
        user_id = match.group(1)
        
        all_ratings = []
        page = 1
        max_empty_pages = 3
        empty_pages_count = 0
        
        while True:
            page_url = f'https://www.kinopoisk.ru/user/{user_id}/votes/list/ord/date/page/{page}/'
            logger.info(f"Обрабатываю страницу {page}")
            
            driver.get(page_url)
            time.sleep(3)
            
            if "captcha" in driver.page_source.lower():
                if not handle_captcha(driver):
                    break
                driver.get(page_url)
                time.sleep(3)
                continue
                
            ratings = parse_ratings_page(driver)
            if ratings is None:
                logger.error("Ошибка парсинга страницы, прекращаю работу")
                break
                
            if not ratings:
                empty_pages_count += 1
                logger.info(f"Пустая страница {page} ({empty_pages_count}/{max_empty_pages})")
                if empty_pages_count >= max_empty_pages:
                    logger.info("Достигнут конец списка оценок")
                    break
            else:
                empty_pages_count = 0
                all_ratings.extend(ratings)
                logger.info(f"Найдено {len(ratings)} оценок")
            
            page += 1
            time.sleep(5)
            
        if not save_to_csv(all_ratings, output_file):
            logger.error("Не удалось сохранить данные")
            
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}")
    finally:
        if driver:
            driver.quit()
        logger.info("Парсинг завершен")

if __name__ == "__main__":
    user_url = input("Введите URL профиля с оценками (например: https://www.kinopoisk.ru/user/12345678/votes/): ").strip()
    parse_user_ratings(user_url)