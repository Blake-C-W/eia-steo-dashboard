from backend.services import connection
import datetime
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import pandas as pd
from io import StringIO

def scrape_files(missing_issue_dates, con, on_progress=None):

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
    steo_archive = steo_archive[steo_archive['issue_date'].isin(missing_issue_dates)]

    for _, row in steo_archive.iterrows():

        issue_date = row['issue_date']
        excel_url = row['excel']

        if on_progress:
            on_progress(current=_, total=len(steo_archive), message=f"Processing {issue_date:%Y-%m}")

        if issue_date not in missing_issue_dates:
            continue

        df = pd.read_excel(excel_url, sheet_name='Contents')
        df = df.dropna(how='all', axis=1)  # Drop rows where all elements are NaN
        table_row_index = df.apply(lambda row: row.astype(str).str.startswith('Table').any(), axis=1).idxmax()
        df = df.iloc[table_row_index:]
        table_col = df.apply(lambda col: col.astype(str).str.startswith('Table').any()).idxmax()
        df = df[[table_col]].rename(columns={table_col: 'Table'})
        df = df[
            df['Table'].str.contains('U.S. Regional Natural Gas Prices', regex=False, na=False)
            | df['Table'].str.contains('U.S. Natural Gas Supply, Consumption, and Inventories', regex=False, na=False)
        ]
        df['sheet_name'] = (
            df['Table']
            .str.extract(r'Table\s+([^.]+)\.')[0]
            .str.strip()
            .str.lower()
            + 'tab'
        )

        if len(df) != 2:
            print(f"No relevant tables found in {excel_url} for issue date {issue_date}")
            raise ValueError(f"No relevant tables found in {excel_url} for issue date {issue_date}")
        
        for _, row in df.iterrows():
            sheet_name = row['sheet_name']
            df = pd.read_excel(excel_url, sheet_name=sheet_name, skiprows=2)
            df.iat[0, 0] = 'need for next step'
            df = df.dropna(subset=df.columns[0])
            df = df.rename(columns={df.columns[0]: 'series_id', df.columns[1]: 'series_name'})
            df = df.set_index(['series_id', 'series_name'])
            columns = pd.Series(df.columns, dtype=object)
            columns = columns.mask(columns.astype(str).str.startswith('Unnamed'))
            df.columns = columns.ffill()

            months = df.iloc[0]
            def to_date(year, month):
                return pd.to_datetime(f"{int(float(year))}-{month}", format="%Y-%b").strftime("%Y-%m-01")

            df.columns = [to_date(year, month) for year, month in zip(df.columns, months)]
            df = df.iloc[1:]
            df = df.reset_index()
            df = df.melt(id_vars=['series_id', 'series_name'], var_name='date', value_name='value')
            df['date'] = pd.to_datetime(df['date'])
            df['issue_date'] = issue_date
            df = df[df['date'] >= issue_date]

            con.execute("""
                INSERT INTO tbl_forecasts (series_id, series_name, date, value, issue_date)
                SELECT series_id, series_name, date, value, issue_date FROM df
            """)

            del df


def run(on_progress=None):

    start_date = datetime.datetime.strptime('2010-01', '%Y-%m')
    end_date = datetime.datetime.today()

    con = connection.get_connection()
    cursor = con.cursor()
    cursor.execute("SELECT COUNT(*) FROM tbl_forecasts")
    count = cursor.fetchone()[0]

    if count == 0:
        missing_issue_dates = pd.date_range(start=start_date, end=end_date, freq='MS')
        scrape_files(missing_issue_dates, con, on_progress=on_progress)
    else:
        cursor.execute("SELECT DISTINCT issue_date FROM tbl_forecasts")
        existing_issue_dates = {pd.Timestamp(row[0]) for row in cursor.fetchall()}
        all_months = pd.date_range(start=start_date, end=end_date, freq='MS')
        missing_issue_dates = [d for d in all_months if d not in existing_issue_dates]
        if missing_issue_dates:
            scrape_files(missing_issue_dates, con, on_progress=on_progress)
        



if __name__ == "__main__":

    run(on_progress=lambda current, total, message: print(f"{current}/{total}: {message}"))
    connection.close_connection()