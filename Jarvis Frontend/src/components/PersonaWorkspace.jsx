import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, ArrowLeft, BarChart3, BrainCircuit, Check, ChevronRight, CircleGauge, Clock3,
  Eye, EyeOff, FileUp, Fingerprint, LoaderCircle, LockKeyhole, Menu, MessageSquareText,
  Network, Pin, RefreshCw, Save, ShieldCheck, Target, Trash2, X,
} from 'lucide-react'
import './PersonaDashboard.css'
import './PersonaWorkspace.css'

const activeStatuses = new Set(['queued', 'collecting', 'analyzing', 'generating_image'])
const controlMeta = {
  mirror_complement: ['Agent alignment', 'Mirror me', 'Complement me'],
  concise_detailed: ['Response depth', 'Concise', 'Detailed'],
  direct_diplomatic: ['Delivery', 'Direct', 'Diplomatic'],
  analytical_creative: ['Reasoning', 'Analytical', 'Creative'],
  cautious_bold: ['Decision energy', 'Cautious', 'Bold'],
  supportive_challenging: ['Empathy mode', 'Supportive', 'Challenging'],
  structured_exploratory: ['Working mode', 'Structured', 'Exploratory'],
}

function levelLabel(level = '') {
  return ({ not_ready: 'Building signal', early_signal: 'Early signal', emerging: 'Emerging persona', calibrated: 'Calibrated', adaptive: 'Adaptive' })[level] || 'Not measured'
}

function SignalBar({ label, value, detail = '' }) {
  const score = Math.max(0, Math.min(100, Number(value || 0)))
  return <div className="local-signal-bar"><div><span>{label}</span><strong>{score}%</strong></div><div><i style={{ width: `${score}%` }} /></div>{detail && <small>{detail}</small>}</div>
}

function DashboardBand({ icon, title, subtitle, children }) {
  return <section className="local-dashboard-band"><header>{icon}<strong>{title}</strong><small>{subtitle}</small><i /></header><div className="local-dashboard-grid">{children}</div></section>
}

function ActivityHeatmap({ rows = [] }) {
  const maximum = Math.max(1, ...rows.flatMap((row) => row.hours || []))
  return <div className="local-heatmap">{rows.map((row) => <div key={row.day}><span>{row.day}</span><div>{(row.hours || []).map((count, hour) => <i key={hour} title={`${row.day} ${String(hour).padStart(2, '0')}:00 - ${count} messages`} style={{ opacity: 0.12 + (count / maximum) * 0.88 }} />)}</div></div>)}<footer><span>00h</span><span>06h</span><span>12h</span><span>18h</span><span>23h</span></footer></div>
}

