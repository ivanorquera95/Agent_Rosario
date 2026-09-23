import { useEffect, useRef, useState } from 'react'

const TEXTO_ESTADO = {
  reposo: '',
  pensando: 'Rosario está pensando…',
  hablando: 'Rosario está respondiendo…',
}
// Los enlaces llegan como [texto](url). Se convierten a mano en vez de sumar
// una libreria de Markdown: el prompt ya prohibe negritas y titulos.
const ENLACE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g

function conEnlaces(texto) {
  const partes = []
  let ultimo = 0
  for (const m of texto.matchAll(ENLACE)) {
    if (m.index > ultimo) partes.push(texto.slice(ultimo, m.index))
    partes.push(
      <a key={m.index} href={m[2]} target="_blank" rel="noreferrer">
        {m[1]}
      </a>,
    )
    ultimo = m.index + m[0].length
  }
  partes.push(texto.slice(ultimo))
  return partes
}

export default function Chat({ mensajes, estado, error, enviar, nuevaConversacion, voz }) {
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
            {m.contenido ? conEnlaces(m.contenido) : '…'}
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
        {voz.aviso && <p className="aviso">{voz.aviso}</p>}
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
          <span>
            {voz.activa
              ? 'Audio limitado: 1 por minuto y 200 por día entre todos.'
              : 'Las conversaciones se borran solas después de 2 horas sin actividad.'}
          </span>
          {voz.soportada && (
            <button
              type="button"
              className={`nueva ${voz.activa ? 'activo' : ''}`}
              onClick={voz.alternar}
              aria-pressed={voz.activa}
            >
              {voz.activa ? '🔊 Escuchándome' : '🔈 Escuchame'}
            </button>
          )}
          <button type="button" className="nueva" onClick={nuevaConversacion} disabled={ocupado}>
            Nueva conversación
          </button>
        </div>
      </footer>
    </>
  )
}