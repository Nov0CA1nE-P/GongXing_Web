import { useState, useMemo } from 'react'
import { schoolScores, zhejiang2024Info } from '../data/scores'

export default function Scores() {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | '985' | '211'>('all')
  const [sortBy, setSortBy] = useState<'score' | 'name'>('score')
  const [page, setPage] = useState(1)
  const pageSize = 30

  const filtered = useMemo(() => {
    let list = [...schoolScores]
    if (typeFilter !== 'all') list = list.filter(s => s.type === typeFilter)
    if (search.trim()) {
      const kw = search.trim().toLowerCase()
      list = list.filter(s => s.name.toLowerCase().includes(kw) || s.city.includes(kw) || s.province.includes(kw))
    }
    if (sortBy === 'score') {
      list.sort((a, b) => b.minScore - a.minScore)
    } else {
      list.sort((a, b) => a.name.localeCompare(b.name, 'zh'))
    }
    return list
  }, [search, typeFilter, sortBy])

  const totalPages = Math.ceil(filtered.length / pageSize)
  const paged = filtered.slice((page - 1) * pageSize, page * pageSize)

  const scoreColor = (score: number) => {
    if (score >= 690) return '#C44A5A'
    if (score >= 660) return '#D4743A'
    if (score >= 640) return '#C8A44E'
    return '#5B8C5A'
  }

  const rankLevel = (rank: number): string => {
    if (rank <= 500) return '全省前500名'
    if (rank <= 2000) return '全省前2000名'
    if (rank <= 5000) return '全省前5000名'
    if (rank <= 10000) return '全省前10000名'
    if (rank <= 20000) return '全省前20000名'
    return '全省20000名以外'
  }

  return (
    <div>
      <div className="page-header">
        <h1>📊 高考分数线查询</h1>
        <p>985 / 211 高校 2024 年在浙江省录取分数线与位次</p>
      </div>

      <div className="container">
        {/* 数据来源声明 */}
        <div className="card" style={{
          padding: '16px 20px', marginBottom: '20px',
          background: 'linear-gradient(135deg, #FFF8F0 0%, #FFFDF8 100%)',
          border: '1px solid var(--gold-light)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '1.1rem' }}>📋</span>
            <span style={{ fontSize: '0.84rem', color: 'var(--ink)', fontWeight: 600 }}>
              数据来源：浙江省教育考试院 2024年普通类第一段平行投档分数线（官方发布）
            </span>
          </div>
          <div style={{ marginTop: '6px', fontSize: '0.76rem', color: 'var(--ink-lighter)', display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            <span>🔗 官网：www.zjzs.net</span>
            <span>📅 发布日期：2024年7月21日</span>
            <span>📊 一段线：{zhejiang2024Info.firstTierLine}分 | 特控线：{zhejiang2024Info.specialLine}分</span>
          </div>
        </div>

        {/* 筛选栏 */}
        <div className="card" style={{ padding: '20px 24px', marginBottom: '24px' }}>
          <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
            <input
              value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
              placeholder="搜索学校名称或城市..."
              style={{
                flex: '1 1 200px', padding: '9px 16px',
                border: '1.5px solid var(--border)', borderRadius: '24px',
                fontSize: '0.88rem', background: 'var(--paper)',
              }}
            />
            <div className="tab-bar" style={{ width: 'auto', flex: 0, marginBottom: 0 }}>
              {(['all', '985', '211'] as const).map(t => (
                <button key={t} className={`tab-btn ${typeFilter === t ? 'active' : ''}`}
                  onClick={() => { setTypeFilter(t); setPage(1) }}>
                  {t === 'all' ? '全部' : t}
                </button>
              ))}
            </div>
            <button className="btn btn-outline btn-sm"
              onClick={() => setSortBy(sortBy === 'score' ? 'name' : 'score')}>
              {sortBy === 'score' ? '📊 按分数' : '🔤 按名称'}
            </button>
          </div>
          <div style={{ marginTop: '10px', fontSize: '0.78rem', color: 'var(--ink-lighter)' }}>
            共 {filtered.length} 所高校 · {typeFilter === '985' ? '985工程 39所' : typeFilter === '211' ? '211工程高校' : '985/211 高校'} · 浙江省普通类第一段
            {search && <span> · 搜索"{search}"</span>}
          </div>
        </div>

        {/* 列表 */}
        {paged.length === 0 ? (
          <div className="empty">
            <div style={{ fontSize: '2rem', marginBottom: '8px' }}>🔍</div>
            <p style={{ fontWeight: 600 }}>没有匹配的高校</p>
          </div>
        ) : (
          <>
            {paged.map((school, i) => (
              <div key={school.name} className="card"
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  flexWrap: 'wrap', gap: '14px', padding: '20px 24px',
                  animation: `fadeIn 0.3s ${i * 20}ms both`,
                }}>
                {/* 左侧信息 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flex: '1 1 auto', minWidth: '200px' }}>
                  <div style={{
                    width: '44px', height: '44px', borderRadius: '12px',
                    background: scoreColor(school.minScore) + '14',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.72rem', fontWeight: 700, color: scoreColor(school.minScore),
                    flexShrink: 0,
                  }}>
                    {school.name.slice(0, 2)}
                  </div>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                      <h3 style={{ fontSize: '0.95rem', fontWeight: 700, color: 'var(--ink)' }}>
                        {school.name}
                      </h3>
                      <span className="badge" style={{
                        fontSize: '0.65rem', padding: '1px 8px',
                        background: school.type === '985' ? '#FFE8E0' : '#E8F0F8',
                        color: school.type === '985' ? '#C44A5A' : '#4A7B9D',
                        fontWeight: 600,
                      }}>
                        {school.type}
                      </span>
                    </div>
                    <div style={{ fontSize: '0.76rem', color: 'var(--ink-lighter)', marginTop: '2px' }}>
                      {school.city} · {school.province}
                      {school.avgScore && <span> · 加权平均 {school.avgScore}分</span>}
                    </div>
                  </div>
                </div>

                {/* 右侧分数数据 */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '24px', flexShrink: 0 }}>
                  <div style={{ textAlign: 'center', minWidth: '60px' }}>
                    <div style={{
                      fontFamily: 'var(--font-serif)', fontSize: '1.4rem',
                      fontWeight: 800, color: scoreColor(school.minScore), lineHeight: 1.1,
                    }}>
                      {school.minScore}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--ink-lighter)' }}>最低分</div>
                  </div>
                  <div style={{ textAlign: 'center', minWidth: '80px' }}>
                    <div style={{
                      fontFamily: 'var(--font-serif)', fontSize: '1.05rem',
                      fontWeight: 600, color: 'var(--ink)',
                    }}>
                      {school.minRank.toLocaleString()}
                    </div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--ink-lighter)' }}>最低位次</div>
                  </div>
                  <div style={{ textAlign: 'center', minWidth: '70px' }}>
                    <div style={{
                      fontSize: '0.78rem', fontWeight: 500, color: 'var(--ink-light)',
                    }}>
                      {rankLevel(school.minRank)}
                    </div>
                    <div style={{ fontSize: '0.68rem', color: 'var(--ink-lighter)' }}>竞争力</div>
                  </div>
                </div>
              </div>
            ))}

            {/* 分页 */}
            {totalPages > 1 && (
              <div style={{ textAlign: 'center', marginTop: '28px', display: 'flex', gap: '6px', justifyContent: 'center' }}>
                <button className="btn btn-outline btn-sm"
                  onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1}>
                  上一页
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1)
                  .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
                  .map((p, idx, arr) => (
                    <span key={p}>
                      {idx > 0 && arr[idx - 1] !== p - 1 && (
                        <span style={{ color: 'var(--ink-lighter)', padding: '0 2px' }}>…</span>
                      )}
                      <button className={`btn btn-sm ${p === page ? 'btn-primary' : 'btn-outline'}`}
                        onClick={() => setPage(p)}>{p}</button>
                    </span>
                  ))}
                <button className="btn btn-outline btn-sm"
                  onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages}>
                  下一页
                </button>
              </div>
            )}
          </>
        )}

        {/* 底部说明 */}
        <div style={{ marginTop: '40px', marginBottom: '48px' }}>
          <div className="card" style={{
            padding: '24px 28px', fontSize: '0.84rem', lineHeight: 1.8,
            color: 'var(--ink-light)', background: 'var(--cream-dark)',
          }}>
            <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: '1rem', fontWeight: 700, marginBottom: '12px', color: 'var(--ink)' }}>
              📖 数据说明
            </h3>
            <ul style={{ paddingLeft: '18px' }}>
              <li>以上数据来源于<strong>浙江省教育考试院</strong>2024年7月21日官方发布的《浙江省2024年普通高校招生普通类第一段平行投档分数线表》。</li>
              <li>最低分指该高校在浙江省普通类第一段所有招生专业中的<strong>最低投档分数</strong>（含中外合作办学等特殊类型）。</li>
              <li>最低位次为该最低分对应的<strong>全省排名</strong>。</li>
              <li>加权平均分（部分学校标注）综合考虑了各专业招生人数和分数。</li>
              <li>各高校的详细分专业录取分数线和位次，请访问<strong>浙江省教育考试院官网（www.zjzs.net）</strong>查询。</li>
              <li>高考分数线每年都会变化，往年数据仅供<strong>趋势参考</strong>，不能作为填报志愿的唯一依据。</li>
            </ul>

            <div style={{
              marginTop: '20px', padding: '14px 18px',
              background: 'white', borderRadius: 'var(--radius-sm)',
              display: 'flex', gap: '12px', flexWrap: 'wrap',
              justifyContent: 'center',
            }}>
              {[
                { color: '#C44A5A', label: '≥690分', desc: '清北复交级别' },
                { color: '#D4743A', label: '660-689分', desc: '顶尖985' },
                { color: '#C8A44E', label: '640-659分', desc: '中坚985' },
                { color: '#5B8C5A', label: '621-639分', desc: '985/优势211' },
              ].map(c => (
                <div key={c.label} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem' }}>
                  <span style={{
                    width: '10px', height: '10px', borderRadius: '2px',
                    background: c.color, display: 'inline-block',
                  }} />
                  <span style={{ fontWeight: 600 }}>{c.label}</span>
                  <span style={{ color: 'var(--ink-lighter)' }}>· {c.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <style>{`@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }`}</style>
    </div>
  )
}
