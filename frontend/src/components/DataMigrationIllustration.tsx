import React from "react";

interface Props {
  width?: number | string;
  height?: number | string;
}

export default function DataValidationIllustration({
  width = 480,
  height = 360,
}: Props) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 480 360"
      width={width}
      height={height}
      fill="none"
    >
      <defs>
        <linearGradient id="bgGrad" x1="0" y1="0" x2="480" y2="360" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#e8f4fd" />
          <stop offset="100%" stopColor="#f0e6ff" />
        </linearGradient>
        <linearGradient id="lensGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#a0d4ff" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#60b0ff" stopOpacity="0.1" />
        </linearGradient>
        <linearGradient id="panelLeft" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4096ff" />
          <stop offset="100%" stopColor="#1677ff" />
        </linearGradient>
        <linearGradient id="panelRight" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#73d13d" />
          <stop offset="100%" stopColor="#389e0d" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="shadow">
          <feDropShadow dx="0" dy="2" stdDeviation="4" floodOpacity="0.12" />
        </filter>
      </defs>

      <rect width="480" height="360" rx="16" fill="url(#bgGrad)" />
      <ellipse cx="240" cy="315" rx="200" ry="8" fill="#d6dff7" opacity="0.5" />

      {/* === LEFT DATA PANEL (Source — Salesforce) === */}
      <g filter="shadow">
        <rect x="20" y="80" width="130" height="180" rx="10" fill="#fff" />
        <rect x="20" y="80" width="130" height="32" rx="10" fill="url(#panelLeft)" />
        <rect x="40" y="80" width="110" height="32" fill="url(#panelLeft)" />
        <text x="85" y="101" textAnchor="middle" fontSize="11" fontWeight="700" fill="#fff" fontFamily="system-ui">Source Data</text>
        {/* Data rows */}
        <rect x="32" y="124" width="80" height="6" rx="2" fill="#1677ff" opacity="0.2" />
        <rect x="32" y="138" width="100" height="6" rx="2" fill="#1677ff" opacity="0.15" />
        <rect x="32" y="152" width="60" height="6" rx="2" fill="#1677ff" opacity="0.2" />
        <rect x="32" y="166" width="90" height="6" rx="2" fill="#1677ff" opacity="0.15" />
        <rect x="32" y="180" width="70" height="6" rx="2" fill="#1677ff" opacity="0.2" />
        <rect x="32" y="194" width="95" height="6" rx="2" fill="#1677ff" opacity="0.15" />
        <rect x="32" y="208" width="55" height="6" rx="2" fill="#1677ff" opacity="0.2" />
        <rect x="32" y="222" width="85" height="6" rx="2" fill="#1677ff" opacity="0.15" />
        <rect x="32" y="236" width="75" height="6" rx="2" fill="#1677ff" opacity="0.2" />
      </g>
      <text x="85" y="275" textAnchor="middle" fontSize="10" fontWeight="600" fill="#1677ff" fontFamily="system-ui">Salesforce OCE</text>

      {/* === RIGHT DATA PANEL (Target — Veeva Vault) === */}
      <g filter="shadow">
        <rect x="330" y="80" width="130" height="180" rx="10" fill="#fff" />
        <rect x="330" y="80" width="130" height="32" rx="10" fill="url(#panelRight)" />
        <rect x="350" y="80" width="110" height="32" fill="url(#panelRight)" />
        <text x="395" y="101" textAnchor="middle" fontSize="11" fontWeight="700" fill="#fff" fontFamily="system-ui">Target Data</text>
        {/* Data rows */}
        <rect x="342" y="124" width="80" height="6" rx="2" fill="#389e0d" opacity="0.2" />
        <rect x="342" y="138" width="100" height="6" rx="2" fill="#389e0d" opacity="0.15" />
        <rect x="342" y="152" width="60" height="6" rx="2" fill="#389e0d" opacity="0.2" />
        <rect x="342" y="166" width="90" height="6" rx="2" fill="#389e0d" opacity="0.15" />
        <rect x="342" y="180" width="70" height="6" rx="2" fill="#389e0d" opacity="0.2" />
        <rect x="342" y="194" width="95" height="6" rx="2" fill="#389e0d" opacity="0.15" />
        <rect x="342" y="208" width="55" height="6" rx="2" fill="#389e0d" opacity="0.2" />
        <rect x="342" y="222" width="85" height="6" rx="2" fill="#389e0d" opacity="0.15" />
        <rect x="342" y="236" width="75" height="6" rx="2" fill="#389e0d" opacity="0.2" />
      </g>
      <text x="395" y="275" textAnchor="middle" fontSize="10" fontWeight="600" fill="#389e0d" fontFamily="system-ui">Veeva Vault</text>

      {/* === COMPARISON LINES between panels === */}
      {/* Dashed lines connecting matching rows — validation check */}
      <line x1="150" y1="127" x2="330" y2="127" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
      <line x1="150" y1="141" x2="330" y2="141" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
      <line x1="150" y1="155" x2="330" y2="155" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
      <line x1="150" y1="169" x2="330" y2="169" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
      <line x1="150" y1="183" x2="330" y2="183" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />
      <line x1="150" y1="197" x2="330" y2="197" stroke="#d9d9d9" strokeWidth="1" strokeDasharray="4 3" opacity="0.5" />

      {/* Check / cross marks on comparison lines */}
      <g fontSize="12" fontFamily="system-ui">
        <text x="237" y="131" textAnchor="middle" fill="#52c41a" fontWeight="bold">&#x2713;</text>
        <text x="237" y="145" textAnchor="middle" fill="#52c41a" fontWeight="bold">&#x2713;</text>
        <text x="237" y="159" textAnchor="middle" fill="#ff4d4f" fontWeight="bold">&#x2717;</text>
        <text x="237" y="173" textAnchor="middle" fill="#52c41a" fontWeight="bold">&#x2713;</text>
        <text x="237" y="187" textAnchor="middle" fill="#faad14" fontWeight="bold">!</text>
        <text x="237" y="201" textAnchor="middle" fill="#52c41a" fontWeight="bold">&#x2713;</text>
      </g>

      {/* Scanning animation line */}
      <line x1="155" y1="0" x2="325" y2="0" stroke="#667eea" strokeWidth="2" opacity="0.5">
        <animateMotion path="M0 120 L0 210" dur="3s" repeatCount="indefinite" />
      </line>

      {/* === PERSON SITTING WITH LENS === */}
      <g transform="translate(190, 195)">
        {/* Chair */}
        <rect x="15" y="75" width="60" height="5" rx="2" fill="#8c8c8c" />
        <rect x="20" y="80" width="4" height="25" rx="2" fill="#8c8c8c" />
        <rect x="66" y="80" width="4" height="25" rx="2" fill="#8c8c8c" />
        <rect x="63" y="48" width="5" height="30" rx="2" fill="#8c8c8c" />
        <rect x="22" y="48" width="5" height="30" rx="2" fill="#8c8c8c" />
        <rect x="22" y="44" width="46" height="7" rx="3" fill="#a0a0a0" />
        {/* Torso */}
        <rect x="30" y="32" width="28" height="40" rx="7" fill="#5b6abf" />
        {/* Legs */}
        <rect x="30" y="64" width="11" height="18" rx="4" fill="#3d4a9e" />
        <rect x="47" y="64" width="11" height="18" rx="4" fill="#3d4a9e" />
        {/* Shoes */}
        <ellipse cx="36" cy="83" rx="7" ry="3.5" fill="#2a2a2a" />
        <ellipse cx="53" cy="83" rx="7" ry="3.5" fill="#2a2a2a" />
        {/* Arms — reaching toward both panels */}
        <rect x="12" y="38" width="9" height="26" rx="4" fill="#f5c6a0" transform="rotate(-20, 16, 38)" />
        <rect x="67" y="38" width="9" height="26" rx="4" fill="#f5c6a0" transform="rotate(20, 72, 38)" />
        {/* Head */}
        <circle cx="44" cy="20" r="16" fill="#f5c6a0" />
        {/* Hair */}
        <path d="M28 15 Q 31 0 44 3 Q 57 0 60 15 Q 62 8 57 4 Q 49 -4 39 -4 Q 30 -4 26 6 Z" fill="#4a3728" />
        {/* Eyes — looking down at data */}
        <circle cx="38" cy="20" r="2" fill="#2a2a2a" />
        <circle cx="50" cy="20" r="2" fill="#2a2a2a" />
        <circle cx="39" cy="19" r="0.7" fill="#fff" />
        <circle cx="51" cy="19" r="0.7" fill="#fff" />
        {/* Focused expression */}
        <path d="M40 26 Q 44 28 48 26" stroke="#c4956a" strokeWidth="1.2" fill="none" strokeLinecap="round" />
        {/* Glasses */}
        <circle cx="38" cy="20" r="5.5" stroke="#555" strokeWidth="1.3" fill="none" />
        <circle cx="50" cy="20" r="5.5" stroke="#555" strokeWidth="1.3" fill="none" />
        <line x1="43.5" y1="20" x2="44.5" y2="20" stroke="#555" strokeWidth="1.3" />
        <line x1="32.5" y1="19" x2="29" y2="17" stroke="#555" strokeWidth="1.3" />
        <line x1="55.5" y1="19" x2="59" y2="17" stroke="#555" strokeWidth="1.3" />
      </g>

      {/* === MAGNIFYING LENS (center, over comparison area) === */}
      <g filter="glow">
        <rect x="255" y="225" width="5" height="28" rx="2.5" fill="#8c6e3d" transform="rotate(-40, 257, 239)" />
        <circle cx="240" cy="210" r="30" stroke="#b8860b" strokeWidth="4" fill="url(#lensGrad)" />
        <path d="M224 200 Q 230 190 242 192" stroke="#fff" strokeWidth="1.8" fill="none" opacity="0.5" strokeLinecap="round" />
      </g>

      {/* Data comparison visible through lens */}
      <g opacity="0.9" fontFamily="monospace" fontSize="7">
        <text x="224" y="204" fill="#52c41a" fontWeight="bold">Account &#x2713;</text>
        <text x="224" y="214" fill="#ff4d4f" fontWeight="bold">Call_vod &#x2717;</text>
        <text x="224" y="224" fill="#52c41a" fontWeight="bold">Contact &#x2713;</text>
      </g>

      {/* === RESULT BADGE (top center) === */}
      <g filter="shadow">
        <rect x="195" y="42" width="90" height="28" rx="14" fill="#fff" />
        <circle cx="212" cy="56" r="6" fill="#52c41a" opacity="0.15" />
        <text x="212" y="59" textAnchor="middle" fontSize="9" fill="#52c41a" fontWeight="bold">&#x2713;</text>
        <text x="240" y="60" fontSize="10" fill="#333" fontWeight="600" fontFamily="system-ui">85% Match</text>
      </g>

      {/* Pulsing validation indicator */}
      <circle cx="240" cy="56" r="0" fill="#52c41a" opacity="0">
        <animate attributeName="r" values="0;20;0" dur="3s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.2;0;0.2" dur="3s" repeatCount="indefinite" />
      </circle>

      {/* Bottom label */}
      <text x="240" y="340" textAnchor="middle" fontSize="13" fontWeight="600" fill="#5b6abf" fontFamily="system-ui" letterSpacing="0.5">
        Validating &amp; Comparing Migrated Data
      </text>
    </svg>
  );
}
