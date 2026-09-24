// Iconos como SVG en vez de emojis: los emojis los dibuja cada sistema a su
// manera y no toman el color del boton.
const BASE = {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

export function IconoMicrofono() {
  return (
    <svg {...BASE}>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="18" x2="12" y2="22" />
    </svg>
  )
}

export function IconoDetener() {
  return (
    <svg {...BASE}>
      <rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" />
    </svg>
  )
}

export function IconoVolumen({ activo }) {
  return (
    <svg {...BASE}>
      <path d="M11 5 6 9H2v6h4l5 4V5z" fill="currentColor" />
      {activo ? (
        <>
          <path d="M15.5 8.5a5 5 0 0 1 0 7" />
          <path d="M18.5 5.5a9 9 0 0 1 0 13" />
        </>
      ) : (
        <>
          <line x1="16" y1="9" x2="22" y2="15" />
          <line x1="22" y1="9" x2="16" y2="15" />
        </>
      )}
    </svg>
  )
}

export function IconoPuntos() {
  // Los tres puntitos de "transcribiendo".
  return (
    <svg {...BASE}>
      <circle cx="5" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.5" fill="currentColor" stroke="none" />
      <circle cx="19" cy="12" r="1.5" fill="currentColor" stroke="none" />
    </svg>
  )
}