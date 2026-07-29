import { useState, useEffect, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import { API_BASE_URL } from '../config/runtime'
import { getPublicApiError, publicRequest } from '../config/publicApi'
import { loadJson } from '../config/listApi'

interface QA {
  id: number; author: string; content: string; created_at: string
  answer?: { id: number; content: string; status?: string; likes: number }
}

interface QuestionPage { questions: QA[] }

function isAnswer(value: unknown): value is NonNullable<QA['answer']> {
  if (!value || typeof value !== 'object') return false
  const answer = value as Record<string, unknown>
  return (
    Number.isInteger(answer.id)
    && typeof answer.content === 'string'
    && typeof answer.likes === 'number'
    && Number.isFinite(answer.likes)
    && (answer.status === undefined || typeof answer.status === 'string')
  )
}

function isQuestion(value: unknown): value is QA {
  if (!value || typeof value !== 'object') return false
  const question = value as Record<string, unknown>
  return (
    Number.isInteger(question.id)
    && typeof question.author === 'string'
    && typeof question.content === 'string'
    && typeof question.created_at === 'string'
    && (question.answer === undefined || isAnswer(question.answer))
  )
}

function isQuestionPage(value: unknown): value is QuestionPage {
  if (!value || typeof value !== 'object') return false
  const page = value as Record<string, unknown>
  return Array.isArray(page.questions) && page.questions.every(isQuestion)
}

const getViewed = (): number[] => {
  try { return JSON.parse(localStorage.getItem('qa_viewed') || '[]') } catch { return [] }
}
const markViewed = (id: number) => {
  const v = getViewed(); if (!v.includes(id)) { v.push(id); localStorage.setItem('qa_viewed', JSON.stringify(v)) }
}

// 简单关键词提取
function extractKeywords(text: string): string[] {
  const stopWords = new Set(['的','是','我','你','他','她','它','们','了','在','有','不','和','就','都','也','要','会','可以','这个','那个','什么','怎么','为什么','因为','所以','但是','如果','一个','一种','这个','哪个','还是','比较','之间','没有','觉得','想','学','知道','了解'])
  const words = text.replace(/[，。！？、；：""''（）\n\r]/g, ' ').split(/\s+/).filter(w => w.length >= 2 && !stopWords.has(w))
  return [...new Set(words)].slice(0, 6)
}

export default function QandA() {
  const [questions, setQuestions] = useState<QA[]>([])
  const [loading, setLoading] = useState(true)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [listError, setListError] = useState('')
  const [author, setAuthor] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitMsg, setSubmitMsg] = useState('')
  const [search, setSearch] = useState('')
  const [tab, setTab] = useState<'all' | 'my'>('all')
  const [myName, setMyName] = useState(localStorage.getItem('qa_author') || '')
  const [toast, setToast] = useState('')
  const [toastError, setToastError] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [followUps, setFollowUps] = useState<Record<number, any[]>>({})
  const [followUpQ, setFollowUpQ] = useState<Record<number, string>>({})
  const [followUpAuthor, setFollowUpAuthor] = useState<Record<number, string>>({})
  const [submittingFollowUp, setSubmittingFollowUp] = useState<Record<number, boolean>>({})
  const [likedIds, setLikedIds] = useState<number[]>(() => {
    try { return JSON.parse(localStorage.getItem('qa_liked') || '[]') } catch { return [] }
  })
  const requestIdRef = useRef(0)
  const requestControllerRef = useRef<AbortController | null>(null)

  const fetchQ = async (): Promise<'success' | 'failed' | 'ignored'> => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    setLoading(true)
    setListError('')

    const result = await loadJson(
      {
        request: signal => publicRequest('/qanda/questions', { signal }),
        validate: isQuestionPage,
        getHttpError: response => getPublicApiError(
          response,
          '问答服务暂时不可用，请稍后重试',
        ),
        invalidMessage: '服务器返回的问答数据格式异常，请稍后重试',
        networkMessage: '无法连接问答服务，请检查网络后重试',
      },
      controller.signal,
    )

    if (
      requestId !== requestIdRef.current
      || (!result.ok && result.kind === 'aborted')
    ) {
      return 'ignored'
    }

    if (result.ok) {
      setQuestions(result.data.questions)
      setHasLoaded(true)
      setLoading(false)
      return 'success'
    }

    setListError(result.message)
    setLoading(false)
    return 'failed'
  }
  useEffect(() => {
    void fetchQ()
    return () => {
      requestIdRef.current += 1
      requestControllerRef.current?.abort()
    }
  }, [])

  const showToast = (m: string, error = false) => {
    setToastError(error)
    setToast(m)
    setTimeout(() => setToast(''), 2800)
  }

  const submit = async () => {
    if (!content.trim()) return
    setSubmitting(true); setSubmitMsg('')
    try {
      const name = author.trim() || '匿名'
      const r = await publicRequest('/qanda/questions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author: name, content: content.trim() }),
      })
      if (r.ok) {
        setSubmitMsg('问题已提交，审核通过后即可查看回答。')
        setContent(''); setMyName(name); setTab('my')
        localStorage.setItem('qa_author', name)
        showToast('已提交 ✨')
      } else setSubmitMsg(await getPublicApiError(r, '提交失败，请稍后再试。'))
    } catch {
      setSubmitMsg('网络错误，请稍后再试。')
    } finally { setSubmitting(false) }
  }

  // 加载追问
  const loadFollowUps = async (qid: number) => {
    if (followUps[qid]) return
    try {
      const r = await fetch(`${API_BASE_URL}/qanda/questions/${qid}/follow-ups`)
      if (r.ok) {
        const data = await r.json()
        setFollowUps(prev => ({ ...prev, [qid]: data }))
      }
    } catch {}
  }

  // 提交追问
  const submitFollowUp = async (qid: number) => {
    const text = followUpQ[qid] || ''
    if (!text.trim()) return
    setSubmittingFollowUp(prev => ({ ...prev, [qid]: true }))
    try {
      const name = followUpAuthor[qid]?.trim() || '匿名'
      const response = await publicRequest(`/qanda/questions/${qid}/follow-ups`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author: name, content: text.trim() }),
      })
      if (!response.ok) {
        showToast(
          await getPublicApiError(response, '追问提交失败，请稍后再试'),
          true,
        )
        return
      }
      setFollowUpQ(prev => ({ ...prev, [qid]: '' }))
      setFollowUpAuthor(prev => ({ ...prev, [qid]: '' }))
      showToast('追问已提交，审核通过后可见 ✨')
    } catch {
      showToast('网络错误，请稍后再试', true)
    } finally {
      setSubmittingFollowUp(prev => ({ ...prev, [qid]: false }))
    }
  }

  const doLike = async (answerId: number) => {
    if (likedIds.includes(answerId)) return
    try {
      const r = await publicRequest(`/qanda/answers/${answerId}/like`, { method: 'POST' })
      if (r.ok) {
        const data = await r.json()
        setLikedIds(prev => { const n = [...prev, answerId]; localStorage.setItem('qa_liked', JSON.stringify(n)); return n })
        setQuestions(prev => prev.map(q => q.answer?.id === answerId ? { ...q, answer: { ...q.answer!, likes: data.likes } } : q))
      } else {
        showToast(await getPublicApiError(r, '点赞失败，请稍后再试'), true)
      }
    } catch {
      showToast('网络错误，请稍后再试', true)
    }
  }

  const viewed = getViewed()
  let filtered = questions
  if (search.trim()) {
    const kw = search.toLowerCase()
    filtered = filtered.filter(q => q.content.toLowerCase().includes(kw) || q.answer?.content.toLowerCase().includes(kw))
  }
  if (tab === 'my' && myName) filtered = filtered.filter(q => q.author === myName)

  // 相关问题推荐
  const relatedQuestions = useMemo(() => {
    if (!expandedId) return []
    const current = questions.find(q => q.id === expandedId)
    if (!current) return []
    const keywords = extractKeywords(current.content)
    if (keywords.length === 0) return []
    return questions
      .filter(q => q.id !== expandedId)
      .map(q => {
        const score = keywords.reduce((s, kw) => s + (q.content.includes(kw) ? 1 : 0) + ((q.answer?.content || '').includes(kw) ? 1 : 0), 0)
        return { ...q, score }
      })
      .filter(q => q.score >= 1)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
  }, [expandedId, questions])

  return (
    <div>
      {toast && <div className={`toast ${toastError ? 'toast-error' : 'toast-success'}`}>{toast}</div>}

      <div className="page-header">
        <h1>专业问答</h1>
        <p>有任何关于大学专业的困惑，尽管写下来。即使描述不清楚也没关系。</p>
      </div>

      <div className="container">
        {/* 提问 */}
        <div className="card" style={{ marginBottom: '40px', background: 'linear-gradient(135deg, var(--paper) 0%, var(--cream) 100%)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <span style={{ fontSize: '1.6rem' }}>💡</span>
            <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.15rem', fontWeight: 700, color: 'var(--ink)' }}>提出你的疑问</h2>
          </div>
          <p style={{ color: 'var(--ink-light)', fontSize: '0.86rem', marginBottom: '20px', lineHeight: 1.6 }}>
            不需要准确描述——想到什么就写什么。我们的智能大模型会帮你理清思路。
          </p>
          <div className="form-group">
            <input value={author} onChange={e => setAuthor(e.target.value)} placeholder="你的昵称（可选）" />
          </div>
          <div className="form-group">
            <textarea value={content} onChange={e => setContent(e.target.value)}
              placeholder="写下你的困惑……越详细，回答越精准" style={{ minHeight: '140px' }} />
          </div>
          <button className="btn btn-primary" onClick={submit} disabled={submitting || !content.trim()}>
            💡 {submitting ? '提交中…' : '提交问题'}
          </button>
          {submitMsg && <div className="blockquote-decorated" style={{ marginTop: '14px' }}>{submitMsg}</div>}
        </div>

        {/* 标签 + 搜索 */}
        <div className="qanda-list-toolbar">
          <div className="tab-bar qanda-list-tabs">
            <button className={`tab-btn ${tab === 'all' ? 'active' : ''}`} onClick={() => setTab('all')}>全部问答</button>
            <button className={`tab-btn ${tab === 'my' ? 'active' : ''}`} onClick={() => setTab('my')}>我的提问</button>
          </div>
          <div className="qanda-list-search">
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="🔍 搜索问答" style={{ width: '100%', padding: '8px 16px', border: '1.5px solid var(--border)', borderRadius: '24px', fontSize: '0.84rem', background: 'var(--paper)' }} />
            <button
              className="btn btn-outline btn-sm"
              onClick={() => void fetchQ()}
              disabled={loading}
            >
              {loading ? '刷新中…' : '刷新'}
            </button>
          </div>
        </div>

        {/* 列表 */}
        {!hasLoaded ? (
          loading ? (
            <div className="loading" />
          ) : (
            <div className="list-feedback list-feedback-error">
              <p>{listError}</p>
              <button className="btn btn-outline btn-sm" onClick={() => void fetchQ()}>
                重新加载
              </button>
            </div>
          )
        ) : (
          <>
            {(listError || loading) && (
              <div className={`list-feedback ${listError ? 'list-feedback-error' : ''}`}>
                <p>{listError || '正在刷新问答列表…'}</p>
                {listError && (
                  <button className="btn btn-outline btn-sm" onClick={() => void fetchQ()}>
                    重试
                  </button>
                )}
              </div>
            )}

            {filtered.length === 0 ? (
              <div className="empty">
                <div style={{ fontSize: '3rem', marginBottom: '12px' }}>{search ? '🔍' : tab === 'my' ? '📝' : '🤔'}</div>
                <p style={{ fontWeight: 600 }}>{search ? '没有匹配的结果' : tab === 'my' ? '你还没有提问' : '暂无已发布的问答'}</p>
              </div>
            ) : (
              filtered.map(q => {
                const isNew = !viewed.includes(q.id) && !!q.answer
                const isExpanded = expandedId === q.id
                return (
              <div key={q.id} className="card" onClick={() => { if (isNew) markViewed(q.id); setExpandedId(isExpanded ? null : q.id); if (!isExpanded) loadFollowUps(q.id) }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
                  <div style={{ width: '34px', height: '34px', borderRadius: '50%', background: 'linear-gradient(135deg, var(--green-light), var(--green-glow))', color: 'var(--green)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.78rem', fontWeight: 700 }}>
                    {q.author[0]}
                  </div>
                  <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{q.author}</span>
                  {isNew && <span className="notify-dot" />}
                  <span style={{ color: 'var(--ink-lighter)', fontSize: '0.76rem', marginLeft: 'auto' }}>
                    {new Date(q.created_at).toLocaleDateString('zh-CN')}
                  </span>
                </div>

                <div style={{ background: 'var(--cream-dark)', padding: '16px 20px', borderRadius: 'var(--radius-sm)', fontSize: '0.93rem', lineHeight: 1.7, marginBottom: '20px', whiteSpace: 'pre-wrap', position: 'relative' }}>
                  {q.content}
                  <div style={{ position: 'absolute', bottom: '-8px', left: '20px', width: '16px', height: '16px', background: 'var(--cream-dark)', transform: 'rotate(45deg)' }} />
                </div>

                {q.answer && (
                  <div style={{ background: 'var(--paper)', border: '1px solid var(--green-light)', borderRadius: 'var(--radius)', padding: '24px', position: 'relative' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{ width: '26px', height: '26px', borderRadius: '8px', background: 'linear-gradient(135deg, var(--green), #7CB87A)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.68rem', fontWeight: 700 }}>AI</div>
                        <span style={{ fontWeight: 700, fontSize: '0.84rem', color: 'var(--green)' }}>躬行启杭智能大模型</span>
                      </div>
                      <button
                        className={`btn btn-sm ${likedIds.includes(q.answer.id) ? 'btn-primary' : 'btn-outline'}`}
                        onClick={(e) => { e.stopPropagation(); doLike(q.answer!.id) }}
                        disabled={likedIds.includes(q.answer.id)}
                        title={likedIds.includes(q.answer.id) ? '已点赞' : '有用'}>
                        ❤️ {q.answer.likes || 0}
                      </button>
                    </div>
                    <div className="markdown-body">
                      <ReactMarkdown>{q.answer.content}</ReactMarkdown>
                    </div>
                  </div>
                )}

                {/* 追问 */}
                {isExpanded && (
                  <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '2px dotted var(--border)' }}>
                    {/* 已有追问 */}
                    {followUps[q.id] && followUps[q.id].map((fu: any) => (
                      <div key={fu.id} style={{
                        marginBottom: '14px', padding: '16px 20px',
                        background: 'var(--cream-dark)', borderRadius: 'var(--radius-sm)',
                        borderLeft: '3px solid var(--accent)',
                      }}>
                        <div style={{ marginBottom: '8px' }}>
                          <span style={{ fontWeight: 600, fontSize: '0.85rem', color: 'var(--accent)' }}>
                            {fu.author} 追问：
                          </span>
                          <span style={{ color: 'var(--ink-lighter)', fontSize: '0.72rem', marginLeft: '8px' }}>
                            {new Date(fu.created_at).toLocaleDateString('zh-CN')}
                          </span>
                        </div>
                        <p style={{ fontSize: '0.88rem', lineHeight: 1.6, marginBottom: '12px' }}>
                          {fu.content}
                        </p>
                        {fu.answer_content && (
                          <div style={{
                            background: 'white', borderRadius: 'var(--radius-sm)',
                            padding: '14px 18px',
                          }}>
                            <div style={{ fontWeight: 600, fontSize: '0.78rem', color: 'var(--green)', marginBottom: '6px' }}>
                              躬行启杭智能大模型 回答：
                            </div>
                            <div className="markdown-body" style={{ fontSize: '0.85rem' }}>
                              <ReactMarkdown>{fu.answer_content}</ReactMarkdown>
                            </div>
                          </div>
                        )}
                      </div>
                    ))}

                    {/* 追问输入 */}
                    <div style={{ marginTop: '14px' }}>
                      <input
                        value={followUpAuthor[q.id] || ''}
                        onChange={e => setFollowUpAuthor(prev => ({ ...prev, [q.id]: e.target.value }))}
                        placeholder="你的昵称（可选）"
                        style={{
                          width: '100%', padding: '8px 12px', marginBottom: '8px',
                          border: '1px solid var(--border)', borderRadius: '8px',
                          fontSize: '0.84rem', background: 'var(--paper)',
                        }}
                      />
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <input
                          value={followUpQ[q.id] || ''}
                          onChange={e => setFollowUpQ(prev => ({ ...prev, [q.id]: e.target.value }))}
                          placeholder="还有疑问？继续追问..."
                          style={{
                            flex: 1, padding: '9px 14px',
                            border: '1.5px solid var(--border)', borderRadius: '24px',
                            fontSize: '0.85rem', background: 'var(--paper)',
                          }}
                          onKeyDown={e => { if (e.key === 'Enter') submitFollowUp(q.id) }}
                        />
                        <button className="btn btn-primary btn-sm"
                          onClick={(e) => { e.stopPropagation(); submitFollowUp(q.id) }}
                          disabled={submittingFollowUp[q.id] || !(followUpQ[q.id] || '').trim()}>
                          追问
                        </button>
                      </div>
                    </div>
                  </div>
                )}

                {/* 相关问题推荐 */}
                {isExpanded && relatedQuestions.length > 0 && (
                  <div style={{ marginTop: '20px', paddingTop: '20px', borderTop: '2px dotted var(--border)' }}>
                    <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--ink-light)', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                      💡 相关问题
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {relatedQuestions.map(rq => (
                        <button key={rq.id} className="btn btn-ghost btn-sm"
                          onClick={(e) => { e.stopPropagation(); setExpandedId(rq.id); }}
                          style={{ textAlign: 'left', justifyContent: 'flex-start', fontSize: '0.84rem', color: 'var(--blue)' }}>
                          {rq.content.slice(0, 60)}{rq.content.length > 60 ? '…' : ''}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
                )
              })
            )}
          </>
        )}
      </div>
    </div>
  )
}
