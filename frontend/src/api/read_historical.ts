const API_BASE_URL = "http://localhost:8000"

export async function getHistorical() {
  const response = await fetch(`${API_BASE_URL}/api/read_historical`)

  if (!response.ok) {
    throw new Error(`Read historicals failed: ${response.status}`)
  }

  return response.json()
}