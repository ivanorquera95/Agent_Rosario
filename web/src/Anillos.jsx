// Anillos animados de Rosario. El estado (reposo | pensando | hablando) llega
// como prop y se convierte en una clase: el movimiento y el color son del CSS.
const ANILLOS = [
  { clase: 'anillo-1', r: 92, ancho: 3, trazo: '2 6' },
  { clase: 'anillo-2', r: 80, ancho: 2, trazo: '60 20 10 20' },
  { clase: 'anillo-3', r: 66, ancho: 1, trazo: null },
  { clase: 'anillo-4', r: 58, ancho: 6, trazo: '3 5' },
  { clase: 'anillo-5', r: 46, ancho: 2, trazo: '110 180' },
]

export default function Anillos({ estado }) {
  return (
    <svg className={`anillos ${estado}`} viewBox="0 0 200 200" role="img" aria-label={`Rosario: ${estado}`}>
      <g className="conjunto">
        {ANILLOS.map((a) => (
          <g key={a.clase} className={`anillo ${a.clase}`}>
            <g className="extra">
              <circle cx="100" cy="100" r={a.r} strokeWidth={a.ancho} strokeDasharray={a.trazo ?? undefined} />
            </g>
          </g>
        ))}
        <circle className="nucleo" cx="100" cy="100" r="34" />
        <text x="100" y="100" textAnchor="middle" dominantBaseline="central">
          ROSARIO
        </text>
      </g>
    </svg>
  )
}