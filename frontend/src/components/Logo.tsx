/**
 * SFDC Dev Agent brand mark: a cloud + code-brackets glyph in Salesforce blue,
 * optionally followed by the wordmark. Used in the app header and login hero so
 * the branding stays consistent in one place.
 */
type LogoProps = {
  size?: number;
  showText?: boolean;
  /** Colour of the wordmark text (glyph colours are fixed). */
  textColor?: string;
};

export default function Logo({
  size = 32,
  showText = true,
  textColor = "#fff",
}: LogoProps) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
      <svg
        viewBox="0 0 64 64"
        width={size}
        height={size}
        aria-label="SFDC Dev Agent logo"
        role="img"
      >
        <defs>
          <linearGradient id="ona-logo-g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#00A1E0" />
            <stop offset="1" stopColor="#1677ff" />
          </linearGradient>
        </defs>
        <rect width="64" height="64" rx="14" fill="url(#ona-logo-g)" />
        <path
          fill="#fff"
          opacity={0.95}
          d="M43 40a8 8 0 0 0-1.2-15.9 11 11 0 0 0-20.9 3.2A7.5 7.5 0 0 0 22 42h20a1 1 0 0 0 1-1z"
        />
        <path
          fill="none"
          stroke="#00A1E0"
          strokeWidth={2.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M27 30l-4 4 4 4"
        />
        <path
          fill="none"
          stroke="#00A1E0"
          strokeWidth={2.6}
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M37 30l4 4-4 4"
        />
      </svg>
      {showText && (
        <span
          style={{
            display: "inline-flex",
            flexDirection: "column",
            lineHeight: 1.1,
          }}
        >
          <span style={{ fontWeight: 700, fontSize: 16, color: textColor }}>
            SFDC Dev Agent
          </span>
          <span
            style={{
              fontSize: 10,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              opacity: 0.65,
              color: textColor,
            }}
          >
            AI for Salesforce delivery
          </span>
        </span>
      )}
    </span>
  );
}
