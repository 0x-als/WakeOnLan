function svgIcon(body) {
  return '<svg viewBox="0 0 24 24" aria-hidden="true">' + body + "</svg>";
}

const Icons = {
  power: svgIcon('<path d="M12 3v9"/><path d="M6.3 7.3a8 8 0 1 0 11.4 0"/>'),
  sliders: svgIcon('<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>'),
  plus: svgIcon('<path d="M12 5v14M5 12h14"/>'),
  search: svgIcon('<circle cx="11" cy="11" r="6"/><path d="m20 20-4.2-4.2"/>'),
  close: svgIcon('<path d="M6 6l12 12M18 6 6 18"/>'),
  more: svgIcon('<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'),
  monitor: svgIcon('<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>'),
  copy: svgIcon('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>'),
  refresh: svgIcon('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>'),
  trash: svgIcon('<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>')
};
