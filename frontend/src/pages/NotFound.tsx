import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div>
      <div className="page-header">
        <h1>页面暂未开放</h1>
        <p>该功能不在网站 V1 公开范围内，或页面地址不存在。</p>
      </div>
      <div className="container" style={{ maxWidth: '620px', textAlign: 'center' }}>
        <div className="card" style={{ padding: '40px 28px' }}>
          <p style={{ color: 'var(--ink-light)', marginBottom: '22px' }}>
            你可以返回首页，继续浏览当前已经开放的内容。
          </p>
          <Link to="/" className="btn btn-primary">返回首页</Link>
        </div>
      </div>
    </div>
  )
}
