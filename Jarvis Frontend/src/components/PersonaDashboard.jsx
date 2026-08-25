import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowLeft, BarChart3, BrainCircuit, Check, ChevronRight, CircleGauge, Clock3, Eye, EyeOff,
  Fingerprint, FileUp, FlaskConical, LoaderCircle, LockKeyhole, MessageSquareText, Network, Target,
  RefreshCw, Save, ShieldCheck, Sparkles, Trash2, Users,
} from 'lucide-react'
import './PersonaDashboard.css'

const tabs = [
  ['overview', 'Overview'],
  ['signals', 'Signals'],
  ['controls', 'Controls'],
  ['evidence', 'Evidence'],
]

const controlMeta = {
  mirror_complement: ['Agent alignment', 'Mirror me', 'Complement me'],
  concise_detailed: ['Response depth', 'Concise', 'Detailed'],
  direct_diplomatic: ['Delivery', 'Direct', 'Diplomatic'],
  analytical_creative: ['Reasoning', 'Analytical', 'Creative'],
  cautious_bold: ['Decision energy', 'Cautious', 'Bold'],
  supportive_challenging: ['Empathy mode', 'Supportive', 'Challenging'],
  structured_exploratory: ['Working mode', 'Structured', 'Exploratory'],
}

const activeStatuses = new Set(['queued', 'collecting', 'analyzing', 'generating_image'])

