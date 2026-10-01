from backend.services import connection
import pandas as pd


def get_forecast_actual_pairs(con):
    query = """
        SELECT
            f.series_id,
            f.series_name,
            f.issue_date,
            f.date,
            f.value AS forecast_value,
            h.value AS actual_value,
            date_diff('month', f.issue_date, f.date) AS horizon,
            month(f.date) AS calendar_month
        FROM tbl_forecasts f
        JOIN tbl_historical h
            ON f.series_id = h.series_id AND f.date = h.date
    """
    return con.execute(query).df()


def add_error_columns(df):
    df['error'] = df['forecast_value'] - df['actual_value']
    df['abs_error'] = df['error'].abs()
    df['pct_error'] = df['error'] / df['actual_value'].replace(0, float('nan')) * 100
    return df


def add_recency_weight(df, half_life_years=4, as_of=None):
    as_of = as_of or df['issue_date'].max()
    age_years = (as_of - df['issue_date']).dt.days / 365.25
    df['weight'] = 0.5 ** (age_years / half_life_years)
    return df


def _weighted_stats(g):
    w = g['weight']
    w_sum = w.sum()

    return pd.Series({
        'series_name': g['series_name'].iloc[0],
        'bias': (g['error'] * w).sum() / w_sum,
        'mae': (g['abs_error'] * w).sum() / w_sum,
        'mape': (g['pct_error'].abs() * w).sum() / w_sum,
        'rmse': (((g['error'] ** 2) * w).sum() / w_sum) ** 0.5,
        'n': len(g),
    })


def summarize(df, group_cols):
    return (
        df.groupby(group_cols)
          .apply(_weighted_stats, include_groups=False)
          .reset_index()
    )


def get_latest_forecast(con, series_id):
    query = """
        SELECT
            series_id,
            series_name,
            issue_date,
            date,
            value AS forecast_value,
            date_diff('month', issue_date, date) AS horizon
        FROM tbl_forecasts
        WHERE series_id = ?
          AND issue_date = (SELECT MAX(issue_date) FROM tbl_forecasts WHERE series_id = ?)
        ORDER BY date
    """
    return con.execute(query, [series_id, series_id]).df()


def forecast_with_band(con, by_horizon, by_month, series_id, metric='rmse'):
    forecast_df = get_latest_forecast(con, series_id)
    forecast_df['calendar_month'] = forecast_df['date'].dt.month

    horizon_band = by_horizon[by_horizon['series_id'] == series_id].set_index('horizon')[metric]

    month_band = by_month[by_month['series_id'] == series_id].set_index('calendar_month')[metric]
    seasonal_factor = month_band / month_band.mean()

    forecast_df['horizon_rmse'] = forecast_df['horizon'].map(horizon_band)
    forecast_df['seasonal_factor'] = forecast_df['calendar_month'].map(seasonal_factor)
    forecast_df['band_width'] = forecast_df['horizon_rmse'] * forecast_df['seasonal_factor']
    forecast_df['lower_bound'] = forecast_df['forecast_value'] - forecast_df['band_width']
    forecast_df['upper_bound'] = forecast_df['forecast_value'] + forecast_df['band_width']

    return forecast_df


def save(con, banded, by_month):
    con.execute("DELETE FROM tbl_accuracy_band")
    con.execute("""
        INSERT INTO tbl_accuracy_band (
            series_id, series_name, issue_date, date, forecast_value, horizon,
            calendar_month, horizon_rmse, seasonal_factor, band_width, lower_bound, upper_bound
        )
        SELECT
            series_id, series_name, issue_date, date, forecast_value, horizon,
            calendar_month, horizon_rmse, seasonal_factor, band_width, lower_bound, upper_bound
        FROM banded
    """)

    con.execute("DELETE FROM tbl_accuracy_by_month")
    con.execute("""
        INSERT INTO tbl_accuracy_by_month (series_id, series_name, calendar_month, bias, mae, mape, rmse, n)
        SELECT series_id, series_name, calendar_month, bias, mae, mape, rmse, n FROM by_month
    """)


def run(half_life_years=4):
    con = connection.get_connection()
    df = get_forecast_actual_pairs(con)
    df = add_error_columns(df)
    df = add_recency_weight(df, half_life_years=half_life_years)

    by_horizon = summarize(df, ['series_id', 'horizon'])
    by_month = summarize(df, ['series_id', 'calendar_month'])

    series_ids = df['series_id'].unique()
    banded = pd.concat(
        [forecast_with_band(con, by_horizon, by_month, series_id) for series_id in series_ids],
        ignore_index=True,
    )

    save(con, banded, by_month)

    return banded, by_month


if __name__ == "__main__":
    banded, by_month = run()
    connection.close_connection()