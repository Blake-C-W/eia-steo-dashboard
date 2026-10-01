from backend.services import connection
import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
import pandas as pd
from io import StringIO
import os

def run(on_progress=None):

    url = 'https://www.eia.gov/dnav/ng/xls/NG_STOR_WKLY_S1_W.xls'
    df = pd.read_excel(url, sheet_name='Data 1', skiprows=2)
    df = df.rename(columns={
        'Date': 'date',
        'Weekly Lower 48 States Natural Gas Working Underground Storage (Billion Cubic Feet)': 'Lower 48',
        'Weekly East Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'East',
        'Weekly Midwest Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'Midwest',
        'Weekly Mountain Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'Mountain',
        'Weekly Pacific Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'Pacific',
        'Weekly South Central  Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'South Central',
        'Weekly Salt South Central Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'South Central Salt',
        'Weekly Nonsalt South Central Region Natural Gas Working Underground Storage (Billion Cubic Feet)': 'South Central Nonsalt',
    })
    df['date'] = pd.to_datetime(df['date'])
    df = df.melt(id_vars=['date'], var_name='series_name', value_name='value')

    with connection.get_connection() as con:
        con.execute("""
        INSERT INTO tbl_storage (series_name, date, value)
        SELECT series_name, date, value FROM df
    """)


if __name__ == "__main__":

    run(on_progress=lambda current, total, message: print(f"{current}/{total}: {message}"))
    connection.close_connection()