from backend.services import connection
import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
import pandas as pd
from io import StringIO
from dotenv import load_dotenv
import os

load_dotenv()
EIA_API_KEY = os.getenv("EIA_API_KEY")

def run(on_progress=None):

    con = connection.get_connection()
    cursor = con.cursor()
    cursor.execute("SELECT DISTINCT series_id FROM tbl_forecasts")
    series_ids = [row[0] for row in cursor.fetchall()]

    url = 'https://www.eia.gov/outlooks/steo/outlook.php'

    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, 'html.parser')

    table = soup.find('table', class_='contable')

    rows = []

    for tr in table.find_all('tr'):
        cells = tr.find_all('td')

        if len(cells) < 4:
            continue

        pdf = cells[2].find('a')
        excel = cells[3].find('a')

        rows.append({
            'issue': cells[0].get_text(strip=True),
            'release_date': cells[1].get_text(strip=True),
            'pdf': urljoin(url, pdf['href']) if pdf else None,
            'excel': urljoin(url, excel['href']) if excel else None
        })

    steo_archive = pd.DataFrame(rows)
    steo_archive = steo_archive.dropna(subset=['excel'])
    steo_archive['issue_date'] = pd.to_datetime(steo_archive['issue'], format='%B %Y')
    steo_archive = steo_archive[['issue_date', 'excel']]
    steo_archive = steo_archive.sort_values(by='issue_date')
    last_issue_date = steo_archive['issue_date'].max()

    cursor.execute("SELECT MAX(last_updated) FROM tbl_meta_data WHERE table_name = 'tbl_historical'")
    row = cursor.fetchone()
    existing_last_updated = pd.Timestamp(row[0]) if row and row[0] is not None else None

    if existing_last_updated is not None and existing_last_updated == pd.Timestamp(last_issue_date):
        if on_progress:
            on_progress(current=0, total=0, message="tbl_historical already up to date, skipping")
        return

    cursor.execute("DELETE FROM tbl_historical")
    con.commit()

    for series_id in series_ids:

        if on_progress:
            on_progress(current=series_ids.index(series_id), total=len(series_ids), message=f"Processing {series_id}")

        url = f"https://api.eia.gov/v2/steo/data/?frequency=monthly&data[0]=value&facets[seriesId][]={series_id}&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000"
        url = url + "&api_key=" + EIA_API_KEY

        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
        else:
            raise RuntimeError(f"Request failed with status {response.status_code}: {response.text}")
        
        df = pd.DataFrame(data['response']['data'])

        if df.empty:
            continue

        df = df.rename(columns={
            'period': 'date',
            'seriesId': 'series_id',
            'seriesDescription': 'series_name',
            'value': 'value'
            })
        df = df.drop(columns=['unit'])
        df['date'] = pd.to_datetime(df['date'])

        con.execute("""
            INSERT INTO tbl_historical (series_id, series_name, date, value)
            SELECT series_id, series_name, date, value FROM df
        """)

    con.execute("""
        INSERT INTO tbl_meta_data (table_name, last_updated, status)
        VALUES (?, ?, ?)
    """, ['tbl_historical', last_issue_date, 'ok'])



if __name__ == "__main__":

    run(on_progress=lambda current, total, message: print(f"{current}/{total}: {message}"))
    connection.close_connection()