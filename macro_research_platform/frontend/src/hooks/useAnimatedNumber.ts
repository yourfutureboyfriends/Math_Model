// Animated Number Hook — Phase 8 UI Polish
// Counting animation for numeric values

import { useEffect, useRef, useState } from 'react'

interface UseAnimatedNumberOptions {
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
}

/**
 * Normalize any input value to a safe number
 * Handles: numbers, numeric strings, null, undefined, and invalid values
 */
function normalizeNumericInput(value: unknown, fallback: number = 0): number {
  // Already a valid number
  if (typeof value === 'number' && !isNaN(value) && isFinite(value)) {
    return value
  }

  // String that might be numeric
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed === '') return fallback
    const parsed = parseFloat(trimmed)
    if (!isNaN(parsed) && isFinite(parsed)) {
      return parsed
    }
  }

  // Null/undefined or invalid - return fallback
  return fallback
}

export function useAnimatedNumber(
  value: number | string | null | undefined,
  options: UseAnimatedNumberOptions = {}
) {
  const { duration = 600, decimals = 2, prefix = '', suffix = '' } = options

  // Normalize the target value
  const normalizedValue = normalizeNumericInput(value, 0)

  const [displayed, setDisplayed] = useState(normalizedValue)
  const prevRef = useRef(normalizedValue)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const start = prevRef.current
    const end = normalizedValue
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
  }, [normalizedValue, duration])

  // Ensure displayed is always a valid number before calling toFixed
  const safeDisplayed = normalizeNumericInput(displayed, 0)
  return `${prefix}${safeDisplayed.toFixed(decimals)}${suffix}`
}

// Hook for flashing on value change
export function useFlashOnChange(value: number | string | null | undefined) {
  const normalizedValue = normalizeNumericInput(value, 0)
  const prevRef = useRef(normalizedValue)
  const [flashClass, setFlashClass] = useState('')

  useEffect(() => {
    if (normalizedValue !== prevRef.current) {
      const dir = normalizedValue > prevRef.current ? 'flash-up' : 'flash-down'
      setFlashClass(dir)
      const t = setTimeout(() => setFlashClass(''), 1000)
      prevRef.current = normalizedValue
      return () => clearTimeout(t)
    }
  }, [normalizedValue])

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
