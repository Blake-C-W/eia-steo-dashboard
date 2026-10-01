import os
import duckdb

DB_PATH = os.path.join("data", "app.duckdb")

_con: duckdb.DuckDBPyConnection | None = None


def get_connection() -> duckdb.DuckDBPyConnection:
    global _con
    if _con is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        _con = duckdb.connect(DB_PATH)
        _init_schema(_con)
    return _con


def close_connection() -> None:
    global _con
    if _con is not None:
        _con.close()
        _con = None


def _init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_historical (
            date DATE,
            series_id TEXT,
            series_name TEXT,
            value DOUBLE,
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_forecasts (
            issue_date DATE,
            date DATE,
            series_id TEXT,
            series_name TEXT,
            value DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_meta_data (
        table_name TEXT,
        last_updated DATE,
        status TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_accuracy_band (
            series_id TEXT,
            series_name TEXT,
            issue_date DATE,
            date DATE,
            forecast_value DOUBLE,
            horizon INTEGER,
            calendar_month INTEGER,
            horizon_rmse DOUBLE,
            seasonal_factor DOUBLE,
            band_width DOUBLE,
            lower_bound DOUBLE,
            upper_bound DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_accuracy_by_month (
            series_id TEXT,
            series_name TEXT,
            calendar_month INTEGER,
            bias DOUBLE,
            mae DOUBLE,
            mape DOUBLE,
            rmse DOUBLE,
            n INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_hh_spot (
            series_id TEXT,
            series_name TEXT,
            date DATE,
            value DOUBLE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tbl_storage (
            series_name TEXT,
            date DATE,
            value DOUBLE
        )
    """)