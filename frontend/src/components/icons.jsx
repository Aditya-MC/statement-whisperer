/** Small inline stroke icons (1.6px, rounded), so the app needs no icon package. */
function Svg({ size = 20, children, ...rest }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconDashboard = (p) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
    <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
    <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
  </Svg>
);

export const IconList = (p) => (
  <Svg {...p}>
    <path d="M9 6.5h11M9 12h11M9 17.5h11" />
    <circle cx="4.75" cy="6.5" r="0.9" fill="currentColor" />
    <circle cx="4.75" cy="12" r="0.9" fill="currentColor" />
    <circle cx="4.75" cy="17.5" r="0.9" fill="currentColor" />
  </Svg>
);

export const IconUpload = (p) => (
  <Svg {...p}>
    <path d="M12 15.5V4M7.5 8.5 12 4l4.5 4.5" />
    <path d="M4 14.5v3a2.5 2.5 0 0 0 2.5 2.5h11a2.5 2.5 0 0 0 2.5-2.5v-3" />
  </Svg>
);

export const IconTag = (p) => (
  <Svg {...p}>
    <path d="M3.5 12.1V5a1.5 1.5 0 0 1 1.5-1.5h7.1a1.5 1.5 0 0 1 1.06.44l7.4 7.4a1.5 1.5 0 0 1 0 2.12l-7.1 7.1a1.5 1.5 0 0 1-2.12 0l-7.4-7.4a1.5 1.5 0 0 1-.44-1.06Z" />
    <circle cx="8.25" cy="8.25" r="1.4" />
  </Svg>
);

export const IconUser = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="8.5" r="3.75" />
    <path d="M4.5 20c1.2-3.6 4.1-5.5 7.5-5.5s6.3 1.9 7.5 5.5" />
  </Svg>
);

export const IconSun = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2.75v1.5M12 19.75v1.5M2.75 12h1.5M19.75 12h1.5M5.46 5.46l1.06 1.06M17.48 17.48l1.06 1.06M5.46 18.54l1.06-1.06M17.48 6.52l1.06-1.06" />
  </Svg>
);

export const IconMoon = (p) => (
  <Svg {...p}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />
  </Svg>
);

export const IconMonitor = (p) => (
  <Svg {...p}>
    <rect x="3" y="4.5" width="18" height="12" rx="2.5" />
    <path d="M9 20h6M12 16.5V20" />
  </Svg>
);

export const IconPlus = (p) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const IconWallet = (p) => (
  <Svg {...p}>
    <path d="M19 7.5V6a2 2 0 0 0-2-2H6a2.5 2.5 0 0 0 0 5h13a1.5 1.5 0 0 1 1.5 1.5V18a2 2 0 0 1-2 2H6a2.5 2.5 0 0 1-2.5-2.5v-11" />
    <circle cx="16.5" cy="14.5" r="1.1" fill="currentColor" />
  </Svg>
);

export const IconArrowDown = (p) => (
  <Svg {...p}>
    <path d="M12 5v14M6.5 13.5 12 19l5.5-5.5" />
  </Svg>
);

export const IconArrowUp = (p) => (
  <Svg {...p}>
    <path d="M12 19V5M6.5 10.5 12 5l5.5 5.5" />
  </Svg>
);

export const IconPiggy = (p) => (
  <Svg {...p}>
    <path d="M5 11.5C5 8.5 8 6 12 6c1.5 0 2.9.35 4 .95L19 5.5v3.2c.8.8 1.3 1.75 1.45 2.8H21.5v3h-1.4a6 6 0 0 1-2.1 2.4V20h-3v-1.6a9 9 0 0 1-3 0V20H9v-2.1C6.6 16.8 5 14.3 5 11.5Z" />
    <circle cx="16" cy="10.5" r="0.8" fill="currentColor" />
  </Svg>
);

export const IconPercent = (p) => (
  <Svg {...p}>
    <path d="M18.5 5.5 5.5 18.5" />
    <circle cx="7" cy="7" r="2.25" />
    <circle cx="17" cy="17" r="2.25" />
  </Svg>
);

export const IconSearch = (p) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m20 20-4.2-4.2" />
  </Svg>
);
