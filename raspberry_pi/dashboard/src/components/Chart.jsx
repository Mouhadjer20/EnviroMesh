import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { METRICS, formatMetric, hm, label, when } from '../lib.js'

export default function Chart({ points, metric }) {
  if (points.length < 2) return <div className="vide">Le graphique apparaît après deux mesures numériques.</div>
  const danger = METRICS[metric]?.danger
  return (
    <div className="chart-box">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={points} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--ligne)" strokeDasharray="3 4" />
          <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} tickFormatter={hm} stroke="var(--doux)" fontSize={11} minTickGap={40} />
          <YAxis stroke="var(--doux)" fontSize={11} width={48} domain={['auto', 'auto']} />
          <Tooltip labelFormatter={when} formatter={v => [formatMetric(metric, v), label(metric)]}
            contentStyle={{ background: 'var(--panneau)', border: '1px solid var(--ligne)', borderRadius: 10 }} />
          {danger != null && <ReferenceLine y={danger} stroke="var(--alerte)" strokeDasharray="6 4" />}
          <Line type="monotone" dataKey="v" stroke="var(--focus)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
