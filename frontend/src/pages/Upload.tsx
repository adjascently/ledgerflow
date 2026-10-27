import { useState, useRef, ChangeEvent, DragEvent } from 'react'
import { getUploadUrl, uploadFileToS3 } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

type UploadStatus = 'idle' | 'uploading' | 'done' | 'error'

const ACCEPTED = { 'application/pdf': '.pdf', 'text/csv': '.csv' }

export default function Upload() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [error, setError] = useState('')
  const [dragging, setDragging] = useState(false)
  const [lastUploadId, setLastUploadId] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const accept = (f: File) => {
    if (!Object.keys(ACCEPTED).includes(f.type)) {
      setError('Only PDF and CSV files are supported.')
      return
    }
    setFile(f)
    setError('')
  }

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) accept(e.target.files[0])
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files?.[0]) accept(e.dataTransfer.files[0])
  }

  const handleUpload = async () => {
    if (!file || !user) return
    setStatus('uploading')
    setError('')
    try {
      // Step 1: get presigned URL from Swathi's API
      const { uploadId, uploadUrl } = await getUploadUrl(user.userId, file.name, file.type)
      // Step 2: PUT file directly to S3 (triggers Jasmaine's EventBridge → Step Functions)
      await uploadFileToS3(uploadUrl, file)
      localStorage.setItem(
        `finance:lastUploadMeta:${user.userId}`,
        JSON.stringify({
          uploadId,
          fileName: file.name,
          uploadedAt: new Date().toISOString(),
        }),
      )
      setLastUploadId(uploadId)
      setStatus('done')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed')
      setStatus('error')
    }
  }

  const reset = () => { setFile(null); setStatus('idle'); setError('') }

  return (
    <div className="page">
      <div className="page-header">
        <h1 className="page-title">Upload statement</h1>
        <span className="page-subtitle">PDF or CSV bank statements</span>
      </div>

      {status === 'done' ? (
        <div className="upload-success">
          <div className="success-icon">✓</div>
          <h2>Statement uploaded</h2>
          <p>Your file is being processed. You'll receive an email alert when it's done — usually within a minute.</p>
          {lastUploadId && <p>Latest upload ID: <strong>{lastUploadId}</strong></p>}
          {lastUploadId && (
            <button
              className="btn-ghost"
              onClick={() => navigate(`/transactions?uploadId=${encodeURIComponent(lastUploadId)}`)}
            >
              View parsed transactions
            </button>
          )}
          <button className="btn-primary" onClick={reset}>Upload another</button>
        </div>
      ) : (
        <>
          <div
            className={`dropzone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <input ref={inputRef} type="file" accept=".pdf,.csv" onChange={onFileChange} style={{ display: 'none' }} />
            {file ? (
              <div className="dropzone-file">
                <span className="file-name">{file.name}</span>
                <span className="file-size">{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            ) : (
              <div className="dropzone-prompt">
                <span className="dropzone-icon">↑</span>
                <p>Drop your statement here or click to browse</p>
                <span className="dropzone-hint">PDF or CSV · Max 10 MB</span>
              </div>
            )}
          </div>

          {error && <div className="alert alert-error">{error}</div>}

          <div className="upload-actions">
            {file && <button className="btn-ghost" onClick={reset}>Remove</button>}
            <button className="btn-primary" onClick={handleUpload} disabled={!file || status === 'uploading'}>
              {status === 'uploading' ? 'Uploading…' : 'Upload statement'}
            </button>
          </div>

          <div className="upload-info">
            <h3>What happens after upload?</h3>
            <ol>
              <li>Your file is stored securely in S3</li>
              <li>An automated workflow extracts your transactions</li>
              <li>Spending is analysed against your threshold</li>
              <li>You receive an email alert with the summary</li>
            </ol>
          </div>
        </>
      )}
    </div>
  )
}
