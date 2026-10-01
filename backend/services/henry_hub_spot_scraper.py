from backend.services import connection
import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlencode
import pandas as pd
from io import StringIO
import os

def run(on_progress=None):

    url = 'https://www.eia.gov/dnav/ng/hist_xls/RNGWHHDd.xls'
    df = pd.read_excel(url, sheet_name='Data 1', skiprows=2)
    df = df.rename(columns={
        'Date': 'date',
        'Henry Hub Natural Gas Spot Price (Dollars per Million Btu)': 'value'
    })
    df['date'] = pd.to_datetime(df['date'])
    df = df.dropna(subset=['value'])

    df['series_name'] = 'Henry Hub Natural Gas Spot Price (Dollars per Million Btu)'
    df['series_id'] = 'RNGWHHD'

    with connection.get_connection() as con:
        con.execute("""
        INSERT INTO tbl_hh_spot (series_id, series_name, date, value)
        SELECT series_id, series_name, date, value FROM df
    """)


if __name__ == "__main__":

    run(on_progress=lambda current, total, message: print(f"{current}/{total}: {message}"))
    connection.close_connection()