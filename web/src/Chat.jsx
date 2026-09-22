import { useState } from 'react'

export default function Chat({ mensajes, estado, error, enviar, nuevaConversacion }) {
  const [texto, setTexto] = useState('')
  const ocupado = estado !== 'reposo'

  function alEnviar(e) {
    e.preventDefault() // sin esto, el formulario recarga la pagina
    enviar(texto)
    setTexto('')
  }

  return (
    <div>
      <button onClick={nuevaConversacion} disabled={ocupado}>
        Nueva conversación
      </button>

      <ul>
        {mensajes.map((m, i) => (
          <li key={i}>
            <b>{m.rol === 'user' ? 'Vos' : 'Rosario'}:</b>{' '}
            <span style={{ whiteSpace: 'pre-wrap' }}>{m.contenido || '…'}</span>
          </li>
        ))}
      </ul>

      <p>Estado: {estado}</p>
      {error && <p style={{ color: 'red' }}>{error}</p>}

      <form onSubmit={alEnviar}>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          disabled={ocupado}
          maxLength={1000}
          placeholder="Preguntale a Rosario"
        />
        <button type="submit" disabled={ocupado || !texto.trim()}>
          Enviar
        </button>
      </form>
    </div>
  )
}