function formatDate(value) {
  if (!value) return 'Not generated yet'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Recently'
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

function levelLabel(level = '') {
  return ({
    not_ready: 'Building signal',
    early_signal: 'Early signal',
    emerging: 'Emerging persona',
    calibrated: 'Calibrated twin',
    adaptive: 'Adaptive twin',
  })[level] || 'Not measured'
}

function PersonaOrb({ imageUrl, name = 'Your digital twin' }) {
  return (
    <div className={`persona-orb ${imageUrl ? 'has-image' : ''}`} aria-label={imageUrl ? `${name} symbolic persona artwork` : 'Abstract persona visualization'}>
      {imageUrl ? <img src={imageUrl} alt={`${name} — abstract symbolic AI artwork`} /> : <><span /><i /><b><Fingerprint size={54} /></b></>}
    </div>
  )
}

function ReadinessPanel({ readiness, compact = false }) {
  const score = Number(readiness?.score || 0)
  return (
    <section className={`persona-readiness-card ${compact ? 'compact' : ''}`}>
      <div className="persona-score-ring" style={{ '--persona-score': `${score * 3.6}deg` }}>
        <div><strong>{score}</strong><small>/ 100</small></div>
      </div>
      <div className="persona-readiness-copy">
        <span className="persona-eyebrow"><CircleGauge size={14} /> Evidence readiness</span>
        <h2>{levelLabel(readiness?.level)}</h2>
        <p>{readiness?.eligible
          ? 'Enough evidence exists for a useful snapshot. More interaction will improve confidence and unlock deeper modules.'
          : 'Nexa will not invent a persona from weak evidence. Keep interacting naturally and refresh when you are ready.'}</p>
        <div className="persona-requirements">
          {(readiness?.requirements || []).map((item) => (
            <div key={item.key} className={item.met ? 'met' : ''}>
              <span>{item.met ? <Check size={14} /> : <LockKeyhole size={13} />}{item.label}</span>
              <strong>{Number(item.current || 0).toLocaleString()} / {Number(item.target || 0).toLocaleString()}</strong>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function ProcessingBanner({ run, onRefresh, refreshing }) {
  if (!run || !activeStatuses.has(run.status)) return null
  return (
    <div className="persona-processing" role="status">
      <LoaderCircle size={18} className="persona-spin" />
      <div><strong>{run.message || 'Persona analysis is running in the background.'}</strong><small>You can leave this page. Progress is stored safely in your account.</small></div>
      <span>{run.progress || 0}%</span>
      <button type="button" onClick={onRefresh} disabled={refreshing} aria-label="Refresh persona status"><RefreshCw size={15} /></button>
    </div>
  )
}

function ChatProfileDetail({ analysis }) {
  const ai = analysis.ai || {}
  return (
    <div className="persona-chat-detail">
      <div className="persona-chat-detail-note">AI-analyzed context profile · This reflects this conversation only, not your universal persona.</div>
      <div className="persona-chat-hero"><div><span className="persona-eyebrow"><Sparkles size={13} /> {ai.status === 'fallback' ? 'Evidence profile' : 'AI conversation profile'}</span><h2>{ai.persona_name || 'Conversation profile'}</h2><strong>{ai.tagline || 'A context-specific communication pattern'}</strong><p>{ai.summary}</p></div><div className="persona-chat-signature"><small>Signature style</small><span>{ai.signature_style || 'Contextual and relationship-shaped.'}</span></div></div>
      <div className="persona-chat-metrics">
        <div><strong>{Number(analysis.message_count || 0).toLocaleString()}</strong><span>messages</span></div>
        <div><strong>{Number(analysis.word_count || 0).toLocaleString()}</strong><span>words</span></div>
        <div><strong>{analysis.average_message_words || 0}</strong><span>words / message</span></div>
        <div><strong>{analysis.participant_count || 0}</strong><span>participants</span></div>
      </div>
      <div className="persona-chat-detail-grid">
        <section><h4>Communication dimensions</h4>{(analysis.dimensions || []).map((item) => <div className="persona-chat-dimension" key={item.key}><div><span>{item.label}</span><small>{item.low_label} · {item.high_label}</small></div><div className="persona-dimension-track"><i style={{ width: `${item.score}%` }} /></div><strong>{item.score}</strong></div>)}<h4 className="persona-detail-subhead">Archetypes</h4>{(ai.archetypes || []).map((item) => <div className="persona-chat-observation" key={item.name}><strong>{item.name}</strong><p>{item.description}</p></div>)}</section>
        <section><h4>Conversation topics</h4><div className="persona-topic-cloud">{(analysis.topics || []).map((item) => <span key={item.name} style={{ '--topic-score': item.score }}>{item.name}<small>{item.score}</small></span>)}</div><h4 className="persona-detail-subhead">Observed patterns</h4>{(analysis.observations || []).map((item) => <div className="persona-chat-observation" key={item.title}><strong>{item.title}</strong><p>{item.description}</p></div>)}</section>
      </div>
      <div className="persona-chat-ai-columns"><section><h4>Strength signals</h4><ul>{(ai.strengths || []).map((item) => <li key={item}>{item}</li>)}</ul></section><section><h4>How to work with me here</h4><ul>{(ai.how_to_work_with_me || []).map((item) => <li key={item}>{item}</li>)}</ul></section>{ai.decision_patterns?.length > 0 && <section><h4>Decision patterns</h4><ul>{ai.decision_patterns.map((item) => <li key={item}>{item}</li>)}</ul></section>}</div>
      <div className="persona-chat-hours"><h4>Most active hours</h4>{(analysis.active_hours || []).map((item) => <span key={item.hour}>{String(item.hour).padStart(2, '0')}:00 <small>{item.count}</small></span>)}</div>
    </div>
  )
}

// Kept temporarily for compatibility with old hot-reloaded component state.
// eslint-disable-next-line no-unused-vars
function LegacyImportedChatPanel({ imports, busy, onUpload, onToggle, onDelete }) {
  const [expandedImportId, setExpandedImportId] = useState(null)
  return (
    <section className="persona-panel persona-imports">
      <div className="persona-panel-title"><MessageSquareText size={18} /><div><span>Conversation profiles</span><small>Each chat gets its own context. Nothing joins your merged persona without approval.</small></div></div>
      <label className="persona-upload"><FileUp size={18} /><span>{busy ? 'Parsing and analyzing conversation…' : 'Upload WhatsApp or Telegram export'}<small>WhatsApp .zip/.txt or Telegram .json · media files are ignored</small></span><input type="file" accept=".zip,.txt,.json,application/zip,text/plain,application/json" onChange={onUpload} disabled={busy} /></label>
      {!imports.length && <div className="persona-import-empty">No imported conversations yet.</div>}
      <div className="persona-import-list">
        {imports.map((item) => {
          const analysis = item.analysis || {}
          const expanded = expandedImportId === item.id
          return <article key={item.id} className={expanded ? 'expanded' : ''} onClick={() => setExpandedImportId(expanded ? null : item.id)} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setExpandedImportId(expanded ? null : item.id) }}>
            <div><strong>{analysis.name || item.filename}</strong><small>{analysis.format} · {Number(analysis.message_count || 0).toLocaleString()} messages · {Number(analysis.word_count || 0).toLocaleString()} words</small></div>
            <div className="persona-import-actions"><label onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={Boolean(item.include_in_merged)} onChange={(event) => onToggle(item, event.target.checked)} /> Include in merged persona</label><button type="button" onClick={(event) => { event.stopPropagation(); onDelete(item) }} title="Delete imported chat"><Trash2 size={15} /></button></div>
            <div className="persona-import-signals">{(analysis.observations || []).slice(0, 3).map((signal) => <span key={signal.title}>{signal.title}</span>)}</div>
            {expanded && <ChatProfileDetail analysis={analysis} />}
          </article>
        })}
      </div>
    </section>
  )
}

function LocalSignalBar({ label, value, detail = '' }) {
  return <div className="local-signal-bar"><div><span>{label}</span><strong>{value || 0}%</strong></div><div><i style={{ width: `${Math.max(0, Math.min(100, value || 0))}%` }} /></div>{detail && <small>{detail}</small>}</div>
}

function LocalDashboardBand({ icon, title, subtitle, children }) {
  return <section className="local-dashboard-band"><header>{icon}<strong>{title}</strong><small>{subtitle}</small><i /></header><div className="local-dashboard-grid">{children}</div></section>
}

function LocalActivityHeatmap({ rows = [] }) {
  const maximum = Math.max(1, ...rows.flatMap((row) => row.hours || []))
  return <div className="local-heatmap">{rows.map((row) => <div key={row.day}><span>{row.day}</span><div>{(row.hours || []).map((count, hour) => <i key={hour} title={`${row.day} ${String(hour).padStart(2, '0')}:00 · ${count} messages`} style={{ opacity: 0.12 + (count / maximum) * 0.88 }} />)}</div></div>)}<footer><span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>23h</span></footer></div>
}

function LocalChatDashboard({ analysis }) {
  const behavior = analysis.behavior || {}
  const tone = behavior.tone || {}
  const attention = behavior.attention || {}
  const decision = behavior.decision_style || {}
  const profile = analysis.profile || {}
  return <div className="persona-local-dashboard">
    <header className="local-dashboard-head">
      <div><span className="persona-eyebrow"><Fingerprint size={13} /> Local behavioral analysis</span><h2>{analysis.name || 'Conversation dashboard'}</h2><p>{profile.summary || 'Re-upload this conversation to generate the expanded local analytics.'}</p></div>
      <div className="local-dashboard-stats"><div><small>Messages</small><strong>{Number(analysis.message_count || 0).toLocaleString()}</strong></div><div><small>Words</small><strong>{Number(analysis.word_count || 0).toLocaleString()}</strong></div><div><small>Median reply</small><strong>{behavior.median_reply_minutes == null ? '—' : `${behavior.median_reply_minutes}m`}</strong></div><div><small>Method</small><strong>Local only</strong></div></div>
    </header>

    <LocalDashboardBand icon={<CircleGauge size={17} />} title="Communication profile" subtitle="message structure and language markers">
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Behavior dimensions</strong><small>{analysis.message_count || 0} messages</small></div>{(analysis.dimensions || []).map((item) => <LocalSignalBar key={item.key} label={item.label} value={item.score} detail={`${item.low_label} ↔ ${item.high_label}`} />)}</article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Tone markers</strong><small>dictionary based</small></div><LocalSignalBar label="Positive language" value={tone.positive} /><LocalSignalBar label="Curiosity" value={tone.curiosity} /><LocalSignalBar label="Supportive language" value={tone.supportive_language} /><LocalSignalBar label="Negative language" value={tone.negative} /></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Participant balance</strong><small>{analysis.participant_count || 0} participants</small></div><div className="local-participants">{(analysis.participants || []).map((item) => <div key={item.name}><span>{item.name}</span><div><i style={{ width: `${item.share}%` }} /></div><strong>{item.share}%</strong><small>{Number(item.messages).toLocaleString()} msgs</small></div>)}</div></article>
    </LocalDashboardBand>

    <LocalDashboardBand icon={<Network size={17} />} title="Knowledge and context" subtitle="topics, preferences, and explicit plans">
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Topic network</strong><small>{analysis.topic_graph?.nodes?.length || 0} clusters</small></div><div className="local-topic-nodes">{(analysis.topic_graph?.nodes || []).map((node) => <span key={node.id} style={{ '--weight': node.weight }}>{node.label}<small>{node.weight}</small></span>)}</div><div className="local-topic-edges">{(analysis.topic_graph?.edges || []).slice(0, 6).map((edge) => <span key={`${edge.source}-${edge.target}`}>{edge.source} <i>↔</i> {edge.target}<small>{edge.weight}</small></span>)}</div></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Preference-like statements</strong><small>explicit wording only</small></div><div className="local-statement-list">{(analysis.preference_statements || []).map((item, index) => <blockquote key={`${item.author}-${index}`}><p>{item.text}</p><small>{item.author}</small></blockquote>)}{!analysis.preference_statements?.length && <p className="local-empty">No explicit preference phrases detected.</p>}</div></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Goals and action language</strong><small>not inferred</small></div><div className="local-statement-list">{(analysis.goal_statements || []).map((item, index) => <blockquote key={`${item.author}-${index}`}><p>{item.text}</p><small>{item.author}</small></blockquote>)}{!analysis.goal_statements?.length && <p className="local-empty">No explicit goal phrases detected.</p>}</div></article>
    </LocalDashboardBand>

    <LocalDashboardBand icon={<Activity size={17} />} title="Behavioral patterns" subtitle="timing, attention, and decision language">
      <article className="local-dashboard-panel local-wide"><div className="local-panel-title"><strong>Interaction heatmap</strong><small>day × hour</small></div><LocalActivityHeatmap rows={behavior.heatmap || []} /></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Decision language</strong><small>{decision.reasoning_markers || 0} reasoning markers</small></div><LocalSignalBar label="Evidence-led" value={decision.evidence_led} /><LocalSignalBar label="Exploratory" value={decision.exploratory} /><div className="local-kpi"><small>Planning markers</small><strong>{decision.planning_markers || 0}</strong></div></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Attention and engagement</strong><small>message-length signals</small></div><LocalSignalBar label="Deep messages" value={attention.deep_messages} /><LocalSignalBar label="Quick messages" value={attention.quick_messages} /><LocalSignalBar label="Question-led" value={attention.question_led} /></article>
      <article className="local-dashboard-panel"><div className="local-panel-title"><strong>Conversation rhythm</strong><small>{behavior.reply_samples || 0} reply transitions</small></div><div className="local-rhythm"><div><Clock3 size={16} /><span>Median reply time</span><strong>{behavior.median_reply_minutes == null ? 'Not enough data' : `${behavior.median_reply_minutes} min`}</strong></div>{(behavior.initiations || []).map((item) => <div key={item.author}><Target size={16} /><span>{item.author}</span><strong>{item.count} starts</strong></div>)}</div></article>
    </LocalDashboardBand>

    <section className="local-method"><BarChart3 size={18} /><div><strong>How this dashboard is built</strong><p>{profile.method || 'Deterministic analysis only. No LLM, paid API, diagnosis, or hidden personality inference.'}</p></div></section>
  </div>
}

function ImportedChatPanel({ imports, busy, onUpload, onToggle, onDelete }) {
  const [selectedImportId, setSelectedImportId] = useState(null)
  const selected = imports.find((item) => item.id === selectedImportId)
  if (selected) return <LocalChatDashboard analysis={selected.analysis || {}} onBack={() => setSelectedImportId(null)} />
  return <section className="persona-panel persona-imports">
    <div className="persona-panel-title"><MessageSquareText size={18} /><div><span>Conversation profiles</span><small>Each chat stays contextual. Nothing joins the merged profile without approval.</small></div></div>
    <label className="persona-upload"><FileUp size={18} /><span>{busy ? 'Computing local conversation signals…' : 'Upload WhatsApp or Telegram export'}<small>WhatsApp .zip/.txt or Telegram .json · no LLM or paid API</small></span><input type="file" accept=".zip,.txt,.json,application/zip,text/plain,application/json" onChange={onUpload} disabled={busy} /></label>
    {!imports.length && <div className="persona-import-empty">No imported conversations yet.</div>}
    <div className="persona-import-list">{imports.map((item) => { const analysis = item.analysis || {}; return <article key={item.id} onClick={() => setSelectedImportId(item.id)} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') setSelectedImportId(item.id) }}><div><strong>{analysis.name || item.filename}</strong><small>{analysis.format} · {Number(analysis.message_count || 0).toLocaleString()} messages · {Number(analysis.word_count || 0).toLocaleString()} words</small></div><div className="persona-import-actions"><label onClick={(event) => event.stopPropagation()}><input type="checkbox" checked={Boolean(item.include_in_merged)} onChange={(event) => onToggle(item, event.target.checked)} /> Include in merged profile</label><button type="button" onClick={(event) => { event.stopPropagation(); onDelete(item) }} title="Delete imported chat"><Trash2 size={15} /></button></div><div className="persona-import-signals">{(analysis.observations || []).slice(0, 3).map((signal) => <span key={signal.title}>{signal.title}</span>)}</div></article> })}</div>
  </section>
}

export default function PersonaDashboard({ apiBase, fetchApi, user, onBack, onRequireAuth }) {
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(Boolean(user))
  const [refreshing, setRefreshing] = useState(false)
  const [runBusy, setRunBusy] = useState(false)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('overview')
  const [imageUrl, setImageUrl] = useState('')
  const [controls, setControls] = useState({})
  const [controlsBusy, setControlsBusy] = useState(false)
  const [scenario, setScenario] = useState('')
  const [simulation, setSimulation] = useState(null)
  const [simulationBusy, setSimulationBusy] = useState(false)
  const [editingObservation, setEditingObservation] = useState(null)
  const [importBusy, setImportBusy] = useState(false)

  const loadDashboard = useCallback(async ({ quiet = false } = {}) => {
    if (!user) return
    if (quiet) setRefreshing(true)
    else setLoading(true)
    try {
      const response = await fetchApi(`${apiBase}/api/persona`, { credentials: 'include' })
      const data = await response.json()
      if (response.status === 401) {
        onRequireAuth()
        return
      }
      if (!response.ok) throw new Error(data.detail || 'Could not load your persona.')
      setDashboard(data)
      setControls(data.profile?.controls || {})
      if (!data.profile?.has_image) setImageUrl('')
      setError('')
    } catch (requestError) {
      setError(requestError.message || 'Could not load your persona.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [apiBase, fetchApi, onRequireAuth, user])

  const uploadChat = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setImportBusy(true)
    try {
      const body = new FormData()
      body.append('file', file)
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports`, { method: 'POST', credentials: 'include', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not read that chat export.')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) } finally { setImportBusy(false) }
  }

  const toggleChatImport = async (item, include) => {
    try {
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports/${encodeURIComponent(item.id)}`, { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ include_in_merged: include }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not update the merged persona source.')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) }
  }

  const deleteChatImport = async (item) => {
    if (!window.confirm(`Delete ${item.filename || 'this imported conversation'}?`)) return
    try {
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'include' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not delete this import.')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => loadDashboard(), 0)
    return () => window.clearTimeout(timer)
  }, [loadDashboard])

  useEffect(() => {
    if (!user || !dashboard?.is_processing) return undefined
    const timer = window.setTimeout(() => loadDashboard({ quiet: true }), 8000)
    return () => window.clearTimeout(timer)
  }, [dashboard?.is_processing, dashboard?.run?.progress, loadDashboard, user])

  useEffect(() => {
    if (!user) return undefined
    const refreshOnFocus = () => loadDashboard({ quiet: true })
    window.addEventListener('focus', refreshOnFocus)
    return () => window.removeEventListener('focus', refreshOnFocus)
  }, [loadDashboard, user])

  useEffect(() => {
    let objectUrl = ''
    let disposed = false
    if (!user || !dashboard?.profile?.has_image) return undefined
    fetchApi(`${apiBase}/api/persona/image`, { credentials: 'include' })
      .then((response) => response.ok ? response.blob() : null)
      .then((blob) => {
        if (!blob || disposed) return
        objectUrl = URL.createObjectURL(blob)
        setImageUrl(objectUrl)
      })
      .catch(() => setImageUrl(''))
    return () => {
      disposed = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [apiBase, dashboard?.profile?.has_image, dashboard?.profile?.run_id, fetchApi, user])

  const startRun = async () => {
    if (!user) return onRequireAuth()
    if (runBusy || dashboard?.is_processing) return
    setRunBusy(true)
    setError('')
    try {
      const response = await fetchApi(`${apiBase}/api/persona/runs`, { method: 'POST', credentials: 'include' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not start persona analysis.')
      setDashboard((current) => ({ ...(current || {}), run: data.run, is_processing: true }))
    } catch (requestError) {
      setError(requestError.message || 'Could not start persona analysis.')
    } finally {
      setRunBusy(false)
    }
  }

  const mutate = async (path, options, fallback) => {
    setError('')
    const response = await fetchApi(`${apiBase}${path}`, { credentials: 'include', ...options })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || fallback)
    await loadDashboard({ quiet: true })
    return data
  }

  const saveControls = async () => {
    setControlsBusy(true)
    try {
      await mutate('/api/persona/controls', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(controls),
      }, 'Could not save persona controls.')
    } catch (requestError) { setError(requestError.message) } finally { setControlsBusy(false) }
  }

  const changeObservation = async (observation, updates, remove = false) => {
    try {
      await mutate(`/api/persona/observations/${encodeURIComponent(observation.id)}`, remove ? { method: 'DELETE' } : {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updates),
      }, 'Could not update this observation.')
      setEditingObservation(null)
    } catch (requestError) { setError(requestError.message) }
  }

  const removeSource = async (messageId) => {
    try {
      await mutate(`/api/persona/sources/${encodeURIComponent(messageId)}`, { method: 'DELETE' }, 'Could not remove this source.')
    } catch (requestError) { setError(requestError.message) }
  }

  const runSimulation = async (event) => {
    event.preventDefault()
    if (!scenario.trim() || simulationBusy) return
    setSimulationBusy(true)
    setSimulation(null)
    try {
      const response = await fetchApi(`${apiBase}/api/persona/simulations`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'include', body: JSON.stringify({ scenario: scenario.trim() }),
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not run this simulation.')
      setSimulation(data.simulation)
    } catch (requestError) { setError(requestError.message) } finally { setSimulationBusy(false) }
  }

  const removePersona = async () => {
    if (!window.confirm('Delete your generated persona, controls, image, and simulations? Your chat messages will remain unchanged.')) return
    try {
      await mutate('/api/persona', { method: 'DELETE' }, 'Could not delete your persona.')
      setDashboard(null)
      setImageUrl('')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) }
  }

  const profile = dashboard?.profile
  const readiness = profile?.readiness || dashboard?.run?.readiness
  const modules = readiness?.modules || {}
  const enabledObservations = useMemo(() => (profile?.observations || []).filter((item) => item.enabled !== false), [profile?.observations])

  if (!user) {
    return (
      <section className="persona-page persona-auth-state">
        <div><ShieldCheck size={40} /><span className="persona-eyebrow">Private digital twin</span><h1>Sign in to see your persona</h1><p>This dashboard is private and is never shared with room participants.</p><button type="button" onClick={onRequireAuth}>Sign in</button></div>
      </section>
    )
  }

  if (loading && !dashboard) {
    return <section className="persona-page persona-loading"><LoaderCircle className="persona-spin" size={30} /><p>Opening your private persona workspace…</p></section>
  }

  const runFailed = dashboard?.run?.status === 'failed'
  const insufficient = profile?.status === 'insufficient_data'

  return (
    <section className="persona-page">
      <div className="persona-shell">
        <div className="persona-page-head">
          <button type="button" className="persona-back" onClick={onBack}><ArrowLeft size={17} /> Chats</button>
          <div><span className="persona-eyebrow"><ShieldCheck size={14} /> Only visible to you</span><h1>Your Digital Twin</h1></div>
          <button type="button" className="persona-refresh" onClick={() => loadDashboard({ quiet: true })} disabled={refreshing}><RefreshCw className={refreshing ? 'persona-spin' : ''} size={16} /> Refresh status</button>
        </div>

        {error && <div className="persona-error">{error}</div>}
        <ImportedChatPanel imports={dashboard?.chat_imports || []} busy={importBusy} onUpload={uploadChat} onToggle={toggleChatImport} onDelete={deleteChatImport} />
        <ProcessingBanner run={dashboard?.run} onRefresh={() => loadDashboard({ quiet: true })} refreshing={refreshing} />
        {runFailed && <div className="persona-error"><strong>The last analysis did not finish.</strong> Your previous snapshot was not changed. <button type="button" onClick={startRun}>Try again</button></div>}

        {!profile && !dashboard?.is_processing && (
          <section className="persona-empty">
            <PersonaOrb />
            <span className="persona-eyebrow"><Sparkles size={14} /> Evidence-built, not questionnaire-built</span>
            <h2>Meet the version of you hidden in your conversations.</h2>
            <p>Nexa will privately analyze only messages you authored, identify recurring non-sensitive patterns, and build a dashboard you can inspect and control.</p>
            <button type="button" onClick={startRun} disabled={runBusy}>{runBusy ? <LoaderCircle className="persona-spin" size={17} /> : <BrainCircuit size={17} />} Build my persona</button>
          </section>
        )}

        {!profile && dashboard?.is_processing && (
          <section className="persona-empty persona-waiting"><PersonaOrb /><h2>Your twin is taking shape in the background.</h2><p>You can return to chat or close this page. The completed result will be stored in your private dashboard.</p><button type="button" onClick={onBack}>Return to chats</button></section>
        )}

        {insufficient && (
          <>
            <ReadinessPanel readiness={readiness} />
            <section className="persona-module-grid">
              {Object.entries(modules).map(([key, unlocked]) => <article key={key} className={unlocked ? 'unlocked' : ''}>{unlocked ? <Check size={17} /> : <LockKeyhole size={17} />}<div><strong>{key.replaceAll('_', ' ')}</strong><small>{unlocked ? 'Signal available' : 'Needs more natural interaction'}</small></div></article>)}
            </section>
            <div className="persona-insufficient-action"><p>No KPI or personality claim has been fabricated. Use Nexa naturally, then run `/me` again.</p><button type="button" onClick={startRun} disabled={runBusy || dashboard?.is_processing}><RefreshCw size={16} /> Analyze new interactions</button></div>
          </>
        )}

        {profile?.status === 'completed' && (
          <>
            <section className="persona-hero">
              <PersonaOrb imageUrl={imageUrl} name={profile.persona_name} />
              <div className="persona-hero-copy">
                <span className="persona-eyebrow"><Sparkles size={14} /> {levelLabel(readiness?.level)} · {readiness?.score || 0}% evidence readiness</span>
                <h2>{profile.persona_name}</h2>
                <p className="persona-tagline">{profile.tagline}</p>
                <p>{profile.summary}</p>
                <div className="persona-hero-actions"><button type="button" onClick={startRun} disabled={runBusy || dashboard?.is_processing}><RefreshCw size={16} /> Refresh from new chats</button><small>Updated {formatDate(profile.generated_at)}</small></div>
              </div>
              <div className="persona-hero-stat"><strong>{readiness?.meaningful_messages || 0}</strong><span>meaningful signals</span><i /><strong>{readiness?.conversation_contexts || 0}</strong><span>conversation contexts</span></div>
            </section>

            <nav className="persona-tabs" aria-label="Persona dashboard sections">
              {tabs.map(([key, label]) => <button type="button" key={key} className={activeTab === key ? 'active' : ''} onClick={() => setActiveTab(key)}>{label}</button>)}
            </nav>

            {activeTab === 'overview' && (
              <div className="persona-dashboard-grid">
                <ReadinessPanel readiness={readiness} compact />
                <section className="persona-panel persona-archetypes"><div className="persona-panel-title"><Fingerprint size={18} /><div><span>Current archetypes</span><small>Evidence-based, never fixed labels</small></div></div>{(profile.archetypes || []).map((item) => <article key={item.name}><strong>{item.name}</strong><p>{item.description}</p></article>)}</section>
                <section className="persona-panel persona-strengths"><div className="persona-panel-title"><Sparkles size={18} /><div><span>Strength signals</span><small>Patterns that repeatedly appeared</small></div></div><div>{(profile.strengths || []).map((item) => <span key={item}>{item}</span>)}</div></section>
                <section className="persona-panel persona-work-with"><div className="persona-panel-title"><Users size={18} /><div><span>How to work with me</span><small>Practical interaction guide</small></div></div><ol>{(profile.how_to_work_with_me || []).map((item) => <li key={item}>{item}</li>)}</ol></section>
              </div>
            )}

            {activeTab === 'signals' && (
              <div className="persona-dashboard-grid signals">
                <section className="persona-panel persona-dimensions"><div className="persona-panel-title"><CircleGauge size={18} /><div><span>Behavior dimensions</span><small>Directional signals, not psychological scores</small></div></div>{(profile.dimensions || []).map((item) => <div className="persona-dimension" key={item.key}><div><strong>{item.label}</strong><small>{item.confidence}% confidence</small></div><div className="persona-dimension-track"><i style={{ width: `${item.score}%` }} /></div><div><span>{item.low_label}</span><span>{item.high_label}</span></div></div>)}</section>
                <section className="persona-panel persona-topics"><div className="persona-panel-title"><MessageSquareText size={18} /><div><span>Topic universe</span><small>Where your attention repeatedly goes</small></div></div><div className="persona-topic-cloud">{(profile.topics || []).map((item) => <span key={item.name} style={{ '--topic-score': item.score }}>{item.name}<small>{item.score}</small></span>)}</div></section>
                <section className="persona-panel persona-patterns"><div className="persona-panel-title"><BrainCircuit size={18} /><div><span>Decision patterns</span><small>Unlocked from explicit reasoning examples</small></div></div>{modules.decision_style ? <ul>{(profile.decision_patterns || []).map((item) => <li key={item}>{item}</li>)}</ul> : <div className="persona-locked"><LockKeyhole size={22} /><p>More decisions and trade-offs are needed.</p></div>}</section>
                <section className="persona-panel persona-patterns"><div className="persona-panel-title"><Users size={18} /><div><span>Collaboration roles</span><small>Based on your behavior in shared rooms</small></div></div>{modules.collaboration ? <ul>{(profile.collaboration_roles || []).map((item) => <li key={item}>{item}</li>)}</ul> : <div className="persona-locked"><LockKeyhole size={22} /><p>More shared-room replies are needed.</p></div>}</section>
              </div>
            )}

            {activeTab === 'twin' && (
              <section className="persona-panel persona-twin-lab">
                <div className="persona-panel-title"><FlaskConical size={19} /><div><span>What-if simulator</span><small>A probabilistic projection, never a claim about what you must do</small></div></div>
                {!modules.simulator ? <div className="persona-locked"><LockKeyhole size={28} /><h3>Simulator still calibrating</h3><p>It unlocks after at least 50 meaningful messages, 3 contexts, 3,000 authored words, and 8 decision examples.</p></div> : <form onSubmit={runSimulation}><label htmlFor="persona-scenario">What situation should your twin react to?</label><textarea id="persona-scenario" value={scenario} onChange={(event) => setScenario(event.target.value)} placeholder="Example: I have two product ideas and only one week. Which approach would I likely choose, and why?" /><button type="submit" disabled={simulationBusy || !scenario.trim()}>{simulationBusy ? <LoaderCircle className="persona-spin" size={17} /> : <FlaskConical size={17} />} Simulate my response</button></form>}
                {simulation && <article className="persona-simulation-result"><span>Predicted response · {simulation.confidence}% confidence</span><p>{simulation.predicted_response}</p><details><summary>Why this projection?</summary><p>{simulation.rationale}</p><div>{(simulation.signals_used || []).map((item) => <small key={item}>{item}</small>)}</div></details></article>}
              </section>
            )}

            {activeTab === 'controls' && (
              <div className="persona-controls-grid">
                <section className="persona-panel"><div className="persona-panel-title"><CircleGauge size={18} /><div><span>Empathy & tone controls</span><small>These tune the simulator; normal agent behavior stays unchanged unless you opt in</small></div></div>{Object.entries(controlMeta).map(([key, [label, low, high]]) => <label className="persona-slider" key={key}><div><strong>{label}</strong><span>{controls[key] ?? 50}</span></div><input type="range" min="0" max="100" value={controls[key] ?? 50} onChange={(event) => setControls((current) => ({ ...current, [key]: Number(event.target.value) }))} /><div><small>{low}</small><small>{high}</small></div></label>)}<label className="persona-agent-toggle"><input type="checkbox" checked={Boolean(controls.apply_to_agent)} onChange={(event) => setControls((current) => ({ ...current, apply_to_agent: event.target.checked }))} /><span><strong>Use these controls in regular Nexa chats</strong><small>Off by default. Your source messages remain unchanged.</small></span></label><button className="persona-save" type="button" onClick={saveControls} disabled={controlsBusy}>{controlsBusy ? <LoaderCircle className="persona-spin" size={16} /> : <Save size={16} />} Save controls</button></section>
                <section className="persona-panel persona-privacy"><div className="persona-panel-title"><ShieldCheck size={18} /><div><span>Privacy boundary</span><small>Designed for personal control</small></div></div><ul><li><Check size={15} />Only your authored messages are analyzed</li><li><Check size={15} />Other room members cannot open this dashboard</li><li><Check size={15} />Sensitive traits and physical appearance are not inferred</li><li><Check size={15} />Deleting a persona does not delete chat history</li></ul><button className="persona-danger" type="button" onClick={removePersona}><Trash2 size={16} /> Delete generated persona</button></section>
              </div>
            )}

            {activeTab === 'evidence' && (
              <section className="persona-panel persona-evidence-panel">
                <div className="persona-panel-title"><Eye size={18} /><div><span>Inferences & evidence</span><small>Inspect, disable, edit, or delete what your twin believes</small></div></div>
                {(profile.observations || []).map((observation) => <article key={observation.id} className={observation.enabled === false ? 'disabled' : ''}><div className="persona-observation-head"><span>{observation.category.replaceAll('_', ' ')}</span><strong>{observation.confidence}% confidence</strong><button type="button" onClick={() => changeObservation(observation, { enabled: observation.enabled === false })} title={observation.enabled === false ? 'Enable observation' : 'Disable observation'}>{observation.enabled === false ? <Eye size={15} /> : <EyeOff size={15} />}</button><button type="button" onClick={() => setEditingObservation(observation)} title="Edit observation"><ChevronRight size={16} /></button><button type="button" onClick={() => changeObservation(observation, {}, true)} title="Delete observation"><Trash2 size={15} /></button></div><h3>{observation.title}</h3><p>{observation.description}</p><div className="persona-evidence-list">{(observation.evidence || []).map((source) => <blockquote key={source.message_id}><p>“{source.excerpt}”</p><small>{source.context} · {formatDate(source.created_at)}{source.shared ? ' · Shared room' : ''}</small><button type="button" onClick={() => removeSource(source.message_id)}>Remove as persona evidence</button></blockquote>)}</div></article>)}
                {!enabledObservations.length && <div className="persona-locked"><EyeOff size={24} /><p>No active observations. You remain in control of what the twin can use.</p></div>}
              </section>
            )}
          </>
        )}
      </div>

      {editingObservation && <div className="persona-modal-backdrop"><form className="persona-edit-modal" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); changeObservation(editingObservation, { title: form.get('title'), description: form.get('description') }) }}><span className="persona-eyebrow">Edit inference</span><h2>Correct your twin</h2><label>Title<input name="title" defaultValue={editingObservation.title} required maxLength="80" /></label><label>Description<textarea name="description" defaultValue={editingObservation.description} required maxLength="320" /></label><div><button type="button" onClick={() => setEditingObservation(null)}>Cancel</button><button type="submit"><Save size={16} /> Save correction</button></div></form></div>}
    </section>
  )
}