function ChatDashboard({ analysis }) {
  const behavior = analysis.behavior || {}
  const tone = behavior.tone || {}
  const attention = behavior.attention || {}
  const decision = behavior.decision_style || {}
  const profile = analysis.profile || {}
  return <div className="persona-local-dashboard">
    <header className="local-dashboard-head"><div><span className="persona-eyebrow"><Fingerprint size={13} /> Conversation persona</span><h2>{analysis.name || 'Conversation dashboard'}</h2><p>{profile.summary || 'This profile describes your communication in this conversation only.'}</p></div><Stats items={[[analysis.message_count, 'Messages'], [analysis.word_count, 'Words'], [behavior.median_reply_minutes == null ? '-' : `${behavior.median_reply_minutes}m`, 'Median reply'], ['Local only', 'Method']]} /></header>
    <DashboardBand icon={<CircleGauge size={17} />} title="Communication profile" subtitle="message structure and language markers">
      <Panel title="Behavior dimensions" meta={`${Number(analysis.message_count || 0).toLocaleString()} messages`}>{(analysis.dimensions || []).map((item) => <SignalBar key={item.key} label={item.label} value={item.score} detail={`${item.low_label} to ${item.high_label}`} />)}</Panel>
      <Panel title="Tone markers" meta="dictionary based"><SignalBar label="Positive language" value={tone.positive} /><SignalBar label="Curiosity" value={tone.curiosity} /><SignalBar label="Supportive language" value={tone.supportive_language} /><SignalBar label="Negative language" value={tone.negative} /></Panel>
      <Panel title="Participant balance" meta={`${analysis.participant_count || 0} participants`}><div className="local-participants">{(analysis.participants || []).map((item) => <div key={item.name}><span>{item.name}</span><div><i style={{ width: `${item.share}%` }} /></div><strong>{item.share}%</strong><small>{Number(item.messages).toLocaleString()} msgs</small></div>)}</div></Panel>
    </DashboardBand>
    <DashboardBand icon={<Network size={17} />} title="Knowledge and context" subtitle="topics, preferences, and explicit plans">
      <Panel title="Topic network" meta={`${analysis.topic_graph?.nodes?.length || 0} clusters`}><TopicNodes topics={(analysis.topic_graph?.nodes || []).map((item) => ({ name: item.label, score: item.weight }))} /></Panel>
      <Panel title="Preference-like statements" meta="explicit wording only"><Statements items={analysis.preference_statements} empty="No explicit preference phrases detected." /></Panel>
      <Panel title="Goals and action language" meta="not inferred"><Statements items={analysis.goal_statements} empty="No explicit goal phrases detected." /></Panel>
    </DashboardBand>
    <DashboardBand icon={<Activity size={17} />} title="Behavioral patterns" subtitle="timing, attention, and decision language">
      <Panel title="Interaction heatmap" meta="day by hour" wide><ActivityHeatmap rows={behavior.heatmap || []} /></Panel>
      <Panel title="Decision language" meta={`${decision.reasoning_markers || 0} reasoning markers`}><SignalBar label="Evidence-led" value={decision.evidence_led} /><SignalBar label="Exploratory" value={decision.exploratory} /><div className="local-kpi"><small>Planning markers</small><strong>{decision.planning_markers || 0}</strong></div></Panel>
      <Panel title="Attention and engagement" meta="message-length signals"><SignalBar label="Deep messages" value={attention.deep_messages} /><SignalBar label="Quick messages" value={attention.quick_messages} /><SignalBar label="Question-led" value={attention.question_led} /></Panel>
      <Panel title="Conversation rhythm" meta={`${behavior.reply_samples || 0} transitions`}><div className="local-rhythm"><div><Clock3 size={16} /><span>Median reply time</span><strong>{behavior.median_reply_minutes == null ? 'Not enough data' : `${behavior.median_reply_minutes} min`}</strong></div>{(behavior.initiations || []).map((item) => <div key={item.author}><Target size={16} /><span>{item.author}</span><strong>{item.count} starts</strong></div>)}</div></Panel>
    </DashboardBand>
    <Method text={profile.method} />
  </div>
}

function Stats({ items }) {
  return <div className="local-dashboard-stats">{items.map(([value, label]) => <div key={label}><small>{label}</small><strong>{typeof value === 'number' ? value.toLocaleString() : value}</strong></div>)}</div>
}

function Panel({ title, meta, wide = false, children }) {
  return <article className={`local-dashboard-panel ${wide ? 'local-wide' : ''}`}><div className="local-panel-title"><strong>{title}</strong><small>{meta}</small></div>{children}</article>
}

function TopicNodes({ topics = [] }) {
  return <div className="local-topic-nodes">{topics.map((item) => <span key={item.name} style={{ '--weight': item.score }}>{item.name}<small>{item.score}</small></span>)}</div>
}

function Statements({ items = [], empty }) {
  return <div className="local-statement-list">{(items || []).map((item, index) => <blockquote key={`${item.author}-${index}`}><p>{item.text}</p><small>{item.author}</small></blockquote>)}{!items?.length && <p className="local-empty">{empty}</p>}</div>
}

function Method({ text }) {
  return <section className="local-method"><BarChart3 size={18} /><div><strong>Deterministic analysis</strong><p>{text || 'Local counting, timing, vocabulary, and explicit-language rules. No LLM, paid API, diagnosis, or hidden personality inference.'}</p></div></section>
}

