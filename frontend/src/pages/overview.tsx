import { useEffect, useMemo, useState } from "react"
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { getHistorical } from "../api/read_historical"

interface HistoricalRow {
  series_name: string
  date: string
  value: number
  historical_forecast: "historical" | "forecast"
  five_year_avg?: number | null
  five_year_low?: number | null
  five_year_high?: number | null
}

interface HistoricalResponse {
  hh: HistoricalRow[]
  storage: HistoricalRow[]
  rest: HistoricalRow[]
}

interface ChartRow extends HistoricalRow {
  historicalValue: number | null
  forecastValue: number | null
  five_year_band: number | null
}

type ChartType = "price" | "storage" | "lng" | "balance"
type ChartKey = "price" | "storage" | "lng" | "balance"

interface ChartSeries {
  key: ChartKey
  rows: HistoricalRow[]
  title: string
  subtitle: string
  type: ChartType
}

interface DateRange {
  start: string
  end: string
}

const LNG_SERIES = "Natural Gas LNG Gross Exports"
const BALANCE_SERIES = "Natural Gas Balancing Item (Consumption - Supply)"
const DEFAULT_STORAGE_SERIES = "Natural Gas Working Inventory Lower 48"

const formatAxisDate = (date: string) =>
  new Date(`${date.slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", year: "2-digit" })

const formatTooltipDate = (date: string) =>
  new Date(`${date.slice(0, 10)}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })

const toInputDate = (date: Date) => date.toISOString().slice(0, 10)

const fiveYearsAgo = () => {
  const date = new Date()
  date.setFullYear(date.getFullYear() - 5)
  return toInputDate(date)
}

const monthsAgo = (months: number) => {
  const date = new Date()
  const day = date.getDate()
  date.setDate(1)
  date.setMonth(date.getMonth() - months)
  const lastDayOfMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
  date.setDate(Math.min(day, lastDayOfMonth))
  return toInputDate(date)
}

const fourMonthsAgo = () => monthsAgo(4)

const oneYearAgo = () => {
  const date = new Date()
  date.setFullYear(date.getFullYear() - 1)
  return toInputDate(date)
}

const latestDate = (rows: HistoricalRow[]) =>
  rows.reduce((latest, row) => {
    const date = row.date.slice(0, 10)
    return date > latest ? date : latest
  }, "")

const shortStorageName = (seriesName: string) =>
  seriesName
    .replace("Natural Gas Working Inventory ", "")
    .replace(" Consuming Region", "")
    .replace(" Region", "")

const prepareChartRows = (rows: HistoricalRow[]): ChartRow[] => {
  const prepared = rows
    .slice()
    .sort((a, b) => a.date.slice(0, 10).localeCompare(b.date.slice(0, 10)))
    .map((row) => ({
      ...row,
      historicalValue: row.historical_forecast === "historical" ? row.value : null,
      forecastValue: row.historical_forecast === "forecast" ? row.value : null,
      five_year_band:
        row.historical_forecast === "historical" && row.five_year_low != null && row.five_year_high != null
          ? row.five_year_high - row.five_year_low
          : null,
    }))

  const firstForecastIndex = prepared.findIndex((row) => row.historical_forecast === "forecast")

  // Join the forecast visually to the last actual point without changing the API data.
  if (firstForecastIndex > 0) {
    prepared[firstForecastIndex - 1].forecastValue = prepared[firstForecastIndex - 1].value
  }

  return prepared
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null

  const hiddenKeys = new Set(["five_year_low", "five_year_band"])
  const items = payload.filter((item: any) => item.value != null && !hiddenKeys.has(item.dataKey))

  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip-date">{formatTooltipDate(String(label))}</div>
      {items.map((item: any) => (
        <div className="chart-tooltip-row" key={`${item.dataKey}-${item.name}`}>
          <span>{item.name}</span>
          <strong>{Number(item.value).toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
        </div>
      ))}
    </div>
  )
}

