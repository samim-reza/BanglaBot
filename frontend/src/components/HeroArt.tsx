/**
 * Landing hero illustration: the AI agent on a call, the customer confirming,
 * and the order flipping to confirmed. Inline SVG so it inherits the page's
 * Bengali font and teal palette; the waveform pulses via SMIL.
 */
export default function HeroArt() {
  const wave = [14, 26, 38, 22, 46, 30, 18, 40, 26, 14];
  return (
    <svg
      viewBox="0 0 560 460"
      role="img"
      aria-label="BanglaBot কল করে অর্ডার নিশ্চিত করছে"
      style={{ width: "100%", height: "auto", display: "block" }}
    >
      {/* soft background blob + dots */}
      <ellipse cx="290" cy="245" rx="250" ry="200" fill="#e6f4f2" />
      <g fill="#99d5cf">
        {[
          [70, 90], [95, 70], [120, 90], [70, 115], [95, 135], [120, 115],
        ].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="3.5" />
        ))}
        {[
          [470, 360], [495, 340], [520, 360], [470, 385], [495, 405], [520, 385],
        ].map(([x, y], i) => (
          <circle key={`b${i}`} cx={x} cy={y} r="3.5" />
        ))}
      </g>

      {/* phone */}
      <g>
        <rect x="150" y="60" width="190" height="360" rx="28" fill="#0f766e" />
        <rect x="158" y="68" width="174" height="344" rx="22" fill="#ffffff" />
        <rect x="216" y="78" width="58" height="6" rx="3" fill="#e3e8ec" />

        {/* call header */}
        <circle cx="245" cy="150" r="34" fill="#e6f4f2" />
        <path
          d="M245 138a12 12 0 0 1 12 12v6a12 12 0 0 1-24 0v-6a12 12 0 0 1 12-12z"
          fill="#0d9488"
        />
        <path
          d="M229 158a16 16 0 0 0 32 0M245 174v10M236 184h18"
          stroke="#0d9488"
          strokeWidth="4"
          strokeLinecap="round"
          fill="none"
        />
        <text x="245" y="212" textAnchor="middle" fontSize="15" fontWeight="700" fill="#1f2937">
          BanglaBot
        </text>
        <text x="245" y="232" textAnchor="middle" fontSize="12" fill="#6b7280">
          কল চলছে…
        </text>

        {/* waveform */}
        <g transform="translate(245 285)">
          {wave.map((h, i) => (
            <rect
              key={i}
              x={(i - wave.length / 2) * 13 + 2}
              y={-h / 2}
              width="7"
              height={h}
              rx="3.5"
              fill={i % 2 ? "#0d9488" : "#99d5cf"}
            >
              <animate
                attributeName="height"
                values={`${h};${h * 0.45};${h}`}
                dur={`${1 + (i % 4) * 0.22}s`}
                repeatCount="indefinite"
              />
              <animate
                attributeName="y"
                values={`${-h / 2};${-h * 0.225};${-h / 2}`}
                dur={`${1 + (i % 4) * 0.22}s`}
                repeatCount="indefinite"
              />
            </rect>
          ))}
        </g>

        {/* call button */}
        <circle cx="245" cy="368" r="24" fill="#0d9488" />
        <path
          d="M236 362c1.8-1.8 4.4-1.9 6 0l2 2.4c1.2 1.4 3.2 1.6 4.8.6 1.5-1 3.4-.8 4.6.5l2.4 2.4c1.6 1.6 1.6 4.2 0 5.8-2.6 2.6-6.7 3.2-9.8 1.3-4.6-2.7-8.5-6.6-11.2-11.2-.9-1.5-.5-3.5 1.2-1.8z"
          fill="#ffffff"
        />
        <g stroke="#0d9488" strokeWidth="3" strokeLinecap="round" fill="none">
          <path d="M292 130a26 26 0 0 1 0 40">
            <animate attributeName="opacity" values="1;.2;1" dur="2s" repeatCount="indefinite" />
          </path>
          <path d="M302 118a42 42 0 0 1 0 64">
            <animate
              attributeName="opacity"
              values=".2;1;.2"
              dur="2s"
              repeatCount="indefinite"
            />
          </path>
        </g>
      </g>

      {/* agent bubble */}
      <g>
        <rect x="330" y="88" width="204" height="64" rx="14" fill="#ffffff" stroke="#e3e8ec" />
        <path d="M344 152l-8 14 22-14z" fill="#ffffff" stroke="#e3e8ec" />
        <circle cx="356" cy="120" r="14" fill="#e6f4f2" />
        <text x="356" y="125" textAnchor="middle" fontSize="13">🤖</text>
        <text x="378" y="115" fontSize="12.5" fill="#1f2937">
          আপনার অর্ডারটি কি
        </text>
        <text x="378" y="133" fontSize="12.5" fill="#1f2937">
          কনফার্ম করবো?
        </text>
      </g>

      {/* customer reply bubble */}
      <g>
        <rect x="392" y="188" width="140" height="44" rx="14" fill="#0d9488" />
        <path d="M518 232l10 12-24-8z" fill="#0d9488" />
        <text x="462" y="215" textAnchor="middle" fontSize="13.5" fontWeight="700" fill="#ffffff">
          হ্যাঁ, কনফার্ম ✓
        </text>
      </g>

      {/* order card */}
      <g>
        <rect x="360" y="278" width="180" height="112" rx="14" fill="#ffffff" stroke="#e3e8ec" />
        <text x="378" y="306" fontSize="12.5" fontWeight="700" fill="#1f2937">
          অর্ডার #১০২৪
        </text>
        <rect x="378" y="318" width="104" height="7" rx="3.5" fill="#eef1f4" />
        <rect x="378" y="332" width="76" height="7" rx="3.5" fill="#eef1f4" />
        <rect x="378" y="352" width="76" height="22" rx="11" fill="#d1fae5" />
        <text x="416" y="367" textAnchor="middle" fontSize="11.5" fontWeight="700" fill="#065f46">
          নিশ্চিত
        </text>
        <g>
          <circle cx="516" cy="302" r="17" fill="#0d9488" />
          <path
            d="M508 302l6 6 11-11"
            stroke="#ffffff"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </g>
      </g>

      {/* taka coin */}
      <g>
        <circle cx="110" cy="330" r="26" fill="#ffffff" stroke="#99d5cf" strokeWidth="3" />
        <text x="110" y="340" textAnchor="middle" fontSize="24" fontWeight="700" fill="#0f766e">
          ৳
        </text>
      </g>
    </svg>
  );
}
