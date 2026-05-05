
// Animated Number Hook — Phase 8 UI Polish
// Counting animation for numeric values


import { useEffect, useRef, useState } from 'react'

interface UseAnimatedNumberOptions {
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
}

export function useAnimatedNumber(
  value: number,
  options: UseAnimatedNumberOptions = {}
) {
  const { duration = 600, decimals = 2, prefix = '', suffix = '' } = options
  const [displayed, setDisplayed] = useState(value)
  const prevRef = useRef(value)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const start = prevRef.current
    const end = value
    if (start === end) return

    const startTime = performance.now()
    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3)

    const tick = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = easeOut(progress)
      setDisplayed(start + (end - start) * eased)
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick)
      } else {
        prevRef.current = end
      }
    }

    frameRef.current = requestAnimationFrame(tick)
    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [value, duration])

  return `${prefix}${displayed.toFixed(decimals)}${suffix}`
}

// Hook for flashing on value change
export function useFlashOnChange(value: number) {
  const prevRef = useRef(value)
  const [flashClass, setFlashClass] = useState('')

  useEffect(() => {
    if (value !== prevRef.current) {
      const dir = value > prevRef.current ? 'flash-up' : 'flash-down'
      setFlashClass(dir)
      const t = setTimeout(() => setFlashClass(''), 1000)
      prevRef.current = value
      return () => clearTimeout(t)
    }
  }, [value])

  return flashClass
}

// Hook for signal change animation
export function useSignalChange(value: string, previousValue?: string) {
  const [isChanging, setIsChanging] = useState(false)
  const prevRef = useRef(value)

  useEffect(() => {
    if (previousValue && value !== previousValue) {
      setIsChanging(true)
      const t = setTimeout(() => setIsChanging(false), 800)
      return () => clearTimeout(t)
    }
    prevRef.current = value
  }, [value, previousValue])

  return isChanging
}