function Overview() {
  const [data, setData] = useState<HistoricalResponse>({ hh: [], storage: [], rest: [] })
  const [storageSeries, setStorageSeries] = useState(DEFAULT_STORAGE_SERIES)
  const [dateRanges, setDateRanges] = useState<Record<ChartKey, DateRange>>({
    price: { start: fourMonthsAgo(), end: "" },
    storage: { start: oneYearAgo(), end: "" },
    lng: { start: fiveYearsAgo(), end: "" },
    balance: { start: fiveYearsAgo(), end: "" },
  })

  useEffect(() => {
    getHistorical().then((response: HistoricalResponse) => {
      const normalized: HistoricalResponse = {
        hh: response.hh ?? [],
        storage: response.storage ?? [],
        rest: response.rest ?? [],
      }

      setData(normalized)

      const lngRows = normalized.rest.filter((row) => row.series_name === LNG_SERIES)
      const balanceRows = normalized.rest.filter((row) => row.series_name === BALANCE_SERIES)

      setDateRanges({
        price: { start: fourMonthsAgo(), end: latestDate(normalized.hh) },
        storage: { start: oneYearAgo(), end: latestDate(normalized.storage) },
        lng: { start: fiveYearsAgo(), end: latestDate(lngRows) },
        balance: { start: fiveYearsAgo(), end: latestDate(balanceRows) },
      })

      const availableStorage = new Set(normalized.storage.map((row) => row.series_name))
      if (!availableStorage.has(DEFAULT_STORAGE_SERIES) && normalized.storage.length > 0) {
        setStorageSeries(normalized.storage[0].series_name)
      }
    })
  }, [])

  const storageOptions = useMemo(
    () => Array.from(new Set(data.storage.map((row) => row.series_name))).sort(),
    [data.storage],
  )

  const charts = useMemo<ChartSeries[]>(() => {
    const lngRows = data.rest.filter((row) => row.series_name === LNG_SERIES)
    const balanceRows = data.rest.filter((row) => row.series_name === BALANCE_SERIES)

    return [
      {
        key: "price",
        title: "Henry Hub Price Forecast",
        subtitle: "Spot price and STEO forecast · $/Mcf",
        type: "price",
        // The API's hh array is dedicated to Henry Hub, so do not filter the
        // historical spot rows by an exact source-table series label here.
        rows: data.hh,
      },
      {
        key: "storage",
        title: "Storage vs 5-Year Average",
        subtitle: `${shortStorageName(storageSeries)} working gas · Bcf`,
        type: "storage",
        rows: data.storage.filter((row) => row.series_name === storageSeries),
      },
      {
        key: "lng",
        title: "LNG Exports",
        subtitle: "U.S. LNG gross exports · Bcf/d",
        type: "lng",
        rows: lngRows,
      },
      {
        key: "balance",
        title: "Market Balance",
        subtitle: "Consumption minus supply · Bcf/d",
        type: "balance",
        rows: balanceRows,
      },
    ]
  }, [data, storageSeries])

  const updateDateRange = (chartKey: ChartKey, field: keyof DateRange, value: string) => {
    setDateRanges((current) => ({
      ...current,
      [chartKey]: {
        ...current[chartKey],
        [field]: value,
      },
    }))
  }

  const resetChartRange = (chart: ChartSeries) => {
    setDateRanges((current) => ({
      ...current,
      [chart.key]: {
        start: chart.key === "price" ? fourMonthsAgo() : chart.key === "storage" ? oneYearAgo() : fiveYearsAgo(),
        end: latestDate(chart.rows),
      },
    }))
  }

  return (
    <div className="overview-grid">
      {charts.map((chart) => {
        const range = dateRanges[chart.key]
        const filteredRows = chart.rows.filter((row) => {
          const rowDate = row.date.slice(0, 10)
          const afterStart = !range.start || rowDate >= range.start
          const beforeEnd = !range.end || rowDate <= range.end
          return afterStart && beforeEnd
        })

        const rows = prepareChartRows(filteredRows)
        const forecastStart = rows.find((row) => row.historical_forecast === "forecast")?.date
        const lastDate = rows.at(-1)?.date
        const gradientId = `chart-gradient-${chart.key}`
        const bandGradientId = `band-gradient-${chart.key}`
        const height = 245

        return (
          <div key={chart.key} className="overview-chart-card">
            <div className="chart-card-header">
              <div className="chart-card-title">
                <h3>{chart.title}</h3>
                <p className="chart-card-subtitle">{chart.subtitle}</p>
              </div>

              <div className="chart-card-actions">
                {chart.type === "storage" && storageOptions.length > 1 && (
                  <select className="chart-select" value={storageSeries} onChange={(event) => setStorageSeries(event.target.value)}>
                    {storageOptions.map((series) => (
                      <option key={series} value={series}>{shortStorageName(series)}</option>
                    ))}
                  </select>
                )}
                <span className="chart-badge">STEO</span>
              </div>
            </div>

            <div className="chart-filter-row">
              <div className="chart-legend">
                <span><i className="legend-line legend-line--historical" />Historical</span>
                <span><i className="legend-line legend-line--forecast" />Forecast</span>
                {chart.type === "storage" && <span><i className="legend-line legend-line--average" />5Y avg</span>}
                {chart.type === "storage" && <span><i className="legend-band" />5Y range</span>}
              </div>

              <div className="chart-date-picker">
                <label className="chart-date-field">
                  <span>From</span>
                  <input
                    type="date"
                    value={range.start}
                    max={range.end || undefined}
                    onChange={(event) => updateDateRange(chart.key, "start", event.target.value)}
                  />
                </label>
                <span className="chart-date-separator">–</span>
                <label className="chart-date-field">
                  <span>To</span>
                  <input
                    type="date"
                    value={range.end}
                    min={range.start || undefined}
                    onChange={(event) => updateDateRange(chart.key, "end", event.target.value)}
                  />
                </label>
                <button className="chart-date-reset" type="button" onClick={() => resetChartRange(chart)}>{chart.key === "price" ? "4M" : chart.key === "storage" ? "1Y" : "5Y"}</button>
              </div>
            </div>

            <ResponsiveContainer width="100%" height={height}>
              {chart.type === "balance" ? (
                <BarChart data={rows} margin={{ top: 12, right: 8, bottom: 0, left: -12 }}>
                  <CartesianGrid vertical={false} stroke="#edf0f4" strokeDasharray="3 5" />
                  {forecastStart && lastDate && <ReferenceArea x1={forecastStart} x2={lastDate} fill="#246bfd" fillOpacity={0.035} />}
                  <ReferenceLine y={0} stroke="#cfd4dc" strokeWidth={1.2} />
                  {forecastStart && <ReferenceLine x={forecastStart} stroke="#b9c1cd" strokeDasharray="4 5" />}
                  <XAxis dataKey="date" tickFormatter={formatAxisDate} axisLine={false} tickLine={false} minTickGap={42} tick={{ fill: "#8b919a", fontSize: 11 }} dy={8} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8b919a", fontSize: 11 }} width={48} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(21, 85, 216, 0.035)" }} />
                  <Bar dataKey="value" name="Balance" radius={[4, 4, 4, 4]} maxBarSize={18}>
                    {rows.map((row, rowIndex) => (
                      <Cell
                        key={`${row.date}-${rowIndex}`}
                        fill={row.value >= 0 ? "#37b987" : "#ed6b8a"}
                        fillOpacity={row.historical_forecast === "forecast" ? 0.48 : 0.95}
                      />
                    ))}
                  </Bar>
                </BarChart>
              ) : (
                <AreaChart data={rows} margin={{ top: 12, right: 8, bottom: 0, left: -12 }}>
                  <defs>
                    <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#246bfd" stopOpacity={0.18} />
                      <stop offset="100%" stopColor="#246bfd" stopOpacity={0.01} />
                    </linearGradient>
                    <linearGradient id={bandGradientId} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#aab4c5" stopOpacity={0.24} />
                      <stop offset="100%" stopColor="#aab4c5" stopOpacity={0.09} />
                    </linearGradient>
                  </defs>

                  <CartesianGrid vertical={false} stroke="#edf0f4" strokeDasharray="3 5" />
                  {forecastStart && lastDate && <ReferenceArea x1={forecastStart} x2={lastDate} fill="#246bfd" fillOpacity={0.035} />}
                  {forecastStart && <ReferenceLine x={forecastStart} stroke="#b9c1cd" strokeDasharray="4 5" />}
                  <XAxis dataKey="date" tickFormatter={formatAxisDate} axisLine={false} tickLine={false} minTickGap={42} tick={{ fill: "#8b919a", fontSize: 11 }} dy={8} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8b919a", fontSize: 11 }} width={52} />
                  <Tooltip content={<CustomTooltip />} cursor={{ stroke: "#d5d9df", strokeDasharray: "4 4" }} />

                  {chart.type === "storage" && (
                    <>
                      <Area type="monotone" dataKey="five_year_low" stackId="five-year-band" stroke="none" fill="transparent" isAnimationActive={false} connectNulls={false} />
                      <Area type="monotone" dataKey="five_year_band" stackId="five-year-band" name="5Y range" stroke="none" fill={`url(#${bandGradientId})`} isAnimationActive={false} connectNulls={false} />
                      <Line type="monotone" dataKey="five_year_avg" name="5Y avg" stroke="#8d96a5" strokeWidth={1.5} strokeDasharray="6 5" dot={false} connectNulls={false} />
                    </>
                  )}

                  <Area
                    type="monotone"
                    dataKey="historicalValue"
                    name="Historical"
                    stroke="#246bfd"
                    strokeWidth={2.4}
                    fill={`url(#${gradientId})`}
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, fill: "#ffffff", stroke: "#246bfd" }}
                    connectNulls={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="forecastValue"
                    name="Forecast"
                    stroke="#246bfd"
                    strokeWidth={2.4}
                    strokeDasharray="7 6"
                    dot={false}
                    activeDot={{ r: 4, strokeWidth: 2, fill: "#ffffff", stroke: "#246bfd" }}
                    connectNulls={false}
                  />
                </AreaChart>
              )}
            </ResponsiveContainer>
          </div>
        )
      })}
    </div>
  )
}

export default Overview
