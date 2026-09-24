// Anillos animados de Rosario. El estado (reposo | pensando | hablando) llega
// como prop y se convierte en una clase: el movimiento y el color son del CSS.
// r: radio. ancho: grosor. trazo: el patron de guiones (trazo y hueco, en pares).
// Los externos dan la estructura, pero finos: el peso lo pone la escala de
// marcas, que se lee como instrumento sin saturar.
const ANILLOS = [
  { clase: 'anillo-1', r: 96, ancho: 1.5, trazo: '60 10 4 10' },
  { clase: 'anillo-2', r: 86, ancho: 2.5, trazo: '110 16 8 16' },
  { clase: 'anillo-4', r: 74, ancho: 2, trazo: '14 5' },
  { clase: 'anillo-5', r: 60, ancho: 1, trazo: '120 18 4 10' },
]

// Las marcas de escala se generan por codigo: dibujar 120 rayitas a mano seria
// ilegible, y asi se puede cambiar la densidad con un numero.
function marcas({ cantidad, radio, largo, desde = 0, hasta = 360, cada = 1 }) {
  const lineas = []
  const paso = (hasta - desde) / cantidad
  for (let i = 0; i < cantidad; i++) {
    const grados = desde + i * paso
    const rad = (grados * Math.PI) / 180
    // Una de cada 'cada' marcas es mas larga, como en una regla.
    const l = i % cada === 0 ? largo * 2 : largo
    lineas.push({
      x1: 100 + radio * Math.cos(rad),
      y1: 100 + radio * Math.sin(rad),
      x2: 100 + (radio + l) * Math.cos(rad),
      y2: 100 + (radio + l) * Math.sin(rad),
      clave: `${radio}-${i}`,
    })
  }
  return lineas
}

const ESCALA_EXTERNA = marcas({ cantidad: 180, radio: 100, largo: 3, cada: 15 })
const ESCALA_INTERNA = marcas({ cantidad: 60, radio: 50, largo: 1.2, cada: 6 })
const ESCALA_ARCO = marcas({ cantidad: 28, radio: 78, largo: 2, desde: 200, hasta: 320 })

export default function Anillos({ estado }) {
  return (
    <svg className={`anillos ${estado}`} viewBox="-12 -12 224 224" role="img" aria-label={`Rosario: ${estado}`}>
      <defs>
        {/* Degradado radial: blanco en el centro, el color hacia afuera y
            transparente en el borde. Es lo que da el efecto de globo de luz. */}
        <radialGradient id="nucleo-luz">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.7" />
          <stop offset="40%" stopColor="var(--color)" stopOpacity="0.5" />
          <stop offset="75%" stopColor="var(--color)" stopOpacity="0.18" />
          <stop offset="100%" stopColor="var(--color)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <g className="conjunto">
        {/* Escala externa: gira despacio, es la base del conjunto. */}
        <g className="escala escala-externa">
          {ESCALA_EXTERNA.map((m) => (
            <line key={m.clave} x1={m.x1} y1={m.y1} x2={m.x2} y2={m.y2} />
          ))}
        </g>

        {ANILLOS.map((a) => (
          <g key={a.clase} className={`anillo ${a.clase}`}>
            <g className="extra">
              <circle cx="100" cy="100" r={a.r} strokeWidth={a.ancho} strokeDasharray={a.trazo ?? undefined} />
            </g>
          </g>
        ))}

        {/* Arco de acento en ambar: un solo elemento de otro color, como en los
            instrumentos donde un indicador resalta sobre el resto. */}
        <g className="acento">
          <path className="arco-acento" d="M 100 100 m -30 -14 a 33 33 0 0 0 0 28" />
          <g className="escala escala-arco">
            {ESCALA_ARCO.map((m) => (
              <line key={m.clave} x1={m.x1} y1={m.y1} x2={m.x2} y2={m.y2} />
            ))}
          </g>
        </g>

        {/* Escala interna: mas fina y mas rapida, rodea el nucleo. */}
        <g className="escala escala-interna">
          {ESCALA_INTERNA.map((m) => (
            <line key={m.clave} x1={m.x1} y1={m.y1} x2={m.x2} y2={m.y2} />
          ))}
        </g>

        {/* El borde va primero y el globo de luz encima. */}
        <circle className="halo" cx="100" cy="100" r="34" />
        <circle className="nucleo" cx="100" cy="100" r="30" />
      </g>
    </svg>
  )
}