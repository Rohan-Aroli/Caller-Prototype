import { useState } from 'react'
import './App.css'

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [agentId, setAgentId] = useState<string>('')
  const [message, setMessage] = useState<string>('')
  const [loading, setLoading] = useState<boolean>(false)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0])
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!file || !agentId) {
      setMessage('Please select a file and enter an agent ID.')
      return
    }

    setLoading(true)
    setMessage('')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('agent_id', agentId)

    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

    try {
      const response = await fetch(`${baseUrl}/api/v1/leads/upload-csv`, {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()

      if (response.ok) {
        setMessage(`Success! Processed ${data.processed_count} rows. ${data.errors.length} errors.`)
        console.log(data)
      } else {
        setMessage(`Error: ${data.detail || 'Failed to upload CSV'}`)
      }
    } catch (err) {
      setMessage('Error connecting to the server.')
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="App">
      <h1>CSV Lead Upload</h1>
      <form onSubmit={handleSubmit} className="upload-form">
        <div>
          <label htmlFor="agentId">Agent ID: </label>
          <input
            type="text"
            id="agentId"
            value={agentId}
            onChange={(e) => setAgentId(e.target.value)}
            placeholder="Enter Agent ID"
            required
          />
        </div>
        <div style={{ marginTop: '1rem' }}>
          <label htmlFor="file">CSV File: </label>
          <input
            type="file"
            id="file"
            accept=".csv"
            onChange={handleFileChange}
            required
          />
        </div>
        <button type="submit" disabled={loading} style={{ marginTop: '1rem' }}>
          {loading ? 'Uploading...' : 'Upload'}
        </button>
      </form>
      {message && <p style={{ marginTop: '1rem', fontWeight: 'bold' }}>{message}</p>}
    </div>
  )
}

export default App
