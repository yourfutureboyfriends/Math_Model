
// Animated Value Component — Phase 8 UI Polish
// Numbers that count up/down with colour-coding


import { useAnimatedNumber, useFlashOnChange } from '@/hooks/useAnimatedNumber'

interface AnimatedValueProps {
  value: number
  decimals?: number
  prefix?: string
  suffix?: string
  duration?: number
  className?: string
  colorize?: boolean // green if positive, red if negative
  flashOnChange?: boolean
}

export function AnimatedValue({
  value,
  decimals = 2,
  prefix = '',
  suffix = '',
  duration = 600,
  className = '',
  colorize = false,
  flashOnChange = true,
}: AnimatedValueProps) {
  const displayed = useAnimatedNumber(value, { duration, decimals, prefix, suffix })
  const flashClass = useFlashOnChange(value)

  const colorClass = colorize
    ? value >= 0
      ? 'positive'
      : 'negative'
    : ''

  const combinedClass = `number ${colorClass} ${flashOnChange ? flashClass : ''} ${className}`.trim()

  return (
    <span className={combinedClass} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {displayed}
    </span>
  )
}

// Metric value with label — common pattern in KPIs
interface MetricValueProps extends AnimatedValueProps {
  label: string
  sublabel?: string
  trend?: 'up' | 'down' | 'neutral'
}

export function MetricValue({
  label,
  sublabel,
  trend,
  ...animatedProps
}: MetricValueProps) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-text-secondary uppercase tracking-wider">
        {label}
      </span>
      <div className="flex items-baseline gap-2">
        <AnimatedValue {...animatedProps} className="text-2xl font-semibold" />
        {trend && (
          <span
            className={`text-xs ${
              trend === 'up'
                ? 'text-green'
                : trend === 'down'
                  ? 'text-red'
                  : 'text-text-secondary'
            }`}
          >
            {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '—'}
          </span>
        )}
      </div>
      {sublabel && (
        <span className="text-xs text-text-tertiary">{sublabel}</span>
      )}
    </div>
  )
}

// Percentage value — auto-adds % suffix
interface PercentageValueProps extends Omit<AnimatedValueProps, 'suffix'> {}

export function PercentageValue(props: PercentageValueProps) {
  return <AnimatedValue {...props} suffix="%" decimals={props.decimals ?? 1} />
}

// Currency value — auto-adds $ prefix
interface CurrencyValueProps extends Omit<AnimatedValueProps, 'prefix'> {
  currency?: string
}

export function CurrencyValue({ currency = '$', ...props }: CurrencyValueProps) {
  return <AnimatedValue {...props} prefix={currency} />
}
