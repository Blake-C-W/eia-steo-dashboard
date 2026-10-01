const API_BASE_URL = "http://localhost:8000"

export interface RefreshResult {status: string}

export async function postRefresh(): Promise<RefreshResult> {
    const response = await fetch(`${API_BASE_URL}/api/scrape`, {
        method: "POST"
    })

    if (!response.ok) {
        throw new Error(`Refresh failed: ${response.status}`)
    }

    return response.json()
}