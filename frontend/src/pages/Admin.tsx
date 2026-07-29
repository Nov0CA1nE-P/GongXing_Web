import { useEffect, useState, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  adminRequest,
  clearAdminCsrfToken,
  getApiError,
  setAdminCsrfToken,
} from '../config/adminApi'
import { loadJson } from '../config/listApi'
import {
  isAdminCoursewareList,
  type AdminCoursewareItem,
} from '../types/courseware'

type Tab = 'pending' | 'pending_follow_ups' | 'allqa' | 'messages' | 'contacts' | 'upload'
type AuthState = 'checking' | 'anonymous' | 'authenticated'

function getCoursewareFile(item: AdminCoursewareItem) {
  const fileName = item.pdf_path || item.pptx_path || ''
  const extension = fileName.split('.').pop()?.toUpperCase() || ''
  return {
    fileName,
    fileType: ['PDF', 'PPT', 'PPTX'].includes(extension)
      ? extension
      : '课件文件',
  }
}

function formatUtcTimestamp(value: unknown) {
  if (typeof value !== 'string') return '时间异常'
  const normalized = value.includes('T')
    ? value
    : `${value.replace(' ', 'T')}Z`
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime())
    ? '时间异常'
    : parsed.toLocaleString('zh-CN')
}

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
  const [toastError, setToastError] = useState(false)

  const [cwTitle, setCwTitle] = useState('')
  const [cwDesc, setCwDesc] = useState('')
  const [cwTags, setCwTags] = useState('')
  const [cwFile, setCwFile] = useState<File | null>(null)
  const [cwMsg, setCwMsg] = useState('')
  const [courseware, setCourseware] = useState<AdminCoursewareItem[]>([])
  const [cwListLoading, setCwListLoading] = useState(false)
  const [cwListLoaded, setCwListLoaded] = useState(false)
  const [cwListError, setCwListError] = useState('')
  const [cwActionError, setCwActionError] = useState('')
  const [cwUploading, setCwUploading] = useState(false)
  const [deletingCoursewareId, setDeletingCoursewareId] = useState<number | null>(null)
  const [deletingContactId, setDeletingContactId] = useState<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const coursewareRequestIdRef = useRef(0)
  const coursewareControllerRef = useRef<AbortController | null>(null)

  const toast_ = (m: string, error = false) => {
    setToastError(error)
    setToast(m)
    setTimeout(() => setToast(''), 2800)
  }

  const clearAdminData = () => {
    setPending([])
    setPendingFollowUps([])
    setAllQA([])
    setContacts([])
    setMsgs([])
    coursewareRequestIdRef.current += 1
    coursewareControllerRef.current?.abort()
    setCourseware([])
    setCwListLoading(false)
    setCwListLoaded(false)
    setCwListError('')
    setCwActionError('')
    setDeletingCoursewareId(null)
    setDeletingContactId(null)
  }

  const expireAdminSession = () => {
    clearAdminCsrfToken()
    clearAdminData()
    setAuthState('anonymous')
    setAuthMessage('登录已过期，请重新登录')
  }

  const handleResponse = async (response: Response, fallback: string) => {
    if (response.status === 401) {
      expireAdminSession()
      return false
    }
    if (response.status === 403) {
      toast_(await getApiError(response, '安全校验失败或当前身份无权限'), true)
      return false
    }
    if (!response.ok) {
      toast_(await getApiError(response, fallback), true)
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
          const session = await response.json()
          setAdminCsrfToken(session.csrf_token)
          setAuthState('authenticated')
          const pendingResponse = await adminRequest('/qanda/questions/pending')
          if (!active) return
          if (pendingResponse.ok) {
            setPending(await pendingResponse.json())
          } else if (pendingResponse.status === 401) {
            expireAdminSession()
          } else {
            toast_(await getApiError(pendingResponse, '待审核问答加载失败'), true)
          }
        } else {
          clearAdminCsrfToken()
          setAuthState('anonymous')
          if (response.status === 401) {
            setAuthMessage('登录已过期，请重新登录')
          } else {
            setAuthMessage(await getApiError(response, '会话检查失败'))
          }
        }
      })
      .catch(() => {
        if (active) {
          clearAdminCsrfToken()
          setAuthState('anonymous')
          setAuthMessage('暂时无法连接服务器，请稍后重试')
        }
      })
    return () => {
      active = false
      coursewareRequestIdRef.current += 1
      coursewareControllerRef.current?.abort()
    }
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
        clearAdminCsrfToken()
        setAuthMessage(await getApiError(response, '登录失败，请稍后重试'))
        return
      }
      const session = await response.json()
      setAdminCsrfToken(session.csrf_token)
      loginSucceeded = true
      setAuthState('authenticated')
      const pendingResponse = await adminRequest('/qanda/questions/pending')
      if (await handleResponse(pendingResponse, '待审核问答加载失败')) {
        setPending(await pendingResponse.json())
      }
    } catch {
      if (loginSucceeded) toast_('管理数据加载失败，请稍后重试', true)
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
        toast_(await getApiError(response, '退出失败，请稍后重试'), true)
        return
      }
      clearAdminData()
      clearAdminCsrfToken()
      setAuthState('anonymous')
      setAuthMessage('已退出登录')
    } catch {
      toast_('退出失败，请检查网络后重试', true)
    }
  }

  const loadCourseware = async (): Promise<'success' | 'failed' | 'ignored'> => {
    const requestId = coursewareRequestIdRef.current + 1
    coursewareRequestIdRef.current = requestId
    coursewareControllerRef.current?.abort()
    const controller = new AbortController()
    coursewareControllerRef.current = controller
    setCwListLoading(true)
    setCwListError('')

    const result = await loadJson(
      {
        request: signal => adminRequest('/courseware/admin/list', { signal }),
        validate: isAdminCoursewareList,
        getHttpError: response => getApiError(
          response,
          '课件列表加载失败，请稍后重试',
        ),
        invalidMessage: '服务器返回的课件数据格式异常，请稍后重试',
        networkMessage: '无法连接课件服务，请检查网络后重试',
      },
      controller.signal,
    )

    if (
      requestId !== coursewareRequestIdRef.current
      || (!result.ok && result.kind === 'aborted')
    ) {
      return 'ignored'
    }

    if (result.ok) {
      setCourseware(result.data)
      setCwListLoaded(true)
      setCwListLoading(false)
      setCwActionError('')
      return 'success'
    }

    if (result.status === 401) {
      expireAdminSession()
      return 'failed'
    }

    setCwListError(result.message)
    setCwListLoading(false)
    return 'failed'
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
      } else if (t === 'upload') {
        await loadCourseware()
      }
    } catch {
      toast_('网络连接失败，请稍后重试', true)
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
    } catch { toast_('网络连接失败，请稍后重试', true) }
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
    } catch { toast_('网络连接失败，请稍后重试', true) }
  }

  const deleteFollowUp = async (fid: number) => {
    if (!confirm('确定删除这条追问吗？')) return
    try {
      const response = await adminRequest(`/qanda/follow-ups/${fid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData('pending_follow_ups')
      }
    } catch { toast_('网络连接失败，请稍后重试', true) }
  }

  const deleteQA = async (qid: number) => {
    if (!confirm('确定要删除这条问答吗？')) return
    try {
      const response = await adminRequest(`/qanda/questions/${qid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData(tab)
      }
    } catch { toast_('网络连接失败，请稍后重试', true) }
  }

  const deleteMsg = async (mid: number) => {
    if (!confirm('确定要删除这条留言吗？')) return
    try {
      const response = await adminRequest(`/guestbook/messages/${mid}`, { method: 'DELETE' })
      if (await handleResponse(response, '删除失败')) {
        toast_('已删除')
        void fetchData('messages')
      }
    } catch { toast_('网络连接失败，请稍后重试', true) }
  }

  const deleteContact = async (contactId: number) => {
    if (deletingContactId !== null) return
    if (!confirm('确定删除这条联系记录吗？删除后无法从网站恢复。')) return
    setDeletingContactId(contactId)
    try {
      const response = await adminRequest(`/contact/submissions/${contactId}`, {
        method: 'DELETE',
      })
      if (response.status === 401 || response.status === 403) {
        await handleResponse(response, '联系记录删除失败')
        return
      }
      if (response.status === 404) {
        setContacts(current => current.filter(contact => contact.id !== contactId))
        toast_('该联系记录已经不存在，列表已更新', true)
        return
      }
      if (!response.ok) {
        toast_(await getApiError(response, '联系记录删除失败，请稍后重试'), true)
        return
      }
      setContacts(current => current.filter(contact => contact.id !== contactId))
      toast_('联系记录已删除')
    } catch {
      toast_('网络连接失败，删除结果未确认，请手动刷新', true)
    } finally {
      setDeletingContactId(current => current === contactId ? null : current)
    }
  }

  const deleteCourseware = async (item: AdminCoursewareItem) => {
    if (deletingCoursewareId !== null) return
    if (!confirm(`确定删除课件“${item.title}”吗？删除后将无法从网站恢复。`)) return

    setDeletingCoursewareId(item.id)
    setCwActionError('')
    try {
      const response = await adminRequest(`/courseware/${item.id}`, {
        method: 'DELETE',
      })
      if (response.status === 401) {
        await handleResponse(response, '课件删除失败')
        return
      }
      if (response.status === 404) {
        setCourseware(current => current.filter(course => course.id !== item.id))
        toast_('该课件已经不存在，列表已更新', true)
        return
      }
      if (!response.ok) {
        const message = await getApiError(response, '课件删除失败，请稍后重试')
        setCwActionError(message)
        toast_(message, true)
        return
      }

      setCourseware(current => current.filter(course => course.id !== item.id))
      setCwActionError('')
      toast_('课件已删除')
    } catch {
      const message = '网络连接失败，删除结果未确认，请手动刷新'
      setCwActionError(message)
      toast_(message, true)
    } finally {
      setDeletingCoursewareId(current => current === item.id ? null : current)
    }
  }

  const upload = async () => {
    if (!cwTitle || !cwFile || cwUploading) return
    if (
      !cwFile.name.toLowerCase().endsWith('.pdf')
      || cwFile.type !== 'application/pdf'
    ) {
      setCwMsg('V1 运营入口只接受浏览器识别为 PDF 的 .pdf 文件')
      return
    }
    setCwUploading(true)
    setCwMsg('')
    setCwActionError('')
    const fd = new FormData()
    fd.append('title', cwTitle)
    fd.append('description', cwDesc); fd.append('tags', cwTags); fd.append('file', cwFile)
    try {
      const response = await adminRequest('/courseware/upload', { method: 'POST', body: fd })
      if (response.status === 401 || response.status === 403) {
        await handleResponse(response, '课件上传失败')
      } else if (!response.ok) {
        setCwMsg(await getApiError(response, '课件上传失败'))
      } else {
        setCwMsg('')
        setCwTitle(''); setCwDesc(''); setCwTags(''); setCwFile(null)
        if (fileRef.current) fileRef.current.value = ''
        const refreshResult = await loadCourseware()
        if (refreshResult === 'failed') {
          toast_('课件上传成功，但列表刷新失败，请手动刷新', true)
        } else {
          toast_('课件上传成功')
        }
      }
    } catch {
      setCwMsg('网络连接失败，请稍后重试')
    } finally {
      setCwUploading(false)
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
    ['upload', '课件管理', null],
  ]

  return (
    <div>
      {toast && <div className={`toast ${toastError ? 'toast-error' : 'toast-success'}`}>{toast}</div>}
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
                  <button className="btn btn-danger btn-sm"
                    disabled={deletingContactId !== null}
                    onClick={() => void deleteContact(c.id)}>
                    {deletingContactId === c.id ? '删除中…' : '删除'}
                  </button>
                </div>
                <p style={{ color: 'var(--text-tertiary)', fontSize: '0.76rem', marginBottom: '8px' }}>
                  提交：{formatUtcTimestamp(c.created_at)}
                  {' · '}
                  {c.retention_status === 'invalid_timestamp'
                    ? '时间异常，需人工处理'
                    : `预计到期：${formatUtcTimestamp(c.expires_at)}`}
                </p>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.84rem', marginBottom: '8px' }}>
                  {c.contact_info || '未提供联系方式'}
                </p>
                <p style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>{c.message}</p>
              </div>
            ))
          )
        )}

        {/* 课件管理 */}
        {tab === 'upload' && (
          <>
            <div className="card" style={{ padding: '28px' }}>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '20px' }}>上传新课件</h2>
              <div className="form-group">
                <input value={cwTitle} onChange={e => setCwTitle(e.target.value)} placeholder="课件标题" />
              </div>
              <div className="form-group">
                <input value={cwDesc} onChange={e => setCwDesc(e.target.value)} placeholder="简介（可选）" />
              </div>
              <div className="form-group">
                <input value={cwTags} onChange={e => setCwTags(e.target.value)} placeholder="标签，用逗号分隔（如：机械,材料）" />
              </div>
              <div className="form-group">
                <input type="file" accept=".pdf,application/pdf" ref={fileRef}
                  onChange={e => {
                    const file = e.target.files?.[0] || null
                    if (
                      file
                      && (
                        !file.name.toLowerCase().endsWith('.pdf')
                        || file.type !== 'application/pdf'
                      )
                    ) {
                      setCwFile(null)
                      setCwMsg('V1 运营入口只接受浏览器识别为 PDF 的 .pdf 文件')
                      e.currentTarget.value = ''
                      return
                    }
                    setCwMsg('')
                    setCwFile(file)
                  }} />
              </div>
              <button className="btn btn-primary" onClick={upload}
                disabled={!cwTitle || !cwFile || cwUploading}>
                {cwUploading ? '上传中…' : '上传'}
              </button>
              {cwMsg && <p style={{ marginTop: '12px', fontSize: '0.85rem', color: 'var(--accent-red)' }}>{cwMsg}</p>}
            </div>

            <div className="admin-courseware-heading">
              <div>
                <h2>当前课件</h2>
                <p>核对课件信息，错误上传可在这里撤销。</p>
              </div>
              <button
                className="btn btn-outline btn-sm"
                onClick={() => void loadCourseware()}
                disabled={cwListLoading || deletingCoursewareId !== null}
              >
                {cwListLoading ? '刷新中…' : '刷新列表'}
              </button>
            </div>

            {cwActionError && (
              <div className="list-feedback list-feedback-error">
                <p>{cwActionError}</p>
                <button
                  className="btn btn-outline btn-sm"
                  onClick={() => void loadCourseware()}
                  disabled={cwListLoading || deletingCoursewareId !== null}
                >
                  手动刷新
                </button>
              </div>
            )}

            {!cwListLoaded ? (
              cwListLoading ? (
                <div className="loading" />
              ) : (
                <div className="list-feedback list-feedback-error">
                  <p>{cwListError}</p>
                  <button className="btn btn-outline btn-sm" onClick={() => void loadCourseware()}>
                    重新加载
                  </button>
                </div>
              )
            ) : (
              <>
                {cwListError && (
                  <div className="list-feedback list-feedback-error">
                    <p>{cwListError}</p>
                    <button className="btn btn-outline btn-sm" onClick={() => void loadCourseware()}>
                      重试
                    </button>
                  </div>
                )}

                {courseware.length === 0 ? (
                  <div className="empty">
                    <p style={{ fontWeight: 500 }}>暂无课件</p>
                  </div>
                ) : (
                  <div className="admin-courseware-list">
                    {courseware.map(item => {
                      const file = getCoursewareFile(item)
                      return (
                        <div key={item.id} className="card admin-courseware-item">
                          <div className="admin-courseware-info">
                            <h3>{item.title}</h3>
                            <div className="admin-courseware-meta">
                              <span className="tag">内部日期：{item.date}</span>
                              {item.tags?.split(/[,，]/).filter(Boolean).map(tag => (
                                <span key={tag} className="tag">{tag.trim()}</span>
                              ))}
                            </div>
                            <p className="admin-courseware-file">
                              <strong>{file.fileType}</strong>
                              {file.fileName || '文件信息不可用'}
                            </p>
                          </div>
                          <button
                            className="btn btn-danger btn-sm"
                            onClick={() => void deleteCourseware(item)}
                            disabled={deletingCoursewareId !== null}
                          >
                            {deletingCoursewareId === item.id ? '删除中…' : '删除'}
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default Admin
