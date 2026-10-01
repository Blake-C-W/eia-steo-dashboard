import { useState } from "react"
import { postRefresh } from "../api/scrape"
import { getHistorical } from "../api/read_historical"

interface SidebarProps {
  activePage: "overview" | "accuracy"
  onNavigate: (page: "overview" | "accuracy") => void
}

function Sidebar({ activePage, onNavigate }: SidebarProps) {

  const [isRefreshing, setIsRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState<"success" | "error" | null>(null)

  const [isReadingHistoricals, setIsReadingHistoricals] = useState(false)
  const [readHistoricalsResult, setReadHistoricalsResult] = useState<"success" | "error" | null>(null)

  async function handleRefresh() {
    setIsRefreshing(true)
    try {
      await postRefresh()
      setRefreshResult("success")
    } catch (error) {
      setRefreshResult("error")
    } finally {
      setIsRefreshing(false)
      setTimeout(() => setRefreshResult(null), 2000)
    }
  }

  async function handleReadHistoricals() {
    setIsReadingHistoricals(true)
    try {
      const data = await getHistorical()
      console.log(data)
      setReadHistoricalsResult("success")
    } catch (error) {
      setReadHistoricalsResult("error")
    } finally {
      setIsReadingHistoricals(false)
      setTimeout(() => setReadHistoricalsResult(null), 2000)
    }
  }

  const refreshButtonClass = [
    "nav-item",
    refreshResult === "success" && "nav-item--success",
    refreshResult === "error" && "nav-item--error",
  ]
    .filter(Boolean)
    .join(" ")

  const readHistoricalsButtonClass = [
    "nav-item",
    readHistoricalsResult === "success" && "nav-item--success",
    readHistoricalsResult === "error" && "nav-item--error",
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <span>EIA Natural Gas</span>
      </div>

      <nav className="sidebar-nav">
        <button
          className={activePage === "accuracy" ? "nav-item active" : "nav-item"}
          onClick={() => onNavigate("accuracy")}
        >
          Accuracy
        </button>
        <button
          className={activePage === "overview" ? "nav-item active" : "nav-item"}
          onClick={() => onNavigate("overview")}
        >
          Overview
        </button>

        <div className="nav-section">Actions</div>
        <button className={refreshButtonClass} onClick={handleRefresh} disabled={isRefreshing}>
          {isRefreshing ? "Scraping..." : "Scrape"}
        </button>
        <button
          className={readHistoricalsButtonClass}
          onClick={handleReadHistoricals}
          disabled={isReadingHistoricals}
        >
          {isReadingHistoricals ? "Reading..." : "Read Historicals"}
        </button>
      </nav>
    </aside>
  )
}

export default Sidebar