"""
Работа с Яндекс Таблицами через публичные папки Яндекс Диска.

Схема:
1. Пользователь создаёт папку на Яндекс Диске
2. Кладёт в неё XLSX-файл
3. Делает папку публичной
4. Копирует ссылку на папку + имя файла

Бот скачивает файл и парсит через pandas.
"""
import io
import logging
from urllib.parse import urlencode

import pandas as pd
import requests

log = logging.getLogger(__name__)

YADISK_DOWNLOAD_API = "https://cloud-api.yandex.net/v1/disk/public/resources/download"


def get_download_url(public_key: str, file_path: str) -> str | None:
    """
    Получает прямую ссылку на скачивание файла из публичной папки Яндекс Диска.
    """
    try:
        params = {
            "public_key": public_key,
            "path": file_path,
        }
        url = YADISK_DOWNLOAD_API + "?" + urlencode(params)

        response = requests.get(url, timeout=15)
        response.raise_for_status()

        data = response.json()
        href = data.get("href")

        if not href:
            log.error(f"Yandex Disk API не вернул href: {data}")
            return None

        return href

    except requests.RequestException as e:
        log.error(f"Ошибка запроса к Yandex Disk API: {e}")
        return None


def parse_xlsx(content: bytes) -> list[list[str]]:
    """
    Парсит XLSX через pandas.
    Возвращает список строк (каждая строка — список ячеек).
    """
    try:
        df = pd.read_excel(
            io.BytesIO(content),
            header=None,
            dtype=str,
        )

        # Заполняем NaN пустыми строками
        df = df.fillna("")

        rows = []
        for _, row in df.iterrows():
            rows.append([str(cell) for cell in row])

        return rows

    except Exception as e:
        log.error(f"Ошибка парсинга XLSX: {e}", exc_info=True)
        return []


def parse_csv(text: str) -> list[list[str]]:
    """Парсит CSV-текст в список строк."""
    if not text:
        return []
    import csv
    reader = csv.reader(io.StringIO(text))
    return [list(row) for row in reader]


def download_yandex_table(public_key: str, file_path: str) -> list[list[str]] | None:
    """
    Скачивает и парсит файл из публичной папки Яндекс Диска.
    """
    download_url = get_download_url(public_key, file_path)
    if not download_url:
        return None

    try:
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        log.info(f"Скачано {len(response.content)} байт, тип: {content_type}")

        # CSV
        if "csv" in content_type or "text/plain" in content_type:
            text = response.content.decode("utf-8", errors="ignore")
            return parse_csv(text)

        # XLSX
        return parse_xlsx(response.content)

    except requests.RequestException as e:
        log.error(f"Ошибка скачивания файла: {e}", exc_info=True)
        return None


def get_new_rows(public_key: str, file_path: str, last_row: int) -> list[dict]:
    """
    Возвращает новые строки из файла в Яндекс Папке.

    :param public_key: Ссылка на публичную папку
    :param file_path: Путь к файлу внутри папки
    :param last_row: Последняя обработанная строка (1-based)
    """
    rows = download_yandex_table(public_key, file_path)
    if not rows:
        return []

    headers = rows[0] if rows else []

    new_rows = []
    for i, row in enumerate(rows, start=1):
        if i <= last_row:
            continue

        if not any(str(cell).strip() for cell in row):
            continue

        row_dict = {}
        for j, cell in enumerate(row):
            key = headers[j] if j < len(headers) else f"col_{j}"
            row_dict[key] = str(cell).strip()

        row_dict["_row_number"] = i
        new_rows.append(row_dict)

    return new_rows


def extract_folder_url(url: str) -> str | None:
    """
    Проверяет, что ссылка — публичная ссылка на папку Яндекс Диска.
    """
    if not url:
        return None

    url = url.strip()

    if "disk.yandex" in url and "/d/" in url:
        return url

    return None


def normalize_file_path(name: str) -> str:
    """Нормализует имя файла в путь для API."""
    name = name.strip()
    if not name.startswith("/"):
        name = "/" + name
    return name