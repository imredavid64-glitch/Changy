import { useState } from 'react'
import './App.css'

type NotebookCell = {
  id: string
  language: 'python' | 'r' | 'sql' | 'markdown'
  content: string
}

type Notebook = {
  id: string
  title: string
  cells: NotebookCell[]
}

type SqlQueryResponse = {
  columns: string[]
  rows: unknown[][]
}

type KernelExecuteResponse = {
  status: string
  stdout: string
  stderr: string
  result?: unknown
  display?: Record<string, unknown>[]
}

type DbConnection = { id: string; kind: string; url: string }
type DbSchema = { schemas: string[]; tables: { schema: string | null; name: string; columns: { name: string; type: string }[] }[] }
type DataItem = { id: string; name: string; status?: string; kind?: string }

const API_BASE = 'http://localhost:8000'

function App() {
  const [status, setStatus] = useState<string>('idle')
  const [error, setError] = useState<string | null>(null)

  const [notebooks, setNotebooks] = useState<Notebook[]>([])
  const [activeNotebook, setActiveNotebook] = useState<Notebook | null>(null)

  const [sql, setSql] = useState<string>('select 42 as answer;')
  const [sqlResult, setSqlResult] = useState<SqlQueryResponse | null>(null)

  const [cellOutputs, setCellOutputs] = useState<
    Record<
      string,
      | { kind: 'sql'; value: SqlQueryResponse }
      | { kind: 'kernel'; value: KernelExecuteResponse }
      | { kind: 'text'; value: string }
    >
  >({})

  const [chatInput, setChatInput] = useState<string>(
    'Create a SQL query that counts rows in a table named users.'
  )
  const [chatLog, setChatLog] = useState<
    { role: 'user' | 'assistant'; content: string }[]
  >([])

  const [dbKind, setDbKind] = useState<'postgres' | 'mysql' | 'snowflake'>('postgres')
  const [dbUrl, setDbUrl] = useState('postgresql+psycopg://user:pass@localhost:5432/dbname')
  const [dbConnections, setDbConnections] = useState<DbConnection[]>([])
  const [activeConnectionId, setActiveConnectionId] = useState<string | null>(null)
  const [dbSchema, setDbSchema] = useState<DbSchema | null>(null)

  const [datasets, setDatasets] = useState<DataItem[]>([])
  const [datasetName, setDatasetName] = useState('customer-churn-dataset')
  const [experiments, setExperiments] = useState<DataItem[]>([])
  const [experimentName, setExperimentName] = useState('churn-baseline')
  const [jobs, setJobs] = useState<DataItem[]>([])
  const [jobName, setJobName] = useState('llm-finetune-job')

  async function apiGet<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`)
    if (!res.ok) throw new Error(await res.text())
    return (await res.json()) as T
  }

  async function apiPost<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    return (await res.json()) as T
  }

  async function apiPut<T>(path: string, body: unknown): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) throw new Error(await res.text())
    return (await res.json()) as T
  }

  async function refreshNotebooks() {
    setError(null)
    setStatus('loading notebooks…')
    try {
      const items = await apiGet<Notebook[]>('/notebooks')
      setNotebooks(items)
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function createNotebook() {
    setError(null)
    setStatus('creating notebook…')
    try {
      const nb = await apiPost<Notebook>('/notebooks', { title: 'New notebook' })
      setActiveNotebook(nb)
      await refreshNotebooks()
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function openNotebook(id: string) {
    setError(null)
    setStatus('opening notebook…')
    try {
      const nb = await apiGet<Notebook>(`/notebooks/${id}`)
      setActiveNotebook(nb)
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function saveNotebook() {
    if (!activeNotebook) return
    setError(null)
    setStatus('saving notebook…')
    try {
      const nb = await apiPut<Notebook>(`/notebooks/${activeNotebook.id}`, {
        title: activeNotebook.title,
        cells: activeNotebook.cells,
      })
      setActiveNotebook(nb)
      await refreshNotebooks()
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function addCell(language: NotebookCell['language']) {
    if (!activeNotebook) return
    setError(null)
    setStatus('adding cell…')
    try {
      const { id } = await apiPost<{ id: string }>('/ids/new', {})
      const cell: NotebookCell = { id, language, content: '' }
      setActiveNotebook({ ...activeNotebook, cells: [...activeNotebook.cells, cell] })
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  function updateCell(cellId: string, patch: Partial<NotebookCell>) {
    if (!activeNotebook) return
    const cells = activeNotebook.cells.map((c) => (c.id === cellId ? { ...c, ...patch } : c))
    setActiveNotebook({ ...activeNotebook, cells })
  }

  function deleteCell(cellId: string) {
    if (!activeNotebook) return
    const cells = activeNotebook.cells.filter((c) => c.id !== cellId)
    setActiveNotebook({ ...activeNotebook, cells })
    setCellOutputs((prev) => {
      const next = { ...prev }
      delete next[cellId]
      return next
    })
  }

  async function runCell(cell: NotebookCell) {
    setError(null)
    setStatus(`running ${cell.language}…`)
    try {
      if (cell.language === 'sql') {
        const out = await apiPost<SqlQueryResponse>('/sql/query', { query: cell.content })
        setCellOutputs((prev) => ({ ...prev, [cell.id]: { kind: 'sql', value: out } }))
      } else if (cell.language === 'python' || cell.language === 'r') {
        const out = await apiPost<KernelExecuteResponse>('/kernels/execute', {
          language: cell.language,
          code: cell.content,
          timeout_s: 60,
        })
        setCellOutputs((prev) => ({ ...prev, [cell.id]: { kind: 'kernel', value: out } }))
      } else {
        setCellOutputs((prev) => ({
          ...prev,
          [cell.id]: { kind: 'text', value: cell.content },
        }))
      }
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function runSql() {
    setError(null)
    setStatus('running SQL…')
    try {
      const out = await apiPost<SqlQueryResponse>('/sql/query', { query: sql })
      setSqlResult(out)
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function sendChat() {
    setError(null)
    setStatus('assistant thinking…')

    const nextLog = [...chatLog, { role: 'user' as const, content: chatInput }]
    setChatLog(nextLog)
    setChatInput('')

    try {
      const out = await apiPost<{ message: { role: 'assistant'; content: string } }>(
        '/assistant/chat',
        { messages: nextLog }
      )
      setChatLog([...nextLog, out.message])
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function refreshDbConnections() {
    const items = await apiGet<DbConnection[]>('/db/connections')
    setDbConnections(items)
  }

  async function connectDatabase() {
    setError(null)
    setStatus('connecting database…')
    try {
      const c = await apiPost<DbConnection>('/db/connect', { kind: dbKind, url: dbUrl })
      setActiveConnectionId(c.id)
      await refreshDbConnections()
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function loadSchema(connectionId: string) {
    setError(null)
    setStatus('loading schema…')
    try {
      const schema = await apiGet<DbSchema>(`/db/${connectionId}/schema`)
      setDbSchema(schema)
      setStatus('ready')
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function refreshDataOps() {
    const [ds, ex, tj] = await Promise.all([
      apiGet<DataItem[]>('/datasets'),
      apiGet<DataItem[]>('/experiments'),
      apiGet<DataItem[]>('/training/jobs'),
    ])
    setDatasets(ds)
    setExperiments(ex)
    setJobs(tj)
  }

  async function createDataset() {
    await apiPost('/datasets', { name: datasetName, source_type: 'upload' })
    await refreshDataOps()
  }

  async function createExperiment() {
    await apiPost('/experiments', { name: experimentName, status: 'created' })
    await refreshDataOps()
  }

  async function createTrainingJob() {
    await apiPost('/training/jobs', { name: jobName, kind: 'llm-finetune', status: 'queued' })
    await refreshDataOps()
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="logo">C</div>
          <div>
            <div className="title">Changy</div>
            <div className="subtitle">Mini all-in-one data IDE (MVP)</div>
          </div>
        </div>
        <div className="status">
          <span className="pill">{status}</span>
          <button className="btn" onClick={refreshNotebooks}>
            Refresh
          </button>
        </div>
      </header>

      {error ? (
        <div className="error">
          <div className="errorTitle">Backend error</div>
          <pre className="errorBody">{error}</pre>
          <div className="hint">
            Make sure the backend is running on <code>localhost:8000</code>.
          </div>
        </div>
      ) : null}

      <div className="grid">
        <aside className="panel">
          <div className="panelHeader">
            <div className="panelTitle">Notebooks</div>
            <button className="btn primary" onClick={createNotebook}>
              New
            </button>
          </div>
          <div className="panelBody">
            {notebooks.length === 0 ? (
              <div className="muted">No notebooks yet. Click “New”.</div>
            ) : (
              <ul className="list">
                {notebooks.map((nb) => (
                  <li key={nb.id}>
                    <button
                      className={
                        activeNotebook?.id === nb.id ? 'listItem active' : 'listItem'
                      }
                      onClick={() => openNotebook(nb.id)}
                    >
                      <div className="listItemTitle">{nb.title}</div>
                      <div className="listItemMeta">{nb.id.slice(0, 8)}</div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="panel">
          <div className="panelHeader">
            <div className="panelTitle">Notebook editor</div>
            <button className="btn" disabled={!activeNotebook} onClick={saveNotebook}>
              Save
            </button>
          </div>
          <div className="panelBody">
            {!activeNotebook ? (
              <div className="muted">Select a notebook or create a new one.</div>
            ) : (
              <div className="editor">
                <label className="label">
                  Title
                  <input
                    className="input"
                    value={activeNotebook.title}
                    onChange={(e) =>
                      setActiveNotebook({ ...activeNotebook, title: e.target.value })
                    }
                  />
                </label>

                <div className="row">
                  <button className="btn primary" onClick={() => addCell('python')}>
                    + Python cell
                  </button>
                  <button className="btn primary" onClick={() => addCell('r')}>
                    + R cell
                  </button>
                  <button className="btn primary" onClick={() => addCell('sql')}>
                    + SQL cell
                  </button>
                  <button className="btn" onClick={() => addCell('markdown')}>
                    + Markdown
                  </button>
                </div>

                <div className="cells">
                  {activeNotebook.cells.map((cell, idx) => {
                    const out = cellOutputs[cell.id]
                    return (
                      <div className="cell" key={cell.id}>
                        <div className="cellHeader">
                          <div className="cellTitle">
                            Cell {idx + 1}
                            <span className="cellMeta">{cell.language}</span>
                          </div>
                          <div className="row">
                            <select
                              className="select"
                              value={cell.language}
                              onChange={(e) =>
                                updateCell(cell.id, {
                                  language: e.target.value as NotebookCell['language'],
                                })
                              }
                            >
                              <option value="python">python</option>
                              <option value="r">r</option>
                              <option value="sql">sql</option>
                              <option value="markdown">markdown</option>
                            </select>
                            <button className="btn primary" onClick={() => runCell(cell)}>
                              Run
                            </button>
                            <button className="btn" onClick={() => deleteCell(cell.id)}>
                              Delete
                            </button>
                          </div>
                        </div>
                        <textarea
                          className="textarea"
                          value={cell.content}
                          onChange={(e) => updateCell(cell.id, { content: e.target.value })}
                          placeholder={
                            cell.language === 'sql'
                              ? 'select 1;'
                              : cell.language === 'python'
                                ? 'print("hello")'
                                : cell.language === 'r'
                                  ? 'print("hello")'
                                  : '# markdown...'
                          }
                        />

                        {out ? (
                          <div className="output">
                            {out.kind === 'sql' ? (
                              <div className="tableWrap">
                                <table className="table">
                                  <thead>
                                    <tr>
                                      {out.value.columns.map((c) => (
                                        <th key={c}>{c}</th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {out.value.rows.map((r, i) => (
                                      <tr key={i}>
                                        {r.map((v, j) => (
                                          <td key={j}>{String(v)}</td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            ) : out.kind === 'kernel' ? (
                              <div className="kernelOut">
                                <div className="muted">status: {out.value.status}</div>
                                {out.value.stdout ? (
                                  <pre className="chatContent">{out.value.stdout}</pre>
                                ) : null}
                                {out.value.stderr ? (
                                  <pre className="chatContent">{out.value.stderr}</pre>
                                ) : null}
                                {out.value.result !== undefined ? (
                                  <pre className="chatContent">
                                    {typeof out.value.result === 'string'
                                      ? out.value.result
                                      : JSON.stringify(out.value.result, null, 2)}
                                  </pre>
                                ) : null}
                              </div>
                            ) : (
                              <pre className="chatContent">{out.value}</pre>
                            )}
                          </div>
                        ) : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </main>

        <section className="panel">
          <div className="panelHeader">
            <div className="panelTitle">SQL runner (DuckDB)</div>
            <button className="btn primary" onClick={runSql}>
              Run
            </button>
          </div>
          <div className="panelBody">
            <textarea className="textarea" value={sql} onChange={(e) => setSql(e.target.value)} />

            {sqlResult ? (
              <div className="tableWrap">
                <table className="table">
                  <thead>
                    <tr>
                      {sqlResult.columns.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sqlResult.rows.map((r, i) => (
                      <tr key={i}>
                        {r.map((cell, j) => (
                          <td key={j}>{String(cell)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="muted">Run a query to see results.</div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div className="panelTitle">Assistant (LLM + tools)</div>
          </div>
          <div className="panelBody">
            <div className="chatLog">
              {chatLog.length === 0 ? (
                <div className="muted">
                  Ask something about Python, R, or SQL. This is currently a stub.
                </div>
              ) : (
                chatLog.map((m, idx) => (
                  <div key={idx} className={m.role === 'user' ? 'chatMsg user' : 'chatMsg assistant'}>
                    <div className="chatRole">{m.role}</div>
                    <pre className="chatContent">{m.content}</pre>
                  </div>
                ))
              )}
            </div>
            <div className="chatInputRow">
              <textarea
                className="textarea"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                placeholder="Ask the assistant…"
              />
              <button className="btn primary" onClick={sendChat}>
                Send
              </button>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div className="panelTitle">DB connectors + schema browser</div>
            <button className="btn" onClick={refreshDbConnections}>
              Refresh connections
            </button>
          </div>
          <div className="panelBody">
            <div className="row">
              <select className="select" value={dbKind} onChange={(e) => setDbKind(e.target.value as 'postgres' | 'mysql' | 'snowflake')}>
                <option value="postgres">postgres</option>
                <option value="mysql">mysql</option>
                <option value="snowflake">snowflake</option>
              </select>
              <input className="input" value={dbUrl} onChange={(e) => setDbUrl(e.target.value)} />
              <button className="btn primary" onClick={connectDatabase}>
                Connect
              </button>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              {dbConnections.map((c) => (
                <button
                  key={c.id}
                  className={activeConnectionId === c.id ? 'btn primary' : 'btn'}
                  onClick={() => {
                    setActiveConnectionId(c.id)
                    void loadSchema(c.id)
                  }}
                >
                  {c.kind}:{c.id.slice(0, 8)}
                </button>
              ))}
            </div>
            {dbSchema ? (
              <div className="tableWrap" style={{ marginTop: 10 }}>
                <table className="table">
                  <thead>
                    <tr>
                      <th>schema</th>
                      <th>table</th>
                      <th>columns</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dbSchema.tables.map((t, i) => (
                      <tr key={`${t.name}-${i}`}>
                        <td>{t.schema ?? 'default'}</td>
                        <td>{t.name}</td>
                        <td>{t.columns.map((c) => `${c.name}:${c.type}`).join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="muted" style={{ marginTop: 10 }}>
                Connect and select a database to inspect schema.
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div className="panelTitle">Datasets, experiments, training orchestration</div>
            <button className="btn" onClick={refreshDataOps}>
              Refresh
            </button>
          </div>
          <div className="panelBody">
            <div className="row">
              <input className="input" value={datasetName} onChange={(e) => setDatasetName(e.target.value)} />
              <button className="btn primary" onClick={createDataset}>
                Add dataset
              </button>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <input className="input" value={experimentName} onChange={(e) => setExperimentName(e.target.value)} />
              <button className="btn primary" onClick={createExperiment}>
                Add experiment
              </button>
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <input className="input" value={jobName} onChange={(e) => setJobName(e.target.value)} />
              <button className="btn primary" onClick={createTrainingJob}>
                Queue training job
              </button>
            </div>

            <div className="grid3">
              <div>
                <div className="panelTitle" style={{ marginTop: 12 }}>Datasets</div>
                <ul className="list">
                  {datasets.map((d) => (
                    <li key={d.id} className="muted">{d.name}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="panelTitle" style={{ marginTop: 12 }}>Experiments</div>
                <ul className="list">
                  {experiments.map((d) => (
                    <li key={d.id} className="muted">{d.name}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="panelTitle" style={{ marginTop: 12 }}>Training jobs</div>
                <ul className="list">
                  {jobs.map((d) => (
                    <li key={d.id} className="muted">{d.name}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

export default App
