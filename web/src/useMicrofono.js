import { useCallback, useRef, useState } from 'react'

const MAX_SEGUNDOS = 60

export function useMicrofono(sesionId, alTranscribir) {
  const soportado = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
  const [grabando, setGrabando] = useState(false)
  const [transcribiendo, setTranscribiendo] = useState(false)
  const [aviso, setAviso] = useState(null)
  const grabadorRef = useRef(null)
  const cortePorTiempoRef = useRef(null)

  async function enviarAudio(blob) {
    setTranscribiendo(true)
    try {
      const formulario = new FormData()
      formulario.append('sesion_id', sesionId)
      formulario.append('audio', blob, 'audio.webm')

      const respuesta = await fetch('/transcribir', { method: 'POST', body: formulario })
      const datos = await respuesta.json().catch(() => ({}))
      if (!respuesta.ok) throw new Error(datos.detail || 'No pude entender el audio.')

      alTranscribir(datos.texto)
    } catch (e) {
      setAviso(e.message)
    } finally {
      setTranscribiendo(false)
    }
  }

  const empezar = useCallback(async () => {
    setAviso(null)
    try {
      const pista = await navigator.mediaDevices.getUserMedia({ audio: true })
      const grabador = new MediaRecorder(pista)
      const trozos = []

      grabador.ondataavailable = (e) => e.data.size > 0 && trozos.push(e.data)
      grabador.onstop = () => {
        // Apagar la pista es lo que saca el punto rojo de "grabando" del navegador.
        pista.getTracks().forEach((t) => t.stop())
        clearTimeout(cortePorTiempoRef.current)
        setGrabando(false)
        if (trozos.length) enviarAudio(new Blob(trozos, { type: grabador.mimeType }))
      }

      grabador.start()
      grabadorRef.current = grabador
      setGrabando(true)
      // Si el usuario se olvida de cortar, no se graba para siempre.
      cortePorTiempoRef.current = setTimeout(() => grabador.stop(), MAX_SEGUNDOS * 1000)
    } catch (e) {
      // NotAllowedError: el usuario dijo que no, o el sitio no está en HTTPS.
      setAviso(
        e.name === 'NotAllowedError'
          ? 'No tengo permiso para usar el micrófono. Habilitalo en el candado de la barra de direcciones.'
          : 'No pude acceder al micrófono.',
      )
      setGrabando(false)
    }
  }, [sesionId])

  const frenar = useCallback(() => {
    grabadorRef.current?.stop()
  }, [])

  return { soportado, grabando, transcribiendo, aviso, empezar, frenar }
}