import { useEffect, useRef } from 'react'
import { runsApi } from '@/api/runs'
import type { AgentEvent } from '@/api/types'
import { useRunStore } from '@/store/runStore'

const MAX_RETRIES = 10
const BASE_DELAY_MS = 1000

const SSE_EVENT_TYPES = [
  'counters_updated',
  'job_updated',
  'run_started',
  'run_completed',
  'run_interrupted',
  'run_error',
  'search_started',
  'search_completed',
  'search_batch_completed',
  'login_started',
  'login_success',
  'login_failed',
  'resume_parsed',
  'applying',
] as const

export function useAgentEventStream(runId: number | null) {
  const applyEvent = useRunStore((s) => s.applyEvent)
  const retriesRef = useRef(0)

  useEffect(() => {
    if (!runId) return

    let es: EventSource | null = null
    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      if (cancelled) return
      es = new EventSource(runsApi.eventsUrl(runId))

      const handleMessage = (ev: MessageEvent) => {
        try {
          const event = JSON.parse(ev.data) as AgentEvent
          applyEvent(event)
          retriesRef.current = 0
        } catch {
          // ignore malformed events
        }
      }

      es.onmessage = handleMessage
      for (const eventType of SSE_EVENT_TYPES) {
        es.addEventListener(eventType, handleMessage)
      }

      es.onerror = () => {
        es?.close()
        if (cancelled) return
        if (retriesRef.current >= MAX_RETRIES) return
        const delay = BASE_DELAY_MS * 2 ** retriesRef.current
        retriesRef.current += 1
        retryTimer = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
      es?.close()
    }
  }, [runId, applyEvent])
}
