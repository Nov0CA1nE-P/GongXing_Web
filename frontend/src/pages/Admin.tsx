import { useEffect, useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { adminRequest, getApiError } from '../config/adminApi'

type Tab = 'pending' | 'pending_follow_ups' | 'allqa' | 'messages' | 'contacts' | 'upload'
type AuthState = 'checking' | 'anonymous' | 'authenticated'

function Admin() {
  const [pwd, setPwd] = useState('')
  const [authState, setAuthState] = useState<AuthState>('checking')
  const [authMessage, setAuthMessage] = useState('')
  const [tab, setTab] = useState<Tab>('pending')
  const [pending, setPending] = useState<any[]>([])
  const [pendingFollowUps, setPendingFollowUps] = useState<any[]>([])
  const [allQA, setAllQA] = useState<any[]>([])
  const [contacts, setContacts] = useState<any[]>([])
  const [msgs, setMsgs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [toast, setToast] = useState('')

  const [cwTitle, setCwTitle] = useState('')
  const [cwDate, setCwDate] = useState('')
  const [cwDesc, setCwDesc] = useState('')
  const [cwTags, setCwTags] = useState('')
  const [cwFile, setCwFile] = useState<File | null>(null)
  const [cwMsg, setCwMsg] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const toast_ = (m: string) => { setToast(m); setTimeout(() => setToast(''), 2800) }

  const clearAdminData = () => {
    setPending([])
    setPendingFollowUps([])
    setAllQA([])
    setContacts([])
    setMsgs([])
  }

  const handleResponse = async (response: Response, fallback: string) => {
    if (response.status === 401) {
      clearAdminData()
      setAuthState('anonymous')
      setAuthMessage('登录已过期，请重新登录')
      void adminRequest('/admin/logout', { method: 'POST' }).catch(() => undefined)
      return false
    }
    if (response.status === 403) {
      toast_('当前身份无权执行此操作')
      return false
    }
    if (!response.ok) {
      toast_(await getApiError(response, fallback))
      return false
    }
    return true
  }

  useEffect(() => {
    let active = true
    adminRequest('/admin/session')
      .then(async response => {
        if (!active) return
        if (response.ok) {
          setAuthState('authenticated')
          const pendingResponse = await adminRequest('/qanda/questions/pending')
          if (!active) return
          if (pendingResponse.ok) {
            setPending(await pendingResponse.json())
          } else if (pendingResponse.status === 401) {
            clearAdminData()
            setAuthState('anonymous')
            setAuthMessage('登录已过期，请重新登录')
            void adminRequest('/admin/logout', { method: 'POST' }).catch(() => undefined)
          } else {
            toast_(await getApiError(pendingResponse, '待审核问答加载失败'))
          }
        } else {
          setAuthState('anonymous')
          if (response.status === 401) {
            void adminRequest('/admin/logout', { method: 'POST' }).catch(() => undefined)
          } else {
            setAuthMessage(await getApiError(response, '会话检查失败'))
          }
        }
      })
      .catch(() => {
        if (active) {
          setAuthState('anonymous')
          setAuthMessage('暂时无法连接服务器，请稍后重试')
        }
      })
    return () => { active = false }
  }, [])

  const login = async () => {
    if (!pwd) return
    let loginSucceeded = false
    setLoading(true)
    setAuthMessage('')
    try {
      const response = await adminRequest('/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: pwd }),
      })
      if (!response.ok) {
        setAuthMessage(await getApiError(response, '登录失败，请稍后重试'))
        return
      }
      loginSucceeded = true
      setAuthState('authenticated')
      const pendingResponse = await adminRequest('/qanda/questions/pending')
      if (await handleResponse(pendingResponse, '待审核问答加载失败')) {
        setPending(await pendingResponse.json())
      }
    } catch {
      if (loginSucceeded) toast_('管理数据加载失败，请稍后重试')
      else setAuthMessage('暂时无法连接服务器，请稍后重试')
    } finally {
      setPwd('')
      setLoading(false)
    }
  }

  const logout = async () => {
    try {
      const response = await adminRequest('/admin/logout', { method: 'POST' })
      if (!response.ok) {
        toast_(await getApiError(response, '退出失败，请稍后重试'))
        return
      }
      clearAdminData()
      setAuthState('anonymous')
      setAuthMessage('已退出登录')
    } catch {
      toast_('退出失败，请检查网络后重试')
    }
  }

  const fetchData = async (t: Tab) => {
    setTab(t)
    try {
      let response: Response | null = null
      if (t === 'pending') {
        response = await adminRequest('/qanda/questions/pending')
        if (await handleResponse(response, '待审核问答加载失败')) setPending(await response.json())
      } else if (t === 'pending_follow_ups') {
        response = await adminRequest('/qanda/follow-ups/pending')
        if (await handleResponse(response, '待审核追问加载失败')) setPendingFollowUps(await response.json())
      } else if (t === 'allqa') {
        response = await adminRequest('/qanda/admin/all')
        if (await handleResponse(response, '全部问答加载失败')) setAllQA((await response.json()).questions)
      } else if (t === 'contacts') {
        response = await adminRequest('/contact/submissions')
        if (await handleResponse(response, '联系表单加载失败')) setContacts(await response.json())
      } else if (t === 'messages') {
        response = await adminRequest('/guestbook/messages?limit=100')
        if (await handleResponse(response, '留言加载失败')) setMsgs((await response.json()).messages)
      }
    } catch {
      toast_('网络连接失败，请稍后重试')
    }
  }

  const review = async (aid: number, s: string) => {
    try {
      const response = await adminRequest(`/qanda/answers/${aid}/review`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: s }),
      })
      if (await handleResponse(response, '审核失败')) {
        toast_(s === 'published' ? '已发布' : '已拒绝')
        void fetchData('pending')
      }
    } catch { toast_('网络连接失败，请稍后重试') }
  }

  const reviewFollowUp = async (fid: number, s: string) => {
    try {
      const response = await adminRequest(`/qanda/follow-ups/${fid}/review`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: s }),
      })
      if (await handleResponse(response, '审核失败')) {
        toast_(s === 'published' ? '已发布' : '已拒绝')
        void fetchData('pending_follow_ups')
      }
    } catch { toast_('网络连接失败，请稍后重试') }
  }

  const deleteFollowUp = async (fid: number) => {
    if (!confirm('确定删除这条追问吗？')) return
    try {
      const response = await adminRequest(`/qanda/follow-ups/${fid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData('pending_follow_ups')
      }
    } catch { toast_('网络连接失败，请稍后重试') }
  }

  const deleteQA = async (qid: number) => {
    if (!confirm('确定要删除这条问答吗？')) return
    try {
      const response = await adminRequest(`/qanda/questions/${qid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData(tab)
      }
    } catch { toast_('网络连接失败，请稍后重试') }
  }

  const deleteMsg = async (mid: number) => {
    if (!confirm('确定要删除这条留言吗？')) return
    try {
      const response = await adminRequest(`/guestbook/messages/${mid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData('messages')
      }
    } catch { toast_('网络连接失败，请稍后重试') }
  }

  const upload = async () => {
    if (!cwTitle || !cwDate || !cwFile) return
    const fd = new FormData()
    fd.append('title', cwTitle); fd.append('date', cwDate)
    fd.append('description', cwDesc); fd.append('tags', cwTags); fd.append('file', cwFile)
    try {
      const response = await adminRequest('/courseware/upload', { method: 'POST', body: fd })
      if (await handleResponse(response, '课件上传失败')) {
        toast_('课件上传成功')
        setCwMsg('')
        setCwTitle(''); setCwDate(''); setCwDesc(''); setCwTags(''); setCwFile(null)
        if (fileRef.current) fileRef.current.value = ''
      }
    } catch {
      setCwMsg('网络连接失败，请稍后重试')
    }
  }

  if (authState === 'checking') {
    return <div className="loading" />
  }

  if (authState === 'anonymous') {
    return (
      <div>
        <div className="page-header"><h1>管理员</h1></div>
        <div className="container" style={{ maxWidth: '380px' }}>
          <div className="card" style={{ padding: '28px' }}>
            <div className="form-group">
              <label>密码</label>
              <input type="password" value={pwd} onChange={e => setPwd(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && login()} placeholder="请输入管理员密码" />
            </div>
            <button className="btn btn-primary" onClick={login} disabled={loading}
              style={{ width: '100%' }}>
              {loading ? '验证中…' : '登录'}
            </button>
            {authMessage && (
              <p style={{ marginTop: '12px', color: 'var(--accent-red)', fontSize: '0.85rem' }}>
                {authMessage}
              </p>
            )}
          </div>
        </div>
      </div>
    )
  }

  const tabs: [Tab, string, number | null][] = [
    ['pending', '待审核问答', pending.length],
    ['pending_follow_ups', '待审核追问', pendingFollowUps.length],
    ['allqa', '全部问答', null],
    ['messages', '留言管理', null],
    ['contacts', '联系表单', null],
    ['upload', '上传课件', null],
  ]

  return (
    <div>
      {toast && <div className="toast toast-success">{toast}</div>}
      <div className="page-header">
        <h1>管理后台</h1>
        <button className="btn btn-outline btn-sm" onClick={logout}>退出登录</button>
      </div>
      <div className="container">
        <div className="tab-bar" style={{ marginBottom: '28px' }}>
          {tabs.map(([k, l, count]) => (
            <button key={k} className={`tab-btn ${tab === k ? 'active' : ''}`}
              onClick={() => fetchData(k)}>
              {l}
              {count != null && count > 0 && (
                <span style={{ background: 'var(--accent-red)', color: 'white', borderRadius: '980px',
                  padding: '1px 6px', fontSize: '0.7rem', marginLeft: '6px' }}>{count}</span>
              )}
            </button>
          ))}
        </div>

        {/* 待审核问答 */}
        {tab === 'pending' && (
          pending.length === 0 ? (
            <div className="empty"><p style={{ fontWeight: 500 }}>没有待审核的问答</p></div>
          ) : (
            pending.map(q => (
              <div key={q.id} className="card">
                <p style={{ fontWeight: 600, fontSize: '0.95rem', marginBottom: '8px' }}>{q.author} 提问：</p>
                <p style={{ fontSize: '0.9rem', lineHeight: 1.6, marginBottom: '16px' }}>{q.content}</p>
                <p style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                  躬行启杭智能大模型 回答：
                </p>
                <div style={{ background: 'var(--bg-alt)', borderRadius: 'var(--radius-sm)', padding: '20px', marginBottom: '16px' }}>
                  <div className="markdown-body"><ReactMarkdown>{q.answer?.content || ''}</ReactMarkdown></div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button className="btn btn-primary btn-sm" onClick={() => review(q.answer.id, 'published')}>发布</button>
                  <button className="btn btn-danger btn-sm" onClick={() => review(q.answer.id, 'rejected')}>拒绝</button>
                </div>
              </div>
            ))
          )
        )}

        {/* 待审核追问 */}
        {tab === 'pending_follow_ups' && (
          pendingFollowUps.length === 0 ? (
            <div className="empty"><p style={{ fontWeight: 500 }}>没有待审核的追问</p></div>
          ) : (
            pendingFollowUps.map((fu: any) => (
              <div key={fu.id} className="card">
                <p style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--accent)', marginBottom: '6px' }}>
                  {fu.author} 在原问题「{fu.question_content?.slice(0, 40)}...」下的追问：
                </p>
                <div style={{ background: 'var(--cream-dark)', padding: '12px 16px', borderRadius: '8px', marginBottom: '12px', fontSize: '0.9rem' }}>
                  {fu.content}
                </div>
                <p style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--green)', marginBottom: '6px' }}>
                  躬行启杭智能大模型 回答：
                </p>
                <div style={{ background: 'var(--bg-alt)', borderRadius: 'var(--radius-sm)', padding: '16px', marginBottom: '14px' }}>
                  <div className="markdown-body"><ReactMarkdown>{fu.answer_content || ''}</ReactMarkdown></div>
                </div>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <button className="btn btn-primary btn-sm" onClick={() => reviewFollowUp(fu.id, 'published')}>发布</button>
                  <button className="btn btn-danger btn-sm" onClick={() => reviewFollowUp(fu.id, 'rejected')}>拒绝</button>
                  <button className="btn btn-outline btn-sm" onClick={() => deleteFollowUp(fu.id)}>删除</button>
                </div>
              </div>
            ))
          )
        )}

        {/* 全部问答 */}
        {tab === 'allqa' && (
          allQA.length === 0 ? (
            <div className="empty"><p style={{ fontWeight: 500 }}>没有任何问答</p></div>
          ) : (
            allQA.map(q => (
              <div key={q.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{q.author} 提问</span>
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    {q.answer && (
                      <span className={`badge badge-${q.answer.status === 'published' ? 'published' : q.answer.status === 'pending' ? 'pending' : 'rejected'}`}>
                        {q.answer.status === 'published' ? '已发布' : q.answer.status === 'pending' ? '待审核' : '已拒绝'}
                      </span>
                    )}
                    <button className="btn btn-sm" style={{ color: 'var(--accent-red)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.78rem' }}
                      onClick={() => deleteQA(q.id)}>删除</button>
                  </div>
                </div>
                <p style={{ fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '12px' }}>{q.content}</p>
                {q.answer && (
                  <div style={{ background: 'var(--bg-alt)', borderRadius: 'var(--radius-sm)', padding: '16px' }}>
                    <div className="markdown-body" style={{ fontSize: '0.85rem' }}>
                      <ReactMarkdown>{q.answer.content}</ReactMarkdown>
                    </div>
                  </div>
                )}
              </div>
            ))
          )
        )}

        {/* 留言管理 */}
        {tab === 'messages' && (
          msgs.length === 0 ? (
            <div className="empty"><p style={{ fontWeight: 500 }}>没有任何留言</p></div>
          ) : (
            msgs.map((m: any) => (
              <div key={m.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{m.author}</span>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: '0.76rem', marginLeft: '10px' }}>
                      {new Date(m.created_at).toLocaleString('zh-CN')}
                    </span>
                  </div>
                  <button className="btn btn-sm" style={{ color: 'var(--accent-red)', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.78rem' }}
                    onClick={() => deleteMsg(m.id)}>删除</button>
                </div>
                <p style={{ fontSize: '0.9rem', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{m.content}</p>
                {m.replies && m.replies.map((r: any) => (
                  <div key={r.id} style={{ marginTop: '10px', marginLeft: '16px', padding: '10px 14px', background: 'var(--bg-alt)', borderRadius: '8px', fontSize: '0.85rem' }}>
                    <span style={{ fontWeight: 600 }}>{r.author}</span>
                    <span style={{ color: 'var(--text-tertiary)', fontSize: '0.72rem', marginLeft: '8px' }}>
                      {new Date(r.created_at).toLocaleString('zh-CN')}
                    </span>
                    <p style={{ marginTop: '4px' }}>{r.content}</p>
                  </div>
                ))}
              </div>
            ))
          )
        )}

        {/* 联系表单 */}
        {tab === 'contacts' && (
          contacts.length === 0 ? (
            <div className="empty"><p style={{ fontWeight: 500 }}>暂无联系表单提交</p></div>
          ) : (
            contacts.map((c: any) => (
              <div key={c.id} className="card">
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 600 }}>{c.name}</span>
                  <span style={{ color: 'var(--text-tertiary)', fontSize: '0.76rem' }}>
                    {new Date(c.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.84rem', marginBottom: '8px' }}>
                  {c.contact_info || '未提供联系方式'}
                </p>
                <p style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>{c.message}</p>
              </div>
            ))
          )
        )}

        {/* 上传课件 */}
        {tab === 'upload' && (
          <div className="card" style={{ padding: '28px' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '20px' }}>上传新课件</h2>
            <div className="form-group">
              <input value={cwTitle} onChange={e => setCwTitle(e.target.value)} placeholder="课件标题" />
            </div>
            <div className="form-group">
              <input type="date" value={cwDate} onChange={e => setCwDate(e.target.value)} />
            </div>
            <div className="form-group">
              <input value={cwDesc} onChange={e => setCwDesc(e.target.value)} placeholder="简介（可选）" />
            </div>
            <div className="form-group">
              <input value={cwTags} onChange={e => setCwTags(e.target.value)} placeholder="标签，用逗号分隔（如：机械,材料）" />
            </div>
            <div className="form-group">
              <input type="file" accept=".ppt,.pptx,.pdf" ref={fileRef}
                onChange={e => setCwFile(e.target.files?.[0] || null)} />
            </div>
            <button className="btn btn-primary" onClick={upload}
              disabled={!cwTitle || !cwDate || !cwFile}>上传</button>
            {cwMsg && <p style={{ marginTop: '12px', fontSize: '0.85rem', color: cwMsg.startsWith('上传失败') ? 'var(--accent-red)' : 'var(--accent-green)' }}>{cwMsg}</p>}
          </div>
        )}
      </div>
    </div>
  )
}

export default Admin
