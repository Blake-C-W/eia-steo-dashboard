import { useState } from "react"
import './App.css'
import Sidebar from './components/sidebar'
import Overview from './pages/overview'

function App() {
  const [activePage, setActivePage] = useState<"overview" | "accuracy">("overview")

  return (
    <div className="app-layout">
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <main className="main-content">
        {activePage === "overview" && <Overview />}
        {activePage === "accuracy" && <p>Accuracy page coming soon</p>}
      </main>
    </div>
  )
}

export default App