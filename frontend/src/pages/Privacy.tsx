import { useState } from 'react'
import { Link } from 'react-router-dom'

const LOCAL_STORAGE_KEYS = [
  'cw_viewed',
  'qa_viewed',
  'qa_author',
  'qa_liked',
]

export default function Privacy() {
  const [clearMessage, setClearMessage] = useState('')

  const clearLocalRecords = () => {
    LOCAL_STORAGE_KEYS.forEach(key => localStorage.removeItem(key))
    setClearMessage(
      '已删除课件查看、问答查看、问答昵称和点赞记录。'
      + '此操作不会清除 HttpOnly Cookie 或服务器数据。',
    )
  }

  return (
    <div>
      <div className="page-header">
        <h1>隐私说明</h1>
        <p>说明网站实际收集、公开和处理的信息</p>
      </div>
      <div className="container" style={{ maxWidth: '820px' }}>
        <div className="card" style={{ padding: '32px' }}>
          <h2 className="section-title">联系表单</h2>
          <p>
            联系表单保存称呼、选填联系方式、留言内容和提交时间，仅管理员可以查看。
            系统按提交后90天的规则自动清理；服务停机或发生故障时可能延迟，恢复后会补清。
          </p>
          <p>
            你可以通过同一表单提出删除申请，并提供大致提交时间、当时的称呼和内容线索。
            不需要提供身份证件；管理员删除原记录后，也会删除申请记录。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>公开互动内容</h2>
          <p>
            留言、回复、昵称、发布时间和反应数量会公开展示。专业问题、追问及AI回答进入网站数据库，
            只有经过管理员审核的问答内容才公开。上述公开内容目前没有固定自动保存期限，
            可以通过联系表单申请处理。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>第三方AI</h2>
          <p>
            首次专业问答只向 DeepSeek 发送问题正文。追问会发送当前追问、原问题、已发布回答及最近5条
            已发布追问上下文。网站不会主动把昵称、联系方式、访客Cookie、管理员Cookie或用户IP放入
            AI请求体。AI内容可能出错，人工审核也不能保证绝对准确，仅供参考。
          </p>
          <p>
            AI趣味测试的50道原始选择只存在当前页面内存。前端仅提交六维分数，后端转换为六维百分比提示
            后发送 DeepSeek；当前网站数据库不保存原始选择、六维结果或分析报告。DeepSeek可能按其自身
            规则处理请求并保留技术日志，本站无法承诺第三方不存在日志。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>Cookie与防刷</h2>
          <p>
            <code>visitor_rl</code> 是没有显式 Max-Age 或 Expires 的会话Cookie，内容是签名随机标识，
            不含姓名或表单内容。24小时是当前最长限流窗口，不是Cookie的固定有效期。后端重启后旧Cookie
            无法继续验证，并会在下一次公开写请求时轮换。
          </p>
          <p>
            管理员会话Cookie使用 HttpOnly、SameSite=Strict 和 Path=/api，只保存随机令牌，不含密码。
            会话有效期由配置决定，当前默认值为2小时；后端重启后服务端会话失效。关闭浏览器不等同于可靠退出。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>浏览器本地记录</h2>
          <p>
            浏览器会保存最近查看的课件ID、已查看问答ID、问答昵称和已点赞回答ID。这些记录没有自动到期时间。
          </p>
          <button className="btn btn-outline" onClick={clearLocalRecords}>
            清除此网站本地记录
          </button>
          {clearMessage && (
            <p style={{ marginTop: '12px', color: 'var(--green)', fontSize: '0.86rem' }}>
              {clearMessage}
            </p>
          )}
          <p style={{ marginTop: '10px', fontSize: '0.82rem', color: 'var(--ink-lighter)' }}>
            该按钮只删除 cw_viewed、qa_viewed、qa_author、qa_liked 四个 localStorage 键；
            不会清除 HttpOnly Cookie、公开内容、联系记录或其他服务器数据。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>访问日志与第三方脚本</h2>
          <p>
            当前应用没有广告和第三方统计脚本。应用服务器及未来的反向代理可能处理IP、请求时间、路径和状态码等
            基础访问日志。本项目尚未完成正式反向代理部署，因此暂不虚构最终日志保存期限；部署时需要确定并同步更新本说明。
          </p>

          <h2 className="section-title" style={{ marginTop: '30px' }}>重要边界</h2>
          <p>
            本网站不宣称通过正式法律认证、等保认证，也不提供专业心理测评、能力测评或升学诊断。
            请勿在公开互动或联系表单中提交身份证号、家庭住址等敏感信息。
          </p>

          <div style={{ marginTop: '28px' }}>
            <Link to="/contact" className="btn btn-primary">联系实践团或申请删除</Link>
          </div>
        </div>
      </div>
    </div>
  )
}
