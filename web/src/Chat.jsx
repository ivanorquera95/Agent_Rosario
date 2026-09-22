import { useEffect, useRef, useState } from 'react'

const TEXTO_ESTADO = {
  reposo: '',
  pensando: 'Rosario está pensando…',
  hablando: 'Rosario está respondiendo…',
}

export default function Chat({ mensajes, estado, error, enviar, nuevaConversacion }) {
  const [texto, setTexto] = useState('')
  const ocupado = estado !== 'reposo'
  const listaRef = useRef(null)
  const cajaRef = useRef(null)
  const largoAnterior = useRef(0)
  const huboEnvio = useRef(false)

  // Baja al ultimo mensaje. Si llego un mensaje nuevo (o se cargo el historial)
  // baja siempre. Si solo se esta escribiendo la respuesta, baja salvo que el
  // usuario haya subido a leer algo anterior: ahi no se le mueve la pantalla.
  useEffect(() => {
    const lista = listaRef.current
    if (!lista) return
    const hayMensajeNuevo = mensajes.length !== largoAnterior.current
    largoAnterior.current = mensajes.length
    const cercaDelFinal = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 150
    if (hayMensajeNuevo || cercaDelFinal) lista.scrollTop = lista.scrollHeight
  }, [mensajes])

  // Al terminar una respuesta, el cursor vuelve a la caja. Solo despues de un
  // envio: al abrir la pagina en el celular no se despliega el teclado solo.
  useEffect(() => {
    if (estado === 'reposo' && huboEnvio.current) cajaRef.current?.focus()
  }, [estado])

  function alEnviar(e) {
    e.preventDefault() // sin esto, el formulario recarga la pagina
    if (!texto.trim()) return
    huboEnvio.current = true
    enviar(texto)
    setTexto('')
  }

  return (
    <>
      <section className="mensajes" ref={listaRef}>
        {mensajes.length === 0 && (
          <p className="vacio">Preguntame por colectivos, descuentos, precios, el clima o qué hacer en Rosario.</p>
        )}
        {mensajes.map((m, i) => (
          <div key={i} className={`mensaje ${m.rol}`}>
            {m.contenido || '…'}
          </div>
        ))}
      </section>

      <p className="solo-lector" aria-live="polite">
        {TEXTO_ESTADO[estado]}
      </p>

      <footer className="pie">
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <form className="caja" onSubmit={alEnviar}>
          <input
            ref={cajaRef}
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            disabled={ocupado}
            maxLength={1000}
            placeholder="Preguntale a Rosario"
            aria-label="Mensaje para Rosario"
          />
          <button type="submit" disabled={ocupado || !texto.trim()}>
            Enviar
          </button>
        </form>
        <div className="pie-extra">
          <span>Las conversaciones se borran solas después de 2 horas sin actividad.</span>
          <button type="button" className="nueva" onClick={nuevaConversacion} disabled={ocupado}>
            Nueva conversación
          </button>
        </div>
      </footer>
    </>
  )
}