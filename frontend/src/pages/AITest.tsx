import { useState } from 'react'
import { Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { getPublicApiError, publicRequest } from '../config/publicApi'

// 50道测试题，分为6个维度
interface Question {
  q: string; dimension: string; options: { text: string; score: number }[]
}

const questions: Question[] = [
  // === 理科思维 (8题) ===
  { q: '你对数学证明和逻辑推理的兴趣程度？', dimension: '理科', options: [{ text: '非常喜欢，享受严谨推导', score: 4 }, { text: '比较喜欢', score: 3 }, { text: '一般', score: 2 }, { text: '不太感冒', score: 1 }] },
  { q: '看到一个物理现象（比如彩虹），你会想弄清楚背后的原理吗？', dimension: '理科', options: [{ text: '一定会，不弄清楚不舒服', score: 4 }, { text: '有时候会好奇', score: 3 }, { text: '偶尔想想', score: 2 }, { text: '不太关心', score: 1 }] },
  { q: '做化学实验时，你对操作过程和结果分析的感受？', dimension: '理科', options: [{ text: '非常享受实验过程', score: 4 }, { text: '觉得挺有意思', score: 3 }, { text: '没什么特别感觉', score: 2 }, { text: '不太喜欢做实验', score: 1 }] },
  { q: '你对公式和方程的态度是？', dimension: '理科', options: [{ text: '喜欢用公式描述世界', score: 4 }, { text: '愿意学，但不会主动钻研', score: 3 }, { text: '为了考试而学', score: 2 }, { text: '看到公式就头疼', score: 1 }] },
  { q: '如果有一道很难的数学题，你的第一反应是？', dimension: '理科', options: [{ text: '兴奋，想挑战', score: 4 }, { text: '愿意尝试', score: 3 }, { text: '有点犹豫', score: 2 }, { text: '想放弃', score: 1 }] },
  { q: '你更喜欢用数据说话还是凭感觉判断？', dimension: '理科', options: [{ text: '坚定用数据', score: 4 }, { text: '偏数据，偶尔凭感觉', score: 3 }, { text: '偏直觉，偶尔看数据', score: 2 }, { text: '主要凭直觉', score: 1 }] },
  { q: '你对抽象概念（比如无穷大、四维空间）的理解能力？', dimension: '理科', options: [{ text: '很容易理解', score: 4 }, { text: '花点时间能懂', score: 3 }, { text: '比较费劲', score: 2 }, { text: '很难理解', score: 1 }] },
  { q: '解出一个复杂问题后，你的感受是？', dimension: '理科', options: [{ text: '巨大的满足感和成就感', score: 4 }, { text: '挺开心的', score: 3 }, { text: '没什么特别感觉', score: 2 }, { text: '庆幸终于结束了', score: 1 }] },

  // === 动手实践 (8题) ===
  { q: '你喜欢动手组装或修理东西吗？（比如拼模型、修自行车）', dimension: '动手', options: [{ text: '非常喜欢，经常动手', score: 4 }, { text: '偶尔会做', score: 3 }, { text: '很少动手', score: 2 }, { text: '完全不喜欢', score: 1 }] },
  { q: '看到一件机械装置（比如钟表、发动机），你会好奇它的内部结构吗？', dimension: '动手', options: [{ text: '非常好奇，想拆开看看', score: 4 }, { text: '有点好奇', score: 3 }, { text: '偶尔想想', score: 2 }, { text: '不感兴趣', score: 1 }] },
  { q: '做手工或DIY项目时，你的耐心程度？', dimension: '动手', options: [{ text: '非常耐心，做到完美', score: 4 }, { text: '比较有耐心', score: 3 }, { text: '一般', score: 2 }, { text: '容易烦躁', score: 1 }] },
  { q: '你对 3D 打印、机器人制作等技术活动的兴趣？', dimension: '动手', options: [{ text: '非常感兴趣', score: 4 }, { text: '有点兴趣', score: 3 }, { text: '没试过但愿意了解', score: 2 }, { text: '不感兴趣', score: 1 }] },
  { q: '物理课上的实验操作，你的表现通常是？', dimension: '动手', options: [{ text: '第一个动手，乐在其中', score: 4 }, { text: '跟着做，觉得还行', score: 3 }, { text: '看别人做就行', score: 2 }, { text: '能不做就不做', score: 1 }] },
  { q: '你是否喜欢搭建或创造看得见摸得着的东西？', dimension: '动手', options: [{ text: '非常喜欢', score: 4 }, { text: '有时候喜欢', score: 3 }, { text: '无所谓', score: 2 }, { text: '不喜欢', score: 1 }] },
  { q: '你对电路、焊接等电子制作活动的感觉？', dimension: '动手', options: [{ text: '很感兴趣', score: 4 }, { text: '可以试试', score: 3 }, { text: '不太了解', score: 2 }, { text: '没什么兴趣', score: 1 }] },
  { q: '如果让你组装一件宜家家具，你的态度是？', dimension: '动手', options: [{ text: '迫不及待想动手', score: 4 }, { text: '愿意做', score: 3 }, { text: '勉强接受', score: 2 }, { text: '不想碰', score: 1 }] },

  // === 编程与技术 (8题) ===
  { q: '你对编程或写代码的兴趣？', dimension: '编程', options: [{ text: '非常感兴趣，已经自学过', score: 4 }, { text: '有兴趣但还没开始', score: 3 }, { text: '不太确定', score: 2 }, { text: '不感兴趣', score: 1 }] },
  { q: '看到一个新软件或 App，你会想它是怎么做出来的吗？', dimension: '编程', options: [{ text: '经常会想', score: 4 }, { text: '偶尔会想', score: 3 }, { text: '很少想', score: 2 }, { text: '从不关心', score: 1 }] },
  { q: '你对人工智能（如 ChatGPT）背后的技术原理的态度？', dimension: '编程', options: [{ text: '很想深入了解', score: 4 }, { text: '有些好奇', score: 3 }, { text: '只是用用工具', score: 2 }, { text: '不太关心', score: 1 }] },
  { q: '如果让你花一下午调试代码找 bug，你会觉得？', dimension: '编程', options: [{ text: '像侦探破案一样有趣', score: 4 }, { text: '可以接受', score: 3 }, { text: '有点烦', score: 2 }, { text: '完全无法忍受', score: 1 }] },
  { q: '你对逻辑游戏（数独、象棋、解谜游戏）的态度？', dimension: '编程', options: [{ text: '非常喜欢', score: 4 }, { text: '比较喜欢', score: 3 }, { text: '一般', score: 2 }, { text: '不喜欢', score: 1 }] },
  { q: '你是否喜欢用技术解决问题（比如写脚本自动化重复工作）？', dimension: '编程', options: [{ text: '经常这样做', score: 4 }, { text: '偶尔', score: 3 }, { text: '没试过', score: 2 }, { text: '不感兴趣', score: 1 }] },
  { q: '你对计算机底层原理（操作系统、网络协议）的好奇程度？', dimension: '编程', options: [{ text: '非常好奇', score: 4 }, { text: '有点好奇', score: 3 }, { text: '无所谓', score: 2 }, { text: '不关心', score: 1 }] },
  { q: '如果让你设计一个手机 App 的功能，你的心情是？', dimension: '编程', options: [{ text: '很兴奋，有很多想法', score: 4 }, { text: '有些想法', score: 3 }, { text: '没什么想法', score: 2 }, { text: '不感兴趣', score: 1 }] },

  // === 人际与沟通 (8题) ===
  { q: '你更喜欢独自工作还是团队协作？', dimension: '人际', options: [{ text: '非常喜欢团队协作', score: 4 }, { text: '偏向团队', score: 3 }, { text: '偏向独自', score: 2 }, { text: '完全不想跟人合作', score: 1 }] },
  { q: '朋友遇到困扰时，你能敏锐地察觉吗？', dimension: '人际', options: [{ text: '总能第一时间发现', score: 4 }, { text: '经常能发现', score: 3 }, { text: '有时候能', score: 2 }, { text: '不太会注意', score: 1 }] },
  { q: '你喜欢在众人面前表达自己的观点吗？', dimension: '人际', options: [{ text: '非常喜欢，享受演讲', score: 4 }, { text: '还可以', score: 3 }, { text: '会紧张但可以克服', score: 2 }, { text: '完全不想', score: 1 }] },
  { q: '你对帮助他人解决问题的态度？', dimension: '人际', options: [{ text: '非常乐意，有成就感', score: 4 }, { text: '愿意帮忙', score: 3 }, { text: '看情况', score: 2 }, { text: '不太想管', score: 1 }] },
  { q: '你是否喜欢组织活动或者带领团队？', dimension: '人际', options: [{ text: '非常喜欢，经常做', score: 4 }, { text: '有时候愿意', score: 3 }, { text: '偶尔', score: 2 }, { text: '完全不想', score: 1 }] },
  { q: '陌生人向你求助时，你的第一反应是？', dimension: '人际', options: [{ text: '主动热情帮助', score: 4 }, { text: '愿意帮忙', score: 3 }, { text: '有点犹豫', score: 2 }, { text: '尽量避开', score: 1 }] },
  { q: '你对说服别人接受你的观点这件事的感觉？', dimension: '人际', options: [{ text: '很擅长，也喜欢', score: 4 }, { text: '还可以', score: 3 }, { text: '不太擅长', score: 2 }, { text: '很排斥辩论', score: 1 }] },
  { q: '你对参与志愿活动或公益服务的态度？', dimension: '人际', options: [{ text: '非常积极，经常参加', score: 4 }, { text: '愿意参加', score: 3 }, { text: '偶尔', score: 2 }, { text: '不太感兴趣', score: 1 }] },

  // === 创意与表达 (8题) ===
  { q: '你喜欢写作吗？（故事、随笔、日记都算）', dimension: '创意', options: [{ text: '非常喜欢，经常写', score: 4 }, { text: '有时候写', score: 3 }, { text: '很少写', score: 2 }, { text: '完全不喜欢', score: 1 }] },
  { q: '看到一则广告或海报，你会不自觉地分析它的设计吗？', dimension: '创意', options: [{ text: '经常会', score: 4 }, { text: '有时候会', score: 3 }, { text: '很少', score: 2 }, { text: '完全不会', score: 1 }] },
  { q: '你对音乐、绘画、摄影等艺术形式的兴趣？', dimension: '创意', options: [{ text: '非常热爱，有长期坚持的爱好', score: 4 }, { text: '有兴趣但不专业', score: 3 }, { text: '偶尔欣赏', score: 2 }, { text: '不太感冒', score: 1 }] },
  { q: '当别人都用一种方法时，你是否喜欢另辟蹊径？', dimension: '创意', options: [{ text: '经常想新办法', score: 4 }, { text: '偶尔有新想法', score: 3 }, { text: '跟随主流', score: 2 }, { text: '完全不想创新', score: 1 }] },
  { q: '你对设计美观的东西（网站、海报、产品包装）的敏感度？', dimension: '创意', options: [{ text: '非常敏感，会注意到细节', score: 4 }, { text: '比较注意', score: 3 }, { text: '一般', score: 2 }, { text: '不太注意', score: 1 }] },
  { q: '如果有人让你用文字或图片讲一个故事，你会觉得？', dimension: '创意', options: [{ text: '很高兴，马上有想法', score: 4 }, { text: '可以试试', score: 3 }, { text: '有点困难', score: 2 }, { text: '完全不知道怎么做', score: 1 }] },
  { q: '你对历史故事和人类文明的兴趣？', dimension: '创意', options: [{ text: '非常着迷', score: 4 }, { text: '比较感兴趣', score: 3 }, { text: '一般', score: 2 }, { text: '没什么兴趣', score: 1 }] },
  { q: '你是否喜欢把不同的想法或概念组合创造出新东西？', dimension: '创意', options: [{ text: '经常这样做', score: 4 }, { text: '偶尔', score: 3 }, { text: '很少', score: 2 }, { text: '从不', score: 1 }] },

  // === 管理与商业 (10题) ===
  { q: '你对"钱是怎么流动的"这类问题感兴趣吗？', dimension: '管理', options: [{ text: '非常感兴趣', score: 4 }, { text: '比较感兴趣', score: 3 }, { text: '一般', score: 2 }, { text: '不关心', score: 1 }] },
  { q: '你有没有想过自己将来创业或经营一家公司？', dimension: '管理', options: [{ text: '经常想，有明确的创业愿望', score: 4 }, { text: '偶尔会想', score: 3 }, { text: '没仔细想过', score: 2 }, { text: '完全不想', score: 1 }] },
  { q: '看到股市涨跌或者财经新闻，你的反应是？', dimension: '管理', options: [{ text: '会主动关注和研究', score: 4 }, { text: '偶尔关注', score: 3 }, { text: '不太关注', score: 2 }, { text: '完全不懂也不想懂', score: 1 }] },
  { q: '你做决定时更依赖直觉还是理性分析？', dimension: '管理', options: [{ text: '完全理性分析', score: 4 }, { text: '偏理性', score: 3 }, { text: '偏直觉', score: 2 }, { text: '完全凭感觉', score: 1 }] },
  { q: '如果你有 1000 元零花钱，你会怎么处理？', dimension: '管理', options: [{ text: '制定预算，分配用途', score: 4 }, { text: '大概规划一下', score: 3 }, { text: '想买什么买什么', score: 2 }, { text: '完全没概念', score: 1 }] },
  { q: '你是否喜欢分析一个公司的商业模式？（比如 B站怎么赚钱）', dimension: '管理', options: [{ text: '非常喜欢分析', score: 4 }, { text: '偶尔会想', score: 3 }, { text: '很少想', score: 2 }, { text: '没兴趣', score: 1 }] },
  { q: '你对"如何让一个团队高效运转"这类问题的思考？', dimension: '管理', options: [{ text: '经常思考', score: 4 }, { text: '有时会想', score: 3 }, { text: '不太想', score: 2 }, { text: '不关心', score: 1 }] },
  { q: '别人找你帮忙做决策时，你的感觉是？', dimension: '管理', options: [{ text: '喜欢帮人分析决策', score: 4 }, { text: '愿意帮忙', score: 3 }, { text: '看情况', score: 2 }, { text: '不想管', score: 1 }] },
  { q: '你是否关注社会热点和经济政策？', dimension: '管理', options: [{ text: '经常主动关注', score: 4 }, { text: '偶尔看看', score: 3 }, { text: '推送什么看什么', score: 2 }, { text: '完全不关注', score: 1 }] },
  { q: '你在班上是否经常承担组织协调的角色？', dimension: '管理', options: [{ text: '经常是组织者', score: 4 }, { text: '有时协助组织', score: 3 }, { text: '偶尔参与', score: 2 }, { text: '从不参与', score: 1 }] },
]

const DIMENSIONS: Record<string, { label: string; icon: string; majors: string[] }> = {
  '理科': { label: '数理思维', icon: '🔢', majors: ['数学', '物理', '化学', '统计学', '天文学', '地球科学'] },
  '动手': { label: '动手实践', icon: '🔧', majors: ['机械工程', '车辆工程', '航空航天', '机器人工程', '土木工程', '材料科学'] },
  '编程': { label: '编程与逻辑', icon: '💻', majors: ['计算机科学', '软件工程', '人工智能', '电子信息', '网络安全', '大数据'] },
  '人际': { label: '人际沟通', icon: '🤝', majors: ['临床医学', '心理学', '新闻传播', '教育学', '社会学', '人力资源管理'] },
  '创意': { label: '创意表达', icon: '🎨', majors: ['建筑学', '汉语言文学', '广告学', '工业设计', '数字媒体', '艺术学'] },
  '管理': { label: '商业与管理', icon: '📊', majors: ['工商管理', '金融学', '经济学', '会计学', '市场营销', '法学'] },
}

export default function AITest() {
  const [started, setStarted] = useState(false)
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState<Record<number, number>>({})
  const [finished, setFinished] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [result, setResult] = useState('')
  const [analysisError, setAnalysisError] = useState('')

  const handleAnswer = (score: number) => {
    const newAnswers = { ...answers, [current]: score }
    setAnswers(newAnswers)
    if (current < questions.length - 1) {
      setTimeout(() => setCurrent(current + 1), 150)
    } else {
      setFinished(true)
      analyzeResults(newAnswers)
    }
  }

  const goBack = () => { if (current > 0) setCurrent(current - 1) }

  const analyzeResults = async (
    ans: Record<number, number>,
    retry = false,
  ) => {
    setAnalyzing(true)
    if (!retry) setAnalysisError('')
    // 计算各维度得分
    const scores: Record<string, number> = {}
    questions.forEach((q, i) => {
      scores[q.dimension] = (scores[q.dimension] || 0) + (ans[i] || 1)
    })

    try {
      const r = await publicRequest('/qanda/analyze-personality', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          scores: {
            science: scores['理科'],
            hands_on: scores['动手'],
            programming: scores['编程'],
            interpersonal: scores['人际'],
            creativity: scores['创意'],
            management: scores['管理'],
          },
        }),
      })
      if (r.ok) {
        const data = await r.json()
        setResult(data.result)
        setAnalysisError('')
      } else {
        setAnalysisError(
          await getPublicApiError(r, '分析服务暂时不可用，请稍后再试。'),
        )
      }
    } catch {
      setAnalysisError('网络错误，请稍后再试。')
    }
    setAnalyzing(false)
  }

  const restartTest = () => {
    setStarted(true)
    setCurrent(0)
    setAnswers({})
    setFinished(false)
    setAnalyzing(false)
    setResult('')
    setAnalysisError('')
  }

  const totalQuestions = questions.length
  const progress = Math.round(((current + 1) / totalQuestions) * 100)
  const q = questions[current]

  if (!started) {
    return (
      <div>
        <div className="page-header">
          <h1>🧠 AI 专业性格测试</h1>
          <p>50 道趣味题目，帮你发现适合自己的大学专业方向</p>
        </div>
        <div className="container" style={{ maxWidth: '600px', textAlign: 'center' }}>
          <div className="card" style={{ padding: '40px 32px' }}>
            <div style={{ fontSize: '4rem', marginBottom: '20px' }}>🧠</div>
            <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: '1.3rem', fontWeight: 700, marginBottom: '12px' }}>
              发现你的专业性格
            </h2>
            <p style={{ color: 'var(--ink-light)', fontSize: '0.9rem', lineHeight: 1.7, marginBottom: '8px' }}>
              50 道精心设计的题目，从六个维度分析你的兴趣和能力倾向
            </p>
            <div style={{
              display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px',
              margin: '24px 0', textAlign: 'center',
            }}>
              {Object.entries(DIMENSIONS).map(([k, v]) => (
                <div key={k} style={{ padding: '10px 8px', background: 'var(--cream-dark)', borderRadius: 'var(--radius-sm)' }}>
                  <div style={{ fontSize: '1.4rem' }}>{v.icon}</div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 600, color: 'var(--ink)' }}>{v.label}</div>
                </div>
              ))}
            </div>
            <p style={{ color: 'var(--ink-lighter)', fontSize: '0.82rem', marginBottom: '24px' }}>
              约需 8-12 分钟完成 · AI 为你生成个性化分析报告
            </p>
            <button className="btn btn-primary" onClick={() => setStarted(true)}
              style={{ padding: '14px 40px', fontSize: '1rem' }}>
              开始测试 →
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (analyzing && !analysisError) {
    return (
      <div className="container" style={{ maxWidth: '600px', textAlign: 'center', paddingTop: '80px' }}>
        <div className="loading">
          <p style={{ fontSize: '1.2rem', fontWeight: 600 }}>AI 正在分析你的性格特点...</p>
          <p style={{ color: 'var(--ink-lighter)', fontSize: '0.85rem' }}>请稍等片刻</p>
        </div>
      </div>
    )
  }

  if (finished && analysisError) {
    return (
      <div>
        <div className="page-header">
          <h1>🧠 分析暂未完成</h1>
          <p>你的 50 道题答案已经保留，无需重新作答</p>
        </div>
        <div className="container" style={{ maxWidth: '620px' }}>
          <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
            <p style={{ color: '#C94A4A', marginBottom: '20px' }}>
              {analysisError}
            </p>
            <div style={{
              display: 'flex', gap: '12px', justifyContent: 'center',
              flexWrap: 'wrap',
            }}>
              <button
                className="btn btn-primary"
                disabled={analyzing}
                onClick={() => analyzeResults(answers, true)}
              >
                {analyzing ? '重新分析中…' : '重新分析'}
              </button>
              <button
                className="btn btn-outline"
                disabled={analyzing}
                onClick={restartTest}
              >
                重新测试
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (finished && result) {
    return (
      <div>
        <div className="page-header">
          <h1>🧠 你的专业性格分析</h1>
          <p>基于 50 道题目的 AI 个性化分析报告</p>
        </div>
        <div className="container" style={{ maxWidth: '760px' }}>
          <div className="card" style={{ padding: '32px' }}>
            <div className="markdown-body">
              <ReactMarkdown>{result}</ReactMarkdown>
            </div>
            <div style={{ textAlign: 'center', marginTop: '28px', display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-outline" onClick={restartTest}>
                重新测试
              </button>
              <Link to="/explore" className="btn btn-primary">
                去专业探索地图看看 →
              </Link>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      <div style={{
        padding: '16px 28px', background: 'var(--paper)',
        borderBottom: '1px solid var(--border-light)',
        position: 'sticky', top: '52px', zIndex: 50,
      }}>
        <div className="container">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '0.84rem', color: 'var(--ink-light)' }}>
              第 {current + 1} / {totalQuestions} 题
            </span>
            <span style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--accent)' }}>
              {progress}%
            </span>
          </div>
          <div style={{
            width: '100%', height: '4px', background: 'var(--border-light)',
            borderRadius: '2px', overflow: 'hidden',
          }}>
            <div style={{
              width: `${progress}%`, height: '100%',
              background: 'linear-gradient(90deg, var(--accent), var(--gold))',
              borderRadius: '2px', transition: 'width 0.3s',
            }} />
          </div>
        </div>
      </div>

      <div className="container" style={{ maxWidth: '620px', paddingTop: '48px' }}>
        <div className="card" style={{ padding: '36px 32px' }}>
          <span className="tag" style={{ marginBottom: '14px' }}>
            {DIMENSIONS[q.dimension].icon} {DIMENSIONS[q.dimension].label}
          </span>
          <h2 style={{
            fontFamily: 'var(--font-serif)', fontSize: '1.2rem',
            fontWeight: 700, color: 'var(--ink)', marginBottom: '28px',
            lineHeight: 1.5,
          }}>
            {current + 1}. {q.q}
          </h2>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {q.options.map((opt, i) => (
              <button key={i}
                onClick={() => handleAnswer(opt.score)}
                style={{
                  width: '100%', textAlign: 'left', padding: '14px 20px',
                  borderRadius: 'var(--radius-sm)', border: '1.5px solid var(--border-light)',
                  background: answers[current] === opt.score ? 'var(--accent-glow)' : 'white',
                  cursor: 'pointer', fontSize: '0.9rem', color: 'var(--ink)',
                  transition: 'all 0.2s', fontFamily: 'inherit',
                  borderColor: answers[current] === opt.score ? 'var(--accent)' : 'var(--border-light)',
                  fontWeight: answers[current] === opt.score ? 600 : 400,
                }}>
                {opt.text}
              </button>
            ))}
          </div>

          {current > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={goBack}
              style={{ marginTop: '16px' }}>
              ← 上一题
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
