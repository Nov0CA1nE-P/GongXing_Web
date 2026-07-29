import { useState, useEffect } from 'react'
import { API_BASE_URL } from '../config/runtime'
import { getPublicApiError, publicRequest } from '../config/publicApi'

interface Reply { id: number; author: string; content: string; created_at: string; reactions: string }
interface Msg { id: number; author: string; content: string; created_at: string; replies: Reply[]; reactions: string }

const EMOJIS = ['👍', '❤️', '😄', '🎉', '😢', '🔥', '💡', '👏']

export default function Guestbook() {
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [loading, setLoading] = useState(true)
  const [author, setAuthor] = useState('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [replyTo, setReplyTo] = useState<number | null>(null)
  const [rAuthor, setRAuthor] = useState('')
  const [rContent, setRContent] = useState('')
  const [toast, setToast] = useState('')
  const [toastError, setToastError] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const fetchMsgs = (p = 1) => {
    fetch(`${API_BASE_URL}/guestbook/messages?page=${p}`)
      .then(r => r.json())
      .then(d => { setMsgs(d.messages); setTotal(d.total); setLoading(false) })
      .catch(() => setLoading(false))
  }
  useEffect(() => { fetchMsgs() }, [])

  const showToast = (m: string, error = false) => {
    setToastError(error)
    setToast(m)
    setTimeout(() => setToast(''), 2800)
  }

  const submit = async (pid: number | null = null) => {
    const text = pid ? rContent : content
    if (!text.trim()) return
    setSubmitting(true)
    try {
      const name = pid ? (rAuthor.trim() || '匿名') : (author.trim() || '匿名')
      const response = await publicRequest('/guestbook/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ author: name, content: text.trim(), parent_id: pid }),
      })
      if (!response.ok) {
        showToast(
          await getPublicApiError(response, '留言失败，请稍后再试'),
          true,
        )
        return
      }
      if (pid) { setReplyTo(null); setRContent(''); setRAuthor('') }
      else { setContent(''); setAuthor('') }
      fetchMsgs(page)
      showToast('留言成功 ✨')
    } catch {
      showToast('网络错误，请稍后再试', true)
    } finally { setSubmitting(false) }
  }

  const totalPages = Math.ceil(total / 20)

  if (loading) return <div className="loading" />

  return (
    <div>
      {toast && <div className={`toast ${toastError ? 'toast-error' : 'toast-success'}`}>{toast}</div>}

      <div className="page-header">
        <h1>留言板</h1>
        <p>写下你对课程和实践活动的感想与反馈</p>
      </div>

      <div className="container">
        {/* 写留言 */}
        <div className="card" style={{
          marginBottom: '36px',
          background: 'linear-gradient(135deg, var(--paper) 0%, var(--cream) 100%)',
        }}>
          <div className="section-title">写留言</div>
          <div className="form-group">
            <input value={author} onChange={e => setAuthor(e.target.value)}
              placeholder="你的昵称（可选）" />
          </div>
          <div className="form-group">
            <textarea value={content} onChange={e => setContent(e.target.value)}
              placeholder="分享你的想法与感受……" />
          </div>
          <button className="btn btn-primary" onClick={() => submit()}
            disabled={submitting || !content.trim()}>
            ✉️ {submitting ? '发表中…' : '发表留言'}
          </button>
        </div>

        {/* 装饰分隔 */}
        <div className="ornament"><span>✦ 大家的留言 ✦</span></div>

        {msgs.length === 0 ? (
          <div className="empty">
            <div style={{ fontSize: '3rem', marginBottom: '12px' }}>💭</div>
            <p style={{ fontWeight: 600 }}>还没有留言</p>
            <p style={{ color: 'var(--ink-lighter)', fontSize: '0.85rem' }}>
              来做第一个发言的人吧
            </p>
          </div>
        ) : (
          <>
            {msgs.map((m, i) => (
              <div key={m.id} className="card" style={{
                animation: `fadeIn 0.4s ${i * 50}ms both`,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{
                      width: '34px', height: '34px', borderRadius: '50%',
                      background: 'linear-gradient(135deg, var(--accent-glow), var(--gold-light))',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: '0.8rem', fontWeight: 700, color: 'var(--accent)',
                    }}>
                      {m.author[0]}
                    </div>
                    <div>
                      <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{m.author}</span>
                      <span style={{ color: 'var(--ink-lighter)', fontSize: '0.74rem', marginLeft: '8px' }}>
                        {new Date(m.created_at).toLocaleString('zh-CN')}
                      </span>
                    </div>
                  </div>
                </div>

                <p style={{
                  marginTop: '16px', fontSize: '0.93rem',
                  lineHeight: 1.75, whiteSpace: 'pre-wrap',
                }}>
                  {m.content}
                </p>

                {/* 表情反应 */}
                <ReactionBar
                  msgId={m.id}
                  reactions={m.reactions}
                  onReacted={() => fetchMsgs(page)}
                  onError={message => showToast(message, true)}
                />

                {/* 回复 */}
                {m.replies.map(rp => (
                  <div key={rp.id} style={{
                    marginTop: '14px', marginLeft: '16px',
                    padding: '14px 18px', background: 'var(--cream-dark)',
                    borderRadius: 'var(--radius-sm)', borderLeft: '3px solid var(--accent)',
                  }}>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '4px' }}>
                      <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>{rp.author}</span>
                      <span style={{ color: 'var(--ink-lighter)', fontSize: '0.72rem' }}>
                        {new Date(rp.created_at).toLocaleString('zh-CN')}
                      </span>
                    </div>
                    <p style={{ fontSize: '0.87rem', lineHeight: 1.65 }}>{rp.content}</p>
                  </div>
                ))}

                {replyTo === m.id ? (
                  <div style={{ marginTop: '14px', marginLeft: '16px' }}>
                    <input
                      value={rAuthor} onChange={e => setRAuthor(e.target.value)}
                      placeholder="你的昵称（可选）"
                      style={{
                        width: '100%', padding: '8px 12px', marginBottom: '8px',
                        border: '1px solid var(--border)', borderRadius: '8px',
                        fontSize: '0.85rem', background: 'var(--paper)',
                      }}
                    />
                    <textarea
                      value={rContent} onChange={e => setRContent(e.target.value)}
                      placeholder="写下回复……"
                      style={{
                        width: '100%', padding: '10px 12px', borderRadius: '8px',
                        border: '1px solid var(--border)', fontSize: '0.85rem',
                        minHeight: '60px', resize: 'vertical', background: 'var(--paper)',
                      }}
                    />
                    <div style={{ marginTop: '8px', display: 'flex', gap: '8px' }}>
                      <button className="btn btn-primary btn-sm" onClick={() => submit(m.id)}
                        disabled={submitting || !rContent.trim()}>回复</button>
                      <button className="btn btn-outline btn-sm"
                        onClick={() => { setReplyTo(null); setRContent(''); setRAuthor('') }}>取消</button>
                    </div>
                  </div>
                ) : (
                  <button className="btn btn-ghost btn-sm" style={{ marginTop: '10px' }}
                    onClick={() => setReplyTo(m.id)}>💬 回复</button>
                )}
              </div>
            ))}

            {totalPages > 1 && (
              <div style={{
                textAlign: 'center', marginTop: '28px',
                display: 'flex', gap: '8px', justifyContent: 'center',
              }}>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                  <button key={p}
                    className={`btn btn-sm ${p === page ? 'btn-primary' : 'btn-outline'}`}
                    onClick={() => { setPage(p); fetchMsgs(p) }}>
                    {p}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}

// 表情反应组件
function ReactionBar({ msgId, reactions, onReacted, onError }: {
  msgId: number
  reactions: string
  onReacted: () => void
  onError: (message: string) => void
}) {
  const [loading, setLoading] = useState(false)
  const parsed: Record<string, number> = (() => { try { return JSON.parse(reactions || '{}') } catch { return {} } })()

  const react = async (emoji: string) => {
    if (loading) return
    setLoading(true)
    try {
      const response = await publicRequest(
        `/guestbook/messages/${msgId}/react?emoji=${encodeURIComponent(emoji)}`,
        { method: 'POST' },
      )
      if (!response.ok) {
        onError(await getPublicApiError(response, '表情操作失败，请稍后再试'))
        return
      }
      onReacted()
    } catch {
      onError('网络错误，请稍后再试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '4px', marginTop: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
      {EMOJIS.map(e => (
        <button key={e} onClick={() => react(e)}
          disabled={loading}
          style={{
            background: (parsed[e] || 0) > 0 ? 'var(--accent-glow)' : 'transparent',
            border: '1px solid ' + ((parsed[e] || 0) > 0 ? 'transparent' : 'var(--border-light)'),
            borderRadius: '16px', padding: '4px 10px',
            fontSize: '0.82rem', cursor: 'pointer',
            transition: 'all 0.2s',
            display: 'inline-flex', alignItems: 'center', gap: '3px',
          }}>
          {e}
          {(parsed[e] || 0) > 0 && (
            <span style={{ fontSize: '0.68rem', fontWeight: 600, color: 'var(--accent)' }}>
              {parsed[e]}
            </span>
          )}
        </button>
      ))}
    </div>
  )
}