export default function PersonaWorkspace({ apiBase, fetchApi, user, onBack, onRequireAuth }) {
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(Boolean(user))
  const [refreshing, setRefreshing] = useState(false)
  const [runBusy, setRunBusy] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [controlsBusy, setControlsBusy] = useState(false)
  const [controls, setControls] = useState({})
  const [selectedView, setSelectedView] = useState('global')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [editingObservation, setEditingObservation] = useState(null)
  const [error, setError] = useState('')

  const loadDashboard = useCallback(async ({ quiet = false } = {}) => {
    if (!user) return
    quiet ? setRefreshing(true) : setLoading(true)
    try {
      const response = await fetchApi(`${apiBase}/api/persona`, { credentials: 'include' })
      const data = await response.json()
      if (response.status === 401) return onRequireAuth()
      if (!response.ok) throw new Error(data.detail || 'Could not load your persona.')
      setDashboard(data)
      setControls(data.profile?.controls || {})
      setError('')
    } catch (requestError) { setError(requestError.message || 'Could not load your persona.') } finally { setLoading(false); setRefreshing(false) }
  }, [apiBase, fetchApi, onRequireAuth, user])

  useEffect(() => { const timer = window.setTimeout(() => loadDashboard(), 0); return () => window.clearTimeout(timer) }, [loadDashboard])
  useEffect(() => { if (!user || !dashboard?.is_processing) return undefined; const timer = window.setTimeout(() => loadDashboard({ quiet: true }), 5000); return () => window.clearTimeout(timer) }, [dashboard?.is_processing, dashboard?.run?.progress, loadDashboard, user])

  const uploadChat = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setImportBusy(true)
    try {
      const body = new FormData(); body.append('file', file)
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports`, { method: 'POST', credentials: 'include', body })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not read that chat export.')
      setSelectedView(data.chat_import?.id || 'global')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) } finally { setImportBusy(false) }
  }

  const toggleSource = async (item, include) => {
    try {
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports/${encodeURIComponent(item.id)}`, { method: 'PATCH', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ include_in_merged: include }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not update this source.')
      setDashboard((current) => ({ ...current, chat_imports: (current.chat_imports || []).map((entry) => entry.id === item.id ? data.chat_import : entry) }))
    } catch (requestError) { setError(requestError.message) }
  }

  const deleteImport = async (item) => {
    if (!window.confirm(`Delete ${item.filename || 'this imported conversation'}?`)) return
    try {
      const response = await fetchApi(`${apiBase}/api/persona/chat-imports/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'include' })
      if (!response.ok) { const data = await response.json(); throw new Error(data.detail || 'Could not delete this import.') }
      if (selectedView === item.id) setSelectedView('global')
      await loadDashboard({ quiet: true })
    } catch (requestError) { setError(requestError.message) }
  }

  const startRun = async () => {
    if (runBusy || dashboard?.is_processing) return
    setRunBusy(true); setError('')
    try {
      const response = await fetchApi(`${apiBase}/api/persona/runs`, { method: 'POST', credentials: 'include' })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not regenerate the global persona.')
      setDashboard((current) => ({ ...current, run: data.run, is_processing: true }))
    } catch (requestError) { setError(requestError.message) } finally { setRunBusy(false) }
  }

  const mutate = async (path, options, fallback) => {
    const response = await fetchApi(`${apiBase}${path}`, { credentials: 'include', ...options })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || fallback)
    await loadDashboard({ quiet: true })
  }

  const saveControls = async () => {
    setControlsBusy(true)
    try { await mutate('/api/persona/controls', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(controls) }, 'Could not save persona controls.') } catch (requestError) { setError(requestError.message) } finally { setControlsBusy(false) }
  }

  const changeObservation = async (observation, updates, remove = false) => {
    try { await mutate(`/api/persona/observations/${encodeURIComponent(observation.id)}`, remove ? { method: 'DELETE' } : { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(updates) }, 'Could not update this observation.'); setEditingObservation(null) } catch (requestError) { setError(requestError.message) }
  }

  const removePersona = async () => {
    if (!window.confirm('Delete the generated global persona? Imported conversations remain available.')) return
    try { await mutate('/api/persona', { method: 'DELETE' }, 'Could not delete your persona.') } catch (requestError) { setError(requestError.message) }
  }

  const profile = dashboard?.profile
  const readiness = profile?.readiness || dashboard?.run?.readiness || {}
  const imports = dashboard?.chat_imports || []
  const selectedImport = imports.find((item) => item.id === selectedView)
  const observations = useMemo(() => profile?.observations || [], [profile?.observations])
  const includedCount = imports.filter((item) => item.include_in_merged).length

  if (!user) return <section className="persona-page persona-auth-state"><div><ShieldCheck size={40} /><h1>Sign in to see your persona</h1><p>This workspace is private.</p><button type="button" onClick={onRequireAuth}>Sign in</button></div></section>
  if (loading && !dashboard) return <section className="persona-page persona-loading"><LoaderCircle className="persona-spin" size={30} /><p>Opening your persona workspace...</p></section>

  return <section className="persona-page persona-workspace-page">
    <button className="persona-mobile-menu" type="button" onClick={() => setSidebarOpen((open) => !open)}><Menu size={19} /><span>Dashboards</span></button>
    <div className="persona-workspace">
      {sidebarOpen && <button className="persona-sidebar-scrim" type="button" aria-label="Close dashboard menu" onClick={() => setSidebarOpen(false)} />}
      <aside className={`command-sidebar chat-sidebar persona-workspace-sidebar ${sidebarOpen ? 'mobile-open' : ''}`}>
        <button className="mobile-drawer-close" type="button" onClick={() => setSidebarOpen(false)} aria-label="Close dashboard menu"><X size={18} /></button>
        <div className="chat-sidebar-content">
          <button className="new-chat-button" type="button" onClick={onBack}><ArrowLeft size={17} /> Back to chats</button>
          <div className="chat-list-heading"><p className="section-label">PERSONA DASHBOARDS</p></div>
          <div className="persona-sidebar-list">
            <div className={`persona-sidebar-row ${selectedView === 'global' ? 'active' : ''}`}><button className="persona-sidebar-select" type="button" onClick={() => { setSelectedView('global'); setSidebarOpen(false) }}><Pin size={15} /><span><strong>Global Persona</strong><small>{includedCount} imported source{includedCount === 1 ? '' : 's'}</small></span></button><button className="persona-sidebar-delete" type="button" onClick={removePersona} title="Delete global persona" aria-label="Delete global persona"><Trash2 size={14} /></button></div>
            {imports.map((item) => <div className={`persona-sidebar-row ${selectedView === item.id ? 'active' : ''}`} key={item.id}><button className="persona-sidebar-select" type="button" onClick={() => { setSelectedView(item.id); setSidebarOpen(false) }}><MessageSquareText size={15} /><span><strong>{item.analysis?.name || item.filename}</strong><small>{Number(item.analysis?.message_count || 0).toLocaleString()} messages</small></span></button><button className="persona-sidebar-delete" type="button" onClick={() => deleteImport(item)} title="Delete imported conversation" aria-label={`Delete ${item.analysis?.name || item.filename}`}><Trash2 size={14} /></button></div>)}
          </div>
          <label className="persona-sidebar-upload"><FileUp size={16} /><span>{importBusy ? 'Analyzing export...' : 'Upload conversation'}</span><input type="file" accept=".zip,.txt,.json,application/zip,text/plain,application/json" onChange={uploadChat} disabled={importBusy} /></label>
          <div className="sidebar-foot"><span className="shield-icon" aria-hidden="true" /><p><strong>Private and local</strong><small>No LLM or paid API</small></p></div>
        </div>
      </aside>
      <main className="persona-workspace-main"><div className="persona-shell">
        {error && <div className="persona-error">{error}</div>}
        {selectedImport ? <ChatDashboard analysis={selectedImport.analysis || {}} /> : <GlobalDashboard dashboard={dashboard} profile={profile} readiness={readiness} imports={imports} observations={observations} controls={controls} setControls={setControls} controlsBusy={controlsBusy} refreshing={refreshing} runBusy={runBusy} onToggleSource={toggleSource} onRun={startRun} onRefresh={() => loadDashboard({ quiet: true })} onSaveControls={saveControls} onChangeObservation={changeObservation} onEditObservation={setEditingObservation} />}
      </div></main>
    </div>
    {editingObservation && <div className="persona-modal-backdrop"><form className="persona-edit-modal" onSubmit={(event) => { event.preventDefault(); const form = new FormData(event.currentTarget); changeObservation(editingObservation, { title: form.get('title'), description: form.get('description') }) }}><span className="persona-eyebrow">Edit observation</span><h2>Correct this signal</h2><label>Title<input name="title" defaultValue={editingObservation.title} required maxLength="80" /></label><label>Description<textarea name="description" defaultValue={editingObservation.description} required maxLength="320" /></label><div><button type="button" onClick={() => setEditingObservation(null)}>Cancel</button><button type="submit"><Save size={16} /> Save</button></div></form></div>}
  </section>
}

function GlobalDashboard({ dashboard, profile, readiness, imports, observations, controls, setControls, controlsBusy, refreshing, runBusy, onToggleSource, onRun, onRefresh, onSaveControls, onChangeObservation, onEditObservation }) {
  const modules = readiness.modules || {}
  return <div className="persona-local-dashboard global-persona-dashboard">
    <header className="local-dashboard-head"><div><span className="persona-eyebrow"><ShieldCheck size={13} /> Private global profile</span><h2>{profile?.persona_name || 'Global Persona'}</h2><p>{profile?.summary || 'Your combined profile from Nexa and only the imported conversations you approve.'}</p></div><Stats items={[[Number(readiness.meaningful_messages || 0), 'Signals'], [Number(readiness.authored_words || 0), 'Words'], [Number(readiness.conversation_contexts || 0), 'Contexts'], ['Local only', 'Method']]} /></header>
    <section className="persona-source-manager"><div className="persona-source-head"><div><strong>Sources in Global Persona</strong><small>Selections save immediately. Regeneration happens only when you request it.</small></div><div><button className="icon-refresh" type="button" onClick={onRefresh} disabled={refreshing} title="Refresh dashboard"><RefreshCw className={refreshing ? 'persona-spin' : ''} size={16} /></button><button type="button" onClick={onRun} disabled={runBusy || dashboard?.is_processing}>{runBusy || dashboard?.is_processing ? <LoaderCircle className="persona-spin" size={16} /> : <RefreshCw size={16} />} Regenerate Global Persona</button></div></div><div className="persona-source-grid"><label className="locked"><input type="checkbox" checked readOnly /><span><strong>Nexa conversations</strong><small>Your authored messages</small></span><LockKeyhole size={14} /></label>{imports.map((item) => <label key={item.id}><input type="checkbox" checked={Boolean(item.include_in_merged)} onChange={(event) => onToggleSource(item, event.target.checked)} /><span><strong>{item.analysis?.name || item.filename}</strong><small>{Number(item.analysis?.message_count || 0).toLocaleString()} messages</small></span></label>)}</div></section>
    {activeStatuses.has(dashboard?.run?.status) && <div className="persona-processing"><LoaderCircle className="persona-spin" size={18} /><div><strong>{dashboard.run.message || 'Rebuilding global persona...'}</strong><small>Deterministic analysis is running in the background.</small></div><span>{dashboard.run.progress || 0}%</span></div>}
    {dashboard?.run?.status === 'failed' && <div className="persona-error"><strong>The last run did not finish.</strong> Your previous snapshot is unchanged.</div>}
    {!profile && !dashboard?.is_processing && <section className="persona-global-empty"><BrainCircuit size={24} /><div><strong>No global snapshot yet</strong><p>Select the contexts above and generate the first combined dashboard.</p></div></section>}
    {profile && <>
      <DashboardBand icon={<CircleGauge size={17} />} title="Communication profile" subtitle="directional language and interaction signals">
        <Panel title="Behavior dimensions" meta={`${readiness.score || 0}% readiness`}>{(profile.dimensions || []).map((item) => <SignalBar key={item.key} label={item.label} value={item.score} detail={`${item.low_label} to ${item.high_label}`} />)}</Panel>
        <Panel title="Current archetypes" meta="context weighted"><TextItems items={(profile.archetypes || []).map((item) => ({ title: item.name, text: item.description }))} /></Panel>
        <Panel title="Strength signals" meta="recurring markers"><div className="global-chip-list">{(profile.strengths || []).map((item) => <span key={item}>{item}</span>)}</div></Panel>
      </DashboardBand>
      <DashboardBand icon={<Network size={17} />} title="Knowledge and context" subtitle="recurring topics and practical interaction patterns">
        <Panel title="Topic universe" meta={`${profile.topics?.length || 0} clusters`}><TopicNodes topics={(profile.topics || []).map((item) => ({ name: item.name, score: item.score }))} /></Panel>
        <Panel title="How to work with me" meta="interaction guide"><ol className="global-number-list">{(profile.how_to_work_with_me || []).map((item) => <li key={item}>{item}</li>)}</ol></Panel>
        <Panel title="Decision and collaboration" meta="evidence gated"><TextItems items={[...(profile.decision_patterns || []), ...(profile.collaboration_roles || [])].map((text) => ({ text }))} />{!modules.decision_style && !modules.collaboration && <p className="local-empty">More explicit decisions and shared interactions are needed.</p>}</Panel>
      </DashboardBand>
      <DashboardBand icon={<Activity size={17} />} title="Behavior and evidence" subtitle="readiness and inspectable observations">
        <Panel title="Evidence readiness" meta={levelLabel(readiness.level)}>{(readiness.requirements || []).map((item) => <SignalBar key={item.key} label={item.label} value={Math.min(100, Math.round((Number(item.current || 0) / Math.max(1, Number(item.target || 1))) * 100))} detail={`${Number(item.current || 0).toLocaleString()} of ${Number(item.target || 0).toLocaleString()}`} />)}</Panel>
        <Panel title="Inspectable observations" meta={`${observations.filter((item) => item.enabled !== false).length} active`} wide><div className="global-observation-list">{observations.map((item) => <div key={item.id} className={item.enabled === false ? 'disabled' : ''}><span>{item.category?.replaceAll('_', ' ')}</span><strong>{item.title}</strong><p>{item.description}</p><small>{item.confidence}% confidence</small><div><button type="button" onClick={() => onChangeObservation(item, { enabled: item.enabled === false })} title={item.enabled === false ? 'Enable observation' : 'Disable observation'}>{item.enabled === false ? <Eye size={14} /> : <EyeOff size={14} />}</button><button type="button" onClick={() => onEditObservation(item)} title="Edit observation"><ChevronRight size={15} /></button><button type="button" onClick={() => onChangeObservation(item, {}, true)} title="Delete observation"><Trash2 size={14} /></button></div></div>)}</div></Panel>
      </DashboardBand>
      <DashboardBand icon={<ShieldCheck size={17} />} title="Persona controls" subtitle="agent alignment and privacy boundaries">
        <Panel title="Response alignment" meta="user controlled" wide><div className="global-control-grid">{Object.entries(controlMeta).map(([key, [label, low, high]]) => <label className="persona-slider" key={key}><div><strong>{label}</strong><span>{controls[key] ?? 50}</span></div><input type="range" min="0" max="100" value={controls[key] ?? 50} onChange={(event) => setControls((current) => ({ ...current, [key]: Number(event.target.value) }))} /><div><small>{low}</small><small>{high}</small></div></label>)}</div><label className="persona-agent-toggle"><input type="checkbox" checked={Boolean(controls.apply_to_agent)} onChange={(event) => setControls((current) => ({ ...current, apply_to_agent: event.target.checked }))} /><span><strong>Use these controls in Nexa chats</strong><small>Off by default</small></span></label><button className="persona-save" type="button" onClick={onSaveControls} disabled={controlsBusy}>{controlsBusy ? <LoaderCircle className="persona-spin" size={16} /> : <Save size={16} />} Save controls</button></Panel>
        <Panel title="Privacy boundary" meta="private"><ul className="global-privacy-list"><li><Check size={15} />Only your authored messages are analyzed</li><li><Check size={15} />Sensitive traits are not inferred</li><li><Check size={15} />Imports stay separate until approved</li></ul></Panel>
      </DashboardBand>
      <Method />
    </>}
  </div>
}

function TextItems({ items = [] }) {
  return <div className="global-text-list">{items.map((item, index) => <div key={`${item.title || 'item'}-${index}`}>{item.title && <strong>{item.title}</strong>}<p>{item.text}</p></div>)}</div>
}
