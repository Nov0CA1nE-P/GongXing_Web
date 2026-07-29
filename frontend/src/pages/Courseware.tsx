import { useState, useEffect, useRef } from 'react'
import { getUploadedFileUrl } from '../config/runtime'
import { getPublicApiError, publicRequest } from '../config/publicApi'
import { loadJson } from '../config/listApi'
import { isCoursewareList, type CoursewareItem } from '../types/courseware'

const ALL_TAGS = ['全部', '机械', '计算机', '材料', '自动化', '经管', '理科', '文科', '高考政策', '其他']

// 最近观看
const getViewed = (): number[] => { try { return JSON.parse(localStorage.getItem('cw_viewed') || '[]') } catch { return [] } }
const addViewed = (id: number) => {
  const v = getViewed().filter(x => x !== id)
  v.unshift(id)
  localStorage.setItem('cw_viewed', JSON.stringify(v.slice(0, 10)))
}

// PDF 模拟翻页
function PDFViewer({ url, title }: { url: string; title: string }) {
  const [page, setPage] = useState(1)
  const [totalPages] = useState(20) // 模拟总页数
  const [animating, setAnimating] = useState(false)
  const [direction, setDirection] = useState<'next' | 'prev'>('next')

  const goPage = (dir: 'next' | 'prev') => {
    if (animating) return
    if (dir === 'next' && page >= totalPages) return
    if (dir === 'prev' && page <= 1) return
    setDirection(dir)
    setAnimating(true)
    setTimeout(() => {
      setPage(p => dir === 'next' ? p + 1 : p - 1)
      setAnimating(false)
    }, 300)
  }

  return (
    <div style={{ marginTop: '20px' }}>
      {/* 翻页控制栏 */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        gap: '16px', marginBottom: '16px',
        background: 'var(--cream-dark)', borderRadius: 'var(--radius-sm)',
        padding: '10px 20px',
      }}>
        <button className="btn btn-outline btn-sm" onClick={() => goPage('prev')} disabled={page <= 1}>
          ← 上一页
        </button>
        <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--ink)', minWidth: '80px', textAlign: 'center' }}>
          第 {page} / {totalPages} 页
        </span>
        <button className="btn btn-outline btn-sm" onClick={() => goPage('next')} disabled={page >= totalPages}>
          下一页 →
        </button>
        <a href={url} target="_blank" rel="noopener noreferrer"
          className="btn btn-primary btn-sm" style={{ marginLeft: '12px' }}>
          🔗 新窗口打开
        </a>
      </div>

      {/* PDF 预览 + 翻页动画 */}
      <div style={{
        position: 'relative', overflow: 'hidden',
        border: '1px solid var(--border-light)', borderRadius: 'var(--radius)',
        height: '640px', background: '#f0ede6',
      }}>
        <div style={{
          opacity: animating ? 0 : 1,
          transform: animating ? `translateX(${direction === 'next' ? '-40px' : '40px'})` : 'translateX(0)',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          width: '100%', height: '100%',
        }}>
          <iframe
            src={`${url}#page=${page}`}
            style={{ width: '100%', height: '100%', border: 'none' }}
            title={title}
          />
        </div>

        {/* 翻页提示箭头 */}
        {page > 1 && (
          <div onClick={() => goPage('prev')} style={{
            position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)',
            width: '48px', height: '72px', background: 'rgba(255,255,255,0.85)',
            borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', fontSize: '1.4rem', color: 'var(--ink-light)',
            boxShadow: '0 2px 12px rgba(0,0,0,0.08)', transition: 'all 0.2s',
            opacity: 0.6,
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
          onMouseLeave={e => (e.currentTarget.style.opacity = '0.6')}>
            ‹
          </div>
        )}
        {page < totalPages && (
          <div onClick={() => goPage('next')} style={{
            position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)',
            width: '48px', height: '72px', background: 'rgba(255,255,255,0.85)',
            borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer', fontSize: '1.4rem', color: 'var(--ink-light)',
            boxShadow: '0 2px 12px rgba(0,0,0,0.08)', transition: 'all 0.2s',
            opacity: 0.6,
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
          onMouseLeave={e => (e.currentTarget.style.opacity = '0.6')}>
            ›
          </div>
        )}
      </div>
    </div>
  )
}

export default function Courseware() {
  const [items, setItems] = useState<CoursewareItem[]>([])
  const [loading, setLoading] = useState(true)
  const [hasLoaded, setHasLoaded] = useState(false)
  const [listError, setListError] = useState('')
  const [selected, setSelected] = useState<CoursewareItem | null>(null)
  const [activeTag, setActiveTag] = useState('全部')
  const [viewedIds] = useState(getViewed)
  const requestIdRef = useRef(0)
  const requestControllerRef = useRef<AbortController | null>(null)

  const fetchItems = async (tag = '全部') => {
    const requestId = requestIdRef.current + 1
    requestIdRef.current = requestId
    requestControllerRef.current?.abort()
    const controller = new AbortController()
    requestControllerRef.current = controller
    setLoading(true)
    setListError('')
    const path = tag && tag !== '全部'
      ? `/courseware/list?tag=${encodeURIComponent(tag)}`
      : '/courseware/list'
    const result = await loadJson(
      {
        request: signal => publicRequest(path, { signal }),
        validate: isCoursewareList,
        getHttpError: response => getPublicApiError(
          response,
          '课件服务暂时不可用，请稍后重试',
        ),
        invalidMessage: '服务器返回的课件数据格式异常，请稍后重试',
        networkMessage: '无法连接课件服务，请检查网络后重试',
      },
      controller.signal,
    )

    if (
      requestId !== requestIdRef.current
      || (!result.ok && result.kind === 'aborted')
    ) {
      return false
    }

    if (result.ok) {
      setItems(result.data)
      setActiveTag(tag)
      setHasLoaded(true)
      setLoading(false)
      return true
    }

    setListError(result.message)
    setLoading(false)
    return false
  }
  useEffect(() => {
    void fetchItems()
    return () => {
      requestIdRef.current += 1
      requestControllerRef.current?.abort()
    }
  }, [])

  const openItem = (item: CoursewareItem) => {
    setSelected(item)
    addViewed(item.id)
  }

  return (
    <div>
      <div className="page-header">
        <h1>课件展示</h1>
        <p>按日期或学科标签浏览课程课件，在线预览或下载原始文件</p>
      </div>

      <div className="container">
        {selected ? (
          <div>
            <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}
              style={{ marginBottom: '20px' }}>&larr; 返回列表</button>
            <div className="card" style={{ padding: '32px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '14px', marginBottom: '6px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '2rem' }}>📖</span>
                <div>
                  <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.3rem', fontWeight: 700 }}>
                    {selected.title}
                  </h2>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
                    <span className="tag">📅 {selected.date}</span>
                    {selected.tags && selected.tags.split(/[,，]/).map((t: string) => (
                      <span key={t} className="tag" style={{ background: 'var(--accent-glow)', color: 'var(--accent)' }}>
                        {t.trim()}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
              {selected.description && (
                <div className="blockquote-decorated" style={{ marginTop: '16px' }}>
                  {selected.description}
                </div>
              )}

              {selected.pdf_path ? (
                <PDFViewer
                  url={getUploadedFileUrl(selected.pdf_path)}
                  title={selected.title}
                />
              ) : (
                <div style={{ padding: '56px 20px', textAlign: 'center', border: '2px dashed var(--border)', borderRadius: 'var(--radius)', background: 'var(--cream-dark)', marginTop: '20px' }}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '12px' }}>📄</div>
                  <p style={{ fontWeight: 600, color: 'var(--ink-light)' }}>暂无在线预览</p>
                  <p style={{ color: 'var(--ink-lighter)', fontSize: '0.85rem' }}>PPT 需转换为 PDF 后方可预览</p>
                </div>
              )}

              {selected.pptx_path && (
                <div style={{ marginTop: '20px', textAlign: 'center' }}>
                  <a href={getUploadedFileUrl(selected.pptx_path)}
                    className="btn btn-primary" download>
                    📥 下载原始课件
                  </a>
                </div>
              )}
            </div>
          </div>
        ) : (
          <>
            {!hasLoaded ? (
              loading ? (
                <div className="loading" />
              ) : (
                <div className="list-feedback list-feedback-error">
                  <p>{listError}</p>
                  <button className="btn btn-outline btn-sm" onClick={() => void fetchItems(activeTag)}>
                    重新加载
                  </button>
                </div>
              )
            ) : (
              <>
                {(listError || loading) && (
                  <div className={`list-feedback ${listError ? 'list-feedback-error' : ''}`}>
                    <p>{listError || '正在刷新课件列表…'}</p>
                    {listError && (
                      <button className="btn btn-outline btn-sm" onClick={() => void fetchItems(activeTag)}>
                        重试
                      </button>
                    )}
                  </div>
                )}

                <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '24px', justifyContent: 'center' }}>
                  {ALL_TAGS.map(t => (
                    <button key={t}
                      className={`btn btn-sm ${activeTag === t ? 'btn-primary' : 'btn-outline'}`}
                      onClick={() => void fetchItems(t)}
                      style={{ borderRadius: '20px' }}>
                      {t}
                    </button>
                  ))}
                </div>

                <div className="section-title" style={{ marginBottom: '20px' }}>
                  {activeTag === '全部' ? '全部课件' : `标签：${activeTag}`}
                </div>

                {items.length === 0 ? (
                  <div className="empty">
                    <div style={{ fontSize: '3rem', marginBottom: '12px' }}>📭</div>
                    <p style={{ fontWeight: 600 }}>{activeTag !== '全部' ? `暂无"${activeTag}"标签的课件` : '暂无课件'}</p>
                  </div>
                ) : (
                  items.map((item, i) => {
                    const isViewed = viewedIds.includes(item.id)
                    return (
                      <div key={item.id} className="card"
                        onClick={() => openItem(item)}
                        style={{
                          cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
                          alignItems: 'center', animation: `fadeIn 0.4s ${i * 50}ms both`,
                          ...(isViewed ? { opacity: 0.7 } : {}),
                        }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '16px', flex: 1 }}>
                          <div style={{
                            width: '48px', height: '48px', borderRadius: 'var(--radius-sm)',
                            background: 'linear-gradient(135deg, var(--accent-glow), var(--gold-light))',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            fontSize: '1.4rem', flexShrink: 0, position: 'relative',
                          }}>
                            📖
                            {isViewed && (
                              <span style={{
                                position: 'absolute', top: '-4px', right: '-4px',
                                background: 'var(--green)', color: 'white', fontSize: '0.5rem',
                                width: '16px', height: '16px', borderRadius: '50%',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                              }}>✓</span>
                            )}
                          </div>
                          <div>
                            <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1rem', fontWeight: 700, color: 'var(--ink)', marginBottom: '4px' }}>
                              {item.title}
                              {isViewed && <span style={{ fontSize: '0.7rem', color: 'var(--green)', fontWeight: 400, marginLeft: '6px' }}>已读</span>}
                            </h3>
                            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
                              <span className="tag">📅 {item.date}</span>
                              {item.tags && item.tags.split(/[,，]/).map((t: string) => (
                                <span key={t} className="tag" style={{ background: 'var(--accent-glow)', color: 'var(--accent)', fontSize: '0.7rem' }}>
                                  {t.trim()}
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
                        <span style={{ color: 'var(--ink-lighter)', fontSize: '1.2rem', fontWeight: 300, flexShrink: 0, marginLeft: '12px' }}>›</span>
                      </div>
                    )
                  })
                )}
              </>
            )}
          </>
        )}
      </div>

      <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  )
}
