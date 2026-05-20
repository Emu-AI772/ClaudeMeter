let els;
let statusState = {};
let translations = {};
let textTimerId = null;
let currentMode = 'basic';   // 'basic' | 'dials' | 'led'
let currentView = 'usage';   // 'usage' | 'history'
let lastUsageData = null;
let currentAnchor = 'tray';  // 'tray'|'tr'|'tl'|'br'|'bl'|'float'
let compactMode = false;
let historyRange = '24h';  // '24h'|'7d'|'30d'|'all'|'custom'
let alwaysOnTop = true;

// ─── Init ────────────────────────────────────────────────────────────────────

function init(config) {
    const s = document.documentElement.style;
    for (const [key, value] of Object.entries(config.colors)) {
        s.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }

    translations = config.t;
    document.getElementById('title').textContent = translations.title;
    document.getElementById('headingAccount').textContent = translations.account;
    document.getElementById('labelEmail').textContent = translations.email;
    document.getElementById('labelPlan').textContent = translations.plan;
    document.getElementById('headingUsage').textContent = translations.usage;
    document.getElementById('headingUsageDials').textContent = translations.usage;
    document.getElementById('headingUsageLed').textContent = translations.usage;
    document.getElementById('headingExtraUsage').textContent = translations.extra_usage;

    document.getElementById('closeBtn').addEventListener('click', () => pywebview.api.close());
    document.getElementById('appVersion').textContent = config.app_version;

    // Load prefs from Python (persisted server-side) — must be before any pref usage
    const prefs = config.prefs || {};
    currentMode = prefs.display_mode || 'basic';
    currentView = prefs.view || 'usage';
    currentAnchor = prefs.anchor || 'tray';
    alwaysOnTop = prefs.always_on_top !== undefined ? prefs.always_on_top : true;
    compactMode = prefs.compact || false;
    currentTheme = prefs.theme || 'default';
    const notifySessionPct = prefs.notify_session_pct !== undefined ? prefs.notify_session_pct : 80;
    const notifyWeeklyPct  = prefs.notify_weekly_pct  !== undefined ? prefs.notify_weekly_pct  : 80;
    const notifyOnReset    = prefs.notify_on_reset    !== undefined ? prefs.notify_on_reset    : false;
    const autostartEnabled = prefs.autostart !== undefined ? prefs.autostart : false;

    // Theme buttons
    _initThemeButtons();
    if (currentTheme === 'custom' && config.custom_theme && Object.keys(config.custom_theme).length) {
        // Restore saved custom colours
        const s = document.documentElement.style;
        for (const [k, v] of Object.entries(config.custom_theme)) {
            s.setProperty(`--${k.replaceAll('_','-')}`, v);
        }
        document.querySelectorAll('.mode-btn[data-theme]').forEach(b =>
            b.classList.toggle('active', b.dataset.theme === 'custom'));
        // Pre-fill RGB inputs
        const map = {
            rgb_bg: config.custom_theme.bg,
            rgb_bar_fg: config.custom_theme.bar_fg,
            rgb_bar_fg_warn: config.custom_theme.bar_fg_warn,
            rgb_fg: config.custom_theme.fg,
            rgb_fg_dim: config.custom_theme.fg_dim,
        };
        for (const [id, val] of Object.entries(map)) {
            const el = document.getElementById(id);
            if (el && val) el.value = val;
        }
    } else if (currentTheme === 'system') {
        applySystemTheme(config.system_theme || 'dark');
    } else {
        // Apply theme (including 'default') to ensure button highlights correctly
        _applyTheme(currentTheme || 'default');
    }
    // Always track system theme for potential switch later
    systemTheme = config.system_theme || 'dark';

    // RGB custom colour picker
    _initRgbPicker();

    // Minimise / compact toggle
    document.getElementById('minimiseBtn').addEventListener('click', () => {
        compactMode = !compactMode;
        _savePrefToServer('compact', compactMode);
        _applyCompactMode();
    });

    els = {
        accountSection:   document.getElementById('accountSection'),
        emailRow:         document.getElementById('emailRow'),
        emailValue:       document.getElementById('emailValue'),
        planRow:          document.getElementById('planRow'),
        planValue:        document.getElementById('planValue'),
        usageSection:     document.getElementById('usageSection'),
        usageBars:        document.getElementById('usageBars'),
        dialsSection:     document.getElementById('dialsSection'),
        dialsContainer:   document.getElementById('dialsContainer'),
        ledSection:       document.getElementById('ledSection'),
        ledContainer:     document.getElementById('ledContainer'),
        historySection:   document.getElementById('historySection'),
        historyContainer: document.getElementById('historyContainer'),
        extraSection:     document.getElementById('extraSection'),
        extraSpent:       document.getElementById('extraSpent'),
        extraPct:         document.getElementById('extraPct'),
        extraFill:        document.getElementById('extraFill'),

        statusSection:    document.getElementById('statusSection'),
        statusText:       document.getElementById('statusText'),
        modeSelector:     document.getElementById('modeSelector'),
        compactSection:   document.getElementById('compactSection'),
        compactBars:      document.getElementById('compactBars'),
        aotToggle:        document.getElementById('aotToggle'),
        anchorGrid:       document.getElementById('anchorGrid'),
        historyPath:      document.getElementById('historyPath'),
        installSection:   document.getElementById('installSection'),
        installRows:      document.getElementById('installRows'),
    };

    // Apply loaded prefs to UI
    _applyModeButtons();
    _applyAnchorGrid();
    if (els.aotToggle) els.aotToggle.checked = alwaysOnTop;
    if (els.historyPath && config.history_path) {
        els.historyPath.textContent = config.history_path;
    }

    // Gear / settings toggle
    document.getElementById('viewToggle').addEventListener('click', () => {
        els.modeSelector.classList.toggle('hidden');
        // Scroll settings to top when opening
        if (!els.modeSelector.classList.contains('hidden')) {
            els.modeSelector.scrollTop = 0;
        }
    });

    // Mode buttons
    document.querySelectorAll('.mode-btn[data-mode]').forEach(btn => {
        btn.addEventListener('click', () => {
            currentMode = btn.dataset.mode;
            _savePrefToServer('display_mode', currentMode);
            _applyModeButtons();
            if (lastUsageData) renderUsage(lastUsageData);
        });
    });

    // View buttons
    document.querySelectorAll('.mode-btn[data-view]').forEach(btn => {
        btn.addEventListener('click', () => {
            currentView = btn.dataset.view;
            _savePrefToServer('view', currentView);
            _applyModeButtons();
            _renderView();
        });
    });

    // Autostart toggle
    const autostartToggle = document.getElementById('autostartToggle');
    if (autostartToggle) {
        autostartToggle.checked = autostartEnabled;
        autostartToggle.addEventListener('change', () => {
            pywebview.api.set_autostart(autostartToggle.checked);
        });
        // Load actual state from OS on open
        if (window.pywebview?.api?.get_autostart) {
            pywebview.api.get_autostart().then(v => { autostartToggle.checked = !!v; });
        }
    }

    // Notification threshold inputs
    const sessionPctEl = document.getElementById('notifySessionPct');
    const weeklyPctEl  = document.getElementById('notifyWeeklyPct');
    const resetToggle  = document.getElementById('notifyResetToggle');

    if (sessionPctEl) {
        sessionPctEl.value = notifySessionPct;
        sessionPctEl.addEventListener('change', () => {
            const v = Math.min(99, Math.max(1, parseInt(sessionPctEl.value) || 80));
            sessionPctEl.value = v;
            pywebview.api.save_notify_prefs(v, parseInt(weeklyPctEl?.value || 80), resetToggle?.checked || false);
        });
    }
    if (weeklyPctEl) {
        weeklyPctEl.value = notifyWeeklyPct;
        weeklyPctEl.addEventListener('change', () => {
            const v = Math.min(99, Math.max(1, parseInt(weeklyPctEl.value) || 80));
            weeklyPctEl.value = v;
            pywebview.api.save_notify_prefs(parseInt(sessionPctEl?.value || 80), v, resetToggle?.checked || false);
        });
    }
    if (resetToggle) {
        resetToggle.checked = notifyOnReset;
        resetToggle.addEventListener('change', () => {
            pywebview.api.save_notify_prefs(
                parseInt(sessionPctEl?.value || 80),
                parseInt(weeklyPctEl?.value  || 80),
                resetToggle.checked
            );
        });
    }

    // Always on top toggle
    if (els.aotToggle) {
        els.aotToggle.addEventListener('change', () => {
            alwaysOnTop = els.aotToggle.checked;
            pywebview.api.set_always_on_top(alwaysOnTop);
        });
    }

    // Anchor grid buttons
    document.querySelectorAll('.anchor-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            currentAnchor = btn.dataset.anchor;
            _applyAnchorGrid();
            pywebview.api.set_anchor(currentAnchor);
        });
    });

    // Open history file button
    const openHistoryBtn = document.getElementById('openHistoryBtn');
    if (openHistoryBtn) {
        openHistoryBtn.addEventListener('click', () => pywebview.api.open_history_file());
    }
    const openLogFolderBtn = document.getElementById('openLogFolderBtn');
    if (openLogFolderBtn) {
        openLogFolderBtn.addEventListener('click', () => pywebview.api.open_log_folder());
    }

    // History toolbar
    _initHistoryToolbar();

    // Wire both summary buttons (one in history toolbar, one in settings)
    ['openSummaryBtn', 'openSummaryBtn2'].forEach(id => {
        const btn = document.getElementById(id);
        if (btn) btn.addEventListener('click', () => pywebview.api.open_summary_file());
    });

    const testNotifyBtn = document.getElementById('testNotifyBtn');
    if (testNotifyBtn) {
        testNotifyBtn.addEventListener('click', () => {
            testNotifyBtn.textContent = 'Sent!';
            testNotifyBtn.disabled = true;
            pywebview.api.test_notification();
            setTimeout(() => {
                testNotifyBtn.textContent = 'Test';
                testNotifyBtn.disabled = false;
            }, 3000);
        });
    }

    // Drag — make the entire header draggable in any non-tray anchor mode
    _initDrag();

    updateData(config.data);
    _applyCompactMode();
    loadYesterdaySummary();
    requestAnimationFrame(() => document.body.classList.add('open'));
}

// ─── Data update ─────────────────────────────────────────────────────────────

function updateData(data) {
    const hasProfile = !!data.profile;
    els.accountSection.classList.toggle('visible', hasProfile);
    if (hasProfile) {
        els.emailValue.textContent = data.profile.email;
        els.emailRow.style.display = data.profile.email ? '' : 'none';
        els.planValue.textContent = data.profile.plan;
        els.planRow.style.display = data.profile.plan ? '' : 'none';
    }

    const hasUsage = !!data.usage?.length;
    if (hasUsage) {
        lastUsageData = data.usage;
        if (compactMode) renderCompact(data.usage);
    }
    // Hide all usage sections first; _renderView re-shows the right one
    els.usageSection.classList.remove('visible');
    els.dialsSection.classList.remove('visible');
    els.ledSection.classList.remove('visible');
    els.historySection.classList.remove('visible');
    _renderView();

    const hasExtra = !!data.extra;
    // Store extra data for view-aware rendering
    if (hasExtra) {
        els._extraData = data.extra;
    }
    _updateExtraVisibility();

    const hasInstalls = !!data.installations?.length;
    els._installsVisible = hasInstalls;
    if (els.installSection && hasInstalls) {
        // Render as single inline row: "Claude Code  CLI  2.1.143"
        els.installRows.replaceChildren();
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:8px';
        const label = document.createElement('dt');
        label.style.color = 'var(--fg-dim)';
        label.textContent = translations.claude_code || 'Claude Code';
        row.appendChild(label);
        const versions = document.createElement('dd');
        versions.style.cssText = 'display:flex;gap:16px;margin:0';
        data.installations.forEach(inst => {
            const v = document.createElement('span');
            v.textContent = `${inst.name}  ${inst.version}`;
            versions.appendChild(v);
        });
        row.appendChild(versions);
        els.installRows.appendChild(row);
    }

    updateStatus(data.status);
}

// ─── View routing ─────────────────────────────────────────────────────────────

function _renderView() {
    if (currentView === 'history') {
        els.usageSection.classList.remove('visible');
        els.dialsSection.classList.remove('visible');
        els.ledSection.classList.remove('visible');
        els.historySection.classList.add('visible');
        renderHistory();
        // Force popup to stay open on history tab (has its own content to browse)
        if (window.pywebview?.api) {
            pywebview.api.set_force_open(true);
            pywebview.api.set_always_on_top(true);
        }
    } else {
        els.historySection.classList.remove('visible');
        if (lastUsageData) renderUsage(lastUsageData);
        // Release forced-open state when leaving history
        if (window.pywebview?.api) {
            pywebview.api.set_force_open(false);
        }
    }
    _updateExtraVisibility();
}

function _updateExtraVisibility() {
    const isHistory = currentView === 'history';
    const hasExtra = !!els._extraData;
    // Extra usage and CLI only show on usage view
    els.extraSection.classList.toggle('visible', hasExtra && !isHistory);
    if (hasExtra && !isHistory) {
        els.extraSpent.textContent = els._extraData.spent_text;
        els.extraPct.textContent = els._extraData.pct_text;
        els.extraFill.style.width = `${els._extraData.fill_pct * 100}%`;
    }
    if (els.installSection) {
        els.installSection.classList.toggle('visible', !isHistory && !!els._installsVisible);
    }
}

// ─── Display modes ────────────────────────────────────────────────────────────

function renderUsage(entries) {
    if (currentView === 'history') return;

    els.usageSection.classList.remove('visible');
    els.dialsSection.classList.remove('visible');
    els.ledSection.classList.remove('visible');

    if (currentMode === 'dials') {
        els.dialsSection.classList.add('visible');
        renderDials(entries);
    } else if (currentMode === 'led') {
        els.ledSection.classList.add('visible');
        renderLed(entries);
    } else {
        els.usageSection.classList.add('visible');
        updateUsageBars(entries);
    }
}

// ─── BASIC MODE ──────────────────────────────────────────────────────────────

function updateUsageBars(entries) {
    if (entries.length !== els.usageBars.children.length) {
        els.usageBars.replaceChildren(...entries.map(createBarElement));
        requestAnimationFrame(() => {
            for (let i = 0; i < entries.length; i++) {
                els.usageBars.children[i].querySelector('.bar-fill').style.width =
                    `${entries[i].fill_pct * 100}%`;
            }
        });
    } else {
        for (let i = 0; i < entries.length; i++) {
            updateBarElement(els.usageBars.children[i], entries[i]);
        }
    }
}

function createBarElement(entry) {
    const div = document.createElement('div');
    div.className = 'usage-entry';

    const header = document.createElement('div');
    header.className = 'bar-header';
    const label = document.createElement('span');
    label.textContent = entry.label;
    const pct = document.createElement('span');
    pct.className = 'bar-pct';
    pct.textContent = entry.pct_text;
    header.append(label, pct);

    const container = document.createElement('div');
    container.className = 'bar-container';
    const fill = document.createElement('div');
    fill.className = 'bar-fill';
    fill.classList.toggle('warn', entry.warn);
    fill.style.width = '0%';
    container.appendChild(fill);

    for (const pos of entry.midnights) {
        const d = document.createElement('div');
        d.className = 'bar-divider';
        d.style.left = `calc(${pos * 100}% - 1px)`;
        container.appendChild(d);
    }

    if (entry.marker_rel !== null) {
        const marker = document.createElement('div');
        marker.className = 'bar-marker';
        marker.style.left = `calc(${entry.marker_rel * 100}% - 1px)`;
        container.appendChild(marker);
    }

    div.append(header, container);

    if (entry.reset_text) {
        const reset = document.createElement('div');
        reset.className = 'reset-text';
        reset.textContent = entry.reset_text;
        div.appendChild(reset);
    }

    return div;
}

function updateBarElement(div, entry) {
    div.querySelector('.bar-pct').textContent = entry.pct_text;

    const fill = div.querySelector('.bar-fill');
    fill.style.width = `${entry.fill_pct * 100}%`;
    fill.classList.toggle('warn', entry.warn);

    const container = div.querySelector('.bar-container');
    let marker = container.querySelector('.bar-marker');
    if (entry.marker_rel !== null) {
        if (!marker) {
            marker = document.createElement('div');
            marker.className = 'bar-marker';
            container.appendChild(marker);
        }
        marker.style.left = `${entry.marker_rel * 100}%`;
    } else if (marker) {
        marker.remove();
    }

    for (const d of container.querySelectorAll('.bar-divider')) d.remove();
    for (const pos of entry.midnights) {
        const d = document.createElement('div');
        d.className = 'bar-divider';
        d.style.left = `${pos * 100}%`;
        container.appendChild(d);
    }

    let resetEl = div.querySelector('.reset-text');
    if (entry.reset_text) {
        if (resetEl) {
            resetEl.textContent = entry.reset_text;
        } else {
            resetEl = document.createElement('div');
            resetEl.className = 'reset-text';
            resetEl.textContent = entry.reset_text;
            div.appendChild(resetEl);
        }
    } else if (resetEl) {
        resetEl.remove();
    }
}

// ─── DIALS MODE ───────────────────────────────────────────────────────────────

function renderDials(entries) {
    els.dialsContainer.replaceChildren(...entries.map(createDialElement));
}

function createDialElement(entry) {
    const pct = entry.fill_pct * 100;
    const warn = entry.warn;

    const div = document.createElement('div');
    div.className = 'dial-entry';

    // SVG dial
    const size = 90;
    const cx = size / 2, cy = size / 2;
    const r = 34;
    const strokeW = 7;

    // Arc from -210deg to +30deg (240deg sweep), starting bottom-left
    const startAngle = 210; // degrees from 3-o'clock, going CW
    const sweep = 240;
    const fillAngle = sweep * Math.min(pct, 100) / 100;

    const trackPath = _arcPath(cx, cy, r, startAngle, sweep);
    const fillPath  = _arcPath(cx, cy, r, startAngle, fillAngle);

    // Color transitions: green → amber → red
    let fillColor;
    if (pct >= 80 || warn) {
        fillColor = 'var(--bar-fg-warn)';
    } else if (pct >= 50) {
        fillColor = '#f59e0b';
    } else {
        fillColor = 'var(--bar-fg)';
    }

    // Time marker line
    const markerAngle = entry.marker_rel !== null
        ? startAngle + sweep * entry.marker_rel
        : null;

    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size}`);
    svg.setAttribute('width', size);
    svg.setAttribute('height', size);
    svg.classList.add('dial-svg');

    // Track
    const track = document.createElementNS(ns, 'path');
    track.setAttribute('d', trackPath);
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', 'var(--bar-bg)');
    track.setAttribute('stroke-width', strokeW);
    track.setAttribute('stroke-linecap', 'round');
    svg.appendChild(track);

    // Fill
    if (fillAngle > 0) {
        const fill = document.createElementNS(ns, 'path');
        fill.setAttribute('d', fillPath);
        fill.setAttribute('fill', 'none');
        fill.setAttribute('stroke', fillColor);
        fill.setAttribute('stroke-width', strokeW);
        fill.setAttribute('stroke-linecap', 'round');
        svg.appendChild(fill);
    }

    // Time marker
    if (markerAngle !== null) {
        const rad = (markerAngle - 90) * Math.PI / 180;
        const inner = r - strokeW / 2 - 1;
        const outer = r + strokeW / 2 + 1;
        const x1 = cx + inner * Math.cos(rad);
        const y1 = cy + inner * Math.sin(rad);
        const x2 = cx + outer * Math.cos(rad);
        const y2 = cy + outer * Math.sin(rad);
        const ml = document.createElementNS(ns, 'line');
        ml.setAttribute('x1', x1); ml.setAttribute('y1', y1);
        ml.setAttribute('x2', x2); ml.setAttribute('y2', y2);
        ml.setAttribute('stroke', 'var(--bar-marker)');
        ml.setAttribute('stroke-width', 2);
        svg.appendChild(ml);
    }

    // Centre percentage text
    const txt = document.createElementNS(ns, 'text');
    txt.setAttribute('x', cx);
    txt.setAttribute('y', cy + 5);
    txt.setAttribute('text-anchor', 'middle');
    txt.setAttribute('fill', 'var(--fg-heading)');
    txt.setAttribute('font-size', '14');
    txt.setAttribute('font-weight', 'bold');
    txt.setAttribute('font-family', 'system-ui, sans-serif');
    txt.textContent = entry.pct_text;
    svg.appendChild(txt);

    div.appendChild(svg);

    const labelEl = document.createElement('div');
    labelEl.className = 'dial-label';
    labelEl.textContent = entry.label;
    div.appendChild(labelEl);

    if (entry.reset_text) {
        const resetEl = document.createElement('div');
        resetEl.className = 'dial-reset';
        resetEl.textContent = entry.reset_text;
        div.appendChild(resetEl);
    }

    return div;
}

function _arcPath(cx, cy, r, startDeg, sweepDeg) {
    if (sweepDeg <= 0) return '';
    const clamp = Math.min(sweepDeg, 359.99);
    const start = _polar(cx, cy, r, startDeg);
    const end   = _polar(cx, cy, r, startDeg + clamp);
    const large = clamp > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 1 ${end.x} ${end.y}`;
}

function _polar(cx, cy, r, deg) {
    const rad = (deg - 90) * Math.PI / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

// ─── LED MODE ─────────────────────────────────────────────────────────────────

const LED_ROWS = 24;      // number of segments tall
const LED_SEGMENT_H = 7;  // px height per segment
const LED_GAP = 2;        // px gap between segments

function renderLed(entries) {
    els.ledContainer.replaceChildren();

    const grid = document.createElement('div');
    grid.style.cssText = 'display:flex;gap:8px;justify-content:center;align-items:stretch';

    entries.forEach(entry => {
        const col = createLedColumn(entry);
        grid.appendChild(col);
    });

    els.ledContainer.appendChild(grid);
}

function createLedColumn(entry) {
    const pct = entry.fill_pct * 100;
    const litCount = Math.round(LED_ROWS * Math.min(pct, 100) / 100);
    const markerRow = entry.marker_rel !== null
        ? Math.round(entry.marker_rel * LED_ROWS)
        : null;

    // Outer column — flex column, fixed width, full stretch height
    const col = document.createElement('div');
    col.style.cssText = 'display:flex;flex-direction:column;align-items:center;flex:1;min-width:0';

    // Stack wrapper: fixed height so all columns align at top
    const totalStackH = LED_ROWS * (LED_SEGMENT_H + LED_GAP) - LED_GAP;
    const stackWrap = document.createElement('div');
    stackWrap.style.cssText = `height:${totalStackH}px;flex-shrink:0;display:flex;flex-direction:column;justify-content:flex-start;width:100%`;

    // The LED stack itself
    const stack = document.createElement('div');
    stack.style.cssText = `display:flex;flex-direction:column;gap:${LED_GAP}px;width:100%`;

    for (let i = 0; i < LED_ROWS; i++) {
        const seg = document.createElement('div');
        const rowFromBottom = LED_ROWS - 1 - i;
        const isLit = rowFromBottom < litCount;
        const isMarker = markerRow !== null && rowFromBottom === markerRow;

        seg.style.cssText = `width:100%;height:${LED_SEGMENT_H}px;border-radius:2px;transition:background 0.3s`;

        if (isLit) {
            const segPct = (rowFromBottom / LED_ROWS) * 100;
            if (segPct >= 80 || entry.warn) {
                seg.style.background = 'var(--bar-fg-warn)';
                seg.style.boxShadow = '0 0 4px var(--bar-fg-warn)';
            } else if (segPct >= 60) {
                seg.style.background = '#f59e0b';
                seg.style.boxShadow = '0 0 4px #f59e0b88';
            } else {
                seg.style.background = 'var(--bar-fg)';
                seg.style.boxShadow = '0 0 4px var(--bar-fg)66';
            }
        } else {
            seg.style.background = 'var(--bar-bg)';
            seg.style.boxShadow = 'none';
        }

        if (isMarker) {
            seg.style.outline = '1px solid var(--bar-marker)';
            seg.style.outlineOffset = '1px';
        }

        stack.appendChild(seg);
    }

    stackWrap.appendChild(stack);
    col.appendChild(stackWrap);

    // Fixed-height footer area so all columns align at bottom
    const footer = document.createElement('div');
    footer.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:2px;padding-top:6px;width:100%';

    const pctEl = document.createElement('div');
    pctEl.style.cssText = `font-size:13px;font-weight:700;text-align:center;color:${entry.warn ? 'var(--bar-fg-warn)' : 'var(--fg-heading)'}`;
    pctEl.textContent = entry.pct_text;
    footer.appendChild(pctEl);

    const labelEl = document.createElement('div');
    labelEl.style.cssText = 'font-size:10px;color:var(--fg-dim);text-align:center;width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
    labelEl.textContent = entry.label;
    footer.appendChild(labelEl);

    const resetEl = document.createElement('div');
    resetEl.style.cssText = 'font-size:10px;color:var(--fg-dim);text-align:center;min-height:14px';
    resetEl.textContent = entry.reset_text || '';
    footer.appendChild(resetEl);

    col.appendChild(footer);
    return col;
}

// ─── HISTORY VIEW ─────────────────────────────────────────────────────────────

function renderHistory() {
    els.historyContainer.replaceChildren();

    const loading = document.createElement('div');
    loading.className = 'history-empty';
    loading.textContent = 'Loading history…';
    els.historyContainer.appendChild(loading);

    pywebview.api.get_history().then(history => {
        els.historyContainer.replaceChildren();

        // Apply range filter
        const cutoff  = _getHistoryCutoff();
        const ceiling = _getHistoryCeiling();
        history = (history || []).filter(s => s.ts >= cutoff && s.ts <= ceiling);

        if (!history || !history.length) {
            const empty = document.createElement('div');
            empty.className = 'history-empty';
            empty.textContent = 'No history yet. Snapshots are saved every 30 minutes.';
            els.historyContainer.appendChild(empty);
            return;
        }

        // Build 24h chart per usage metric
        const metrics = history[0]?.usage?.map(u => u.label) || [];
        const COLORS = ['var(--bar-fg)', '#f59e0b', '#a78bfa', '#34d399', '#f87171'];

        // Chart title
        const title = document.createElement('div');
        title.style.cssText = 'font-size:11px;color:var(--fg-dim);margin-bottom:8px';
        title.textContent = `Last 24h — ${history.length} snapshot${history.length !== 1 ? 's' : ''}`;
        els.historyContainer.appendChild(title);

        metrics.forEach((label, mi) => {
            const color = COLORS[mi % COLORS.length];
            const section = document.createElement('div');
            section.style.cssText = 'margin-bottom:14px';

            // Label row
            const labelRow = document.createElement('div');
            labelRow.style.cssText = 'display:flex;justify-content:space-between;font-size:11px;margin-bottom:4px';
            const labelEl = document.createElement('span');
            labelEl.style.color = 'var(--fg-dim)';
            labelEl.textContent = label;
            const lastVal = document.createElement('span');
            lastVal.style.color = color;
            const latest = history[history.length - 1]?.usage?.[mi];
            lastVal.textContent = latest?.pct_text || '';
            labelRow.append(labelEl, lastVal);

            // Chart area
            const chartWrap = document.createElement('div');
            chartWrap.style.cssText = 'position:relative;height:50px;background:var(--bar-bg);border-radius:3px;overflow:hidden';

            // Build sparkline as SVG
            const W = 308, H = 50;
            const points = history.map((snap, i) => {
                const u = snap.usage?.[mi];
                const pct = u ? u.fill_pct : 0;
                const x = (i / Math.max(history.length - 1, 1)) * W;
                const y = H - pct * H;
                return `${x},${y}`;
            });

            const ns = 'http://www.w3.org/2000/svg';
            const svg = document.createElementNS(ns, 'svg');
            svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
            svg.setAttribute('width', '100%');
            svg.setAttribute('height', H);
            svg.style.display = 'block';

            // Fill area
            const fillPoints = `0,${H} ${points.join(' ')} ${W},${H}`;
            const fill = document.createElementNS(ns, 'polygon');
            fill.setAttribute('points', fillPoints);
            fill.setAttribute('fill', color);
            fill.setAttribute('opacity', '0.15');
            svg.appendChild(fill);

            // Line
            const line = document.createElementNS(ns, 'polyline');
            line.setAttribute('points', points.join(' '));
            line.setAttribute('fill', 'none');
            line.setAttribute('stroke', color);
            line.setAttribute('stroke-width', '1.5');
            line.setAttribute('stroke-linejoin', 'round');
            svg.appendChild(line);

            // 80% warning line
            const warnY = H - 0.8 * H;
            const warnLine = document.createElementNS(ns, 'line');
            warnLine.setAttribute('x1', 0); warnLine.setAttribute('y1', warnY);
            warnLine.setAttribute('x2', W); warnLine.setAttribute('y2', warnY);
            warnLine.setAttribute('stroke', 'var(--bar-fg-warn)');
            warnLine.setAttribute('stroke-width', '0.5');
            warnLine.setAttribute('stroke-dasharray', '3,3');
            svg.appendChild(warnLine);

            // Dots at each data point
            history.forEach((snap, i) => {
                const u = snap.usage?.[mi];
                if (!u) return;
                const x = (i / Math.max(history.length - 1, 1)) * W;
                const y = H - u.fill_pct * H;
                const warn = u.warn;
                const dot = document.createElementNS(ns, 'circle');
                dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', 2.5);
                dot.setAttribute('fill', warn ? 'var(--bar-fg-warn)' : color);
                svg.appendChild(dot);
            });

            chartWrap.appendChild(svg);
            section.append(labelRow, chartWrap);

            // Time axis labels
            const timeRow = document.createElement('div');
            timeRow.style.cssText = 'display:flex;justify-content:space-between;font-size:10px;color:var(--fg-dim);margin-top:2px';
            const oldest = new Date(history[0].ts);
            const newest = new Date(history[history.length - 1].ts);
            const fmtTime = d => d.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'});
            const midTs = new Date((oldest.getTime() + newest.getTime()) / 2);
            [oldest, midTs, newest].forEach(d => {
                const t = document.createElement('span');
                t.textContent = fmtTime(d);
                timeRow.appendChild(t);
            });
            section.appendChild(timeRow);

            els.historyContainer.appendChild(section);
        });

        // Recent snapshots table (last 6)
        const tableTitle = document.createElement('div');
        tableTitle.style.cssText = 'font-size:11px;color:var(--fg-dim);margin:10px 0 6px;border-top:1px solid var(--bar-bg);padding-top:10px';
        tableTitle.textContent = 'Recent snapshots';
        els.historyContainer.appendChild(tableTitle);

        for (const snap of [...history].reverse().slice(0, 6)) {
            const entry = document.createElement('div');
            entry.className = 'history-entry';

            const timeEl = document.createElement('div');
            timeEl.className = 'history-time';
            timeEl.textContent = new Date(snap.ts).toLocaleString();
            entry.appendChild(timeEl);

            const bars = document.createElement('div');
            bars.className = 'history-bars';
            for (const u of snap.usage) {
                const row = document.createElement('div');
                row.className = 'history-row';
                const lbl = document.createElement('span');
                lbl.className = 'history-row-label';
                lbl.textContent = u.label;
                const barWrap = document.createElement('div');
                barWrap.className = 'history-row-bar';
                const fillEl = document.createElement('div');
                fillEl.className = 'history-row-fill' + (u.warn ? ' warn' : '');
                fillEl.style.width = `${u.fill_pct * 100}%`;
                barWrap.appendChild(fillEl);
                const pctEl = document.createElement('span');
                pctEl.className = 'history-row-pct';
                pctEl.textContent = u.pct_text;
                row.append(lbl, barWrap, pctEl);
                bars.appendChild(row);
            }
            entry.appendChild(bars);
            els.historyContainer.appendChild(entry);
        }
    }).catch(() => {
        els.historyContainer.replaceChildren();
        const err = document.createElement('div');
        err.className = 'history-empty';
        err.textContent = 'Could not load history.';
        els.historyContainer.appendChild(err);
    });
}

// ─── Status ───────────────────────────────────────────────────────────────────

function updateStatus(status) {
    if (textTimerId) {
        clearInterval(textTimerId);
        textTimerId = null;
    }

    if (!status) {
        els.statusSection.classList.remove('visible');
        return;
    }

    els.statusSection.classList.add('visible');

    if (status.last_success_time !== undefined) {
        statusState = {
            lastSuccessTime: status.last_success_time,
            nextPollTime: status.next_poll_time,
            refreshing: status.refreshing,
            error: status.error,
        };
        els.statusSection.classList.toggle('error', !!status.error);
        tickStatusText();
        textTimerId = setInterval(tickStatusText, 1000);
    } else {
        statusState = {};
        els.statusText.textContent = status.text || '';
        els.statusSection.classList.toggle('error', !!status.is_error);
    }
}

function tickStatusText() {
    if (!statusState.lastSuccessTime) return;

    const now = Date.now() / 1000;
    const secondsAgo = Math.max(0, Math.floor(now - statusState.lastSuccessTime));
    const isStale = !!statusState.nextPollTime && (now > statusState.nextPollTime + 30);
    els.usageSection.classList.toggle('stale', isStale);
    els.extraSection.classList.toggle('stale', isStale);

    const parts = [formatDuration(secondsAgo)];

    if (statusState.refreshing) {
        parts.push(translations.status_refreshing);
    } else if (statusState.error) {
        parts.push(statusState.error);
    } else if (secondsAgo >= 60 && statusState.nextPollTime) {
        const secondsUntil = Math.max(0, Math.floor(statusState.nextPollTime - now));
        if (secondsUntil > 0) {
            parts.push(translations.status_next_update.replace('{duration}', formatCountdown(secondsUntil)));
        }
    }

    els.statusText.textContent = parts.join(' \u00b7 ');
}

function formatDuration(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.status_updated_s.replace('{s}', totalSeconds);
    }

    const totalMin = Math.floor(totalSeconds / 60);
    const hours = Math.floor(totalMin / 60);
    const mins = totalMin % 60;

    let duration;
    if (hours > 0) {
        duration = translations.duration_hm.replace('{h}', hours).replace('{m}', mins);
    } else {
        duration = translations.duration_m.replace('{m}', totalMin);
    }
    return translations.status_updated.replace('{duration}', duration);
}

function formatCountdown(totalSeconds) {
    if (totalSeconds < 60) {
        return translations.duration_s.replace('{s}', totalSeconds);
    }

    const totalMin = Math.ceil(totalSeconds / 60);
    const hours = Math.floor(totalMin / 60);
    const mins = totalMin % 60;

    if (hours > 0) {
        return translations.duration_hm.replace('{h}', hours).replace('{m}', mins);
    }
    return translations.duration_m.replace('{m}', totalMin);
}

// ─── Prefs (server-backed via Python) ────────────────────────────────────────

function _savePrefToServer(key, value) {
    // Prefs are saved by individual API calls (set_always_on_top, set_anchor, etc.)
    // For display_mode and view we batch into a generic call if available,
    // otherwise just store in memory (Python reloads on next open anyway)
    try {
        if (window.pywebview?.api?.save_pref) {
            pywebview.api.save_pref(key, value);
        }
    } catch (_) {}
}

function _applyModeButtons() {
    document.querySelectorAll('.mode-btn[data-mode]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === currentMode);
    });
    document.querySelectorAll('.mode-btn[data-view]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === currentView);
    });
    // Also update theme buttons
    document.querySelectorAll('.mode-btn[data-theme]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === currentTheme);
    });
}

function _applyAnchorGrid() {
    document.querySelectorAll('.anchor-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.anchor === currentAnchor);
    });
    // Show drag handle only in float mode
    const dragHandle = document.getElementById('dragHandle');
    if (dragHandle) dragHandle.classList.toggle('hidden', currentAnchor !== 'float');
    // Update always-on-top note visibility
    const aotToggle = document.getElementById('aotToggle');
    if (aotToggle) {
        // AOT only meaningful when not auto-dismissing (non-tray anchor)
        const aotRow = aotToggle.closest('.settings-row');
        if (aotRow) aotRow.style.opacity = currentAnchor === 'tray' ? '0.4' : '1';
    }
}

// ─── Themes ──────────────────────────────────────────────────────────────────

// System themes (auto dark/light following Windows)
const SYSTEM_THEMES = {
    dark: {
        bg: '#1e1e1e', fg: '#cccccc', fg_dim: '#888888',
        fg_heading: '#ffffff', fg_link: '#4a9eff',
        bar_bg: '#333333', bar_fg: '#4a9eff',
        bar_fg_warn: '#e05050', bar_divider: '#000c',
        bar_marker: '#fffc',
    },
    light: {
        bg: '#f0f0f0', fg: '#1a1a1a', fg_dim: '#555555',
        fg_heading: '#000000', fg_link: '#0066cc',
        bar_bg: '#d0d0d0', bar_fg: '#0066cc',
        bar_fg_warn: '#cc2222', bar_divider: '#0003',
        bar_marker: '#0008',
    },
};

let systemTheme = 'dark';

function applySystemTheme(theme) {
    systemTheme = theme;
    // Always apply if in system mode; also apply on auto-change from Windows
    if (currentTheme === 'system') {
        const t = SYSTEM_THEMES[theme] || SYSTEM_THEMES.dark;
        const s = document.documentElement.style;
        document.body.style.transition = 'background 0.3s, color 0.3s';
        for (const [k, v] of Object.entries(t)) {
            s.setProperty(`--${k.replaceAll('_', '-')}`, v);
        }
        setTimeout(() => { document.body.style.transition = ''; }, 400);
    }
}

const THEMES = {
    default: {
        // ClaudeMeter brand theme — warm dark with Claude orange
        bg: '#1c1c1e', fg: '#cccccc', fg_dim: '#888888',
        fg_heading: '#ffffff', fg_link: '#d97757',
        bar_bg: '#2c2c2e', bar_fg: '#d97757',
        bar_fg_warn: '#e05050', bar_divider: '#000c',
        bar_marker: '#fffc',
    },
    traffic: {
        bg: '#1a1a1a', fg: '#cccccc', fg_dim: '#777777',
        fg_heading: '#ffffff', fg_link: '#4ade80',
        bar_bg: '#2a2a2a', bar_fg: '#4ade80',
        bar_fg_warn: '#ef4444', bar_divider: '#000c',
        bar_marker: '#fbbf24cc',
    },
    neon: {
        bg: '#0d0d1a', fg: '#c4c4e0', fg_dim: '#6666aa',
        fg_heading: '#e0e0ff', fg_link: '#00ffcc',
        bar_bg: '#1a1a2e', bar_fg: '#00ffcc',
        bar_fg_warn: '#ff4466', bar_divider: '#0008',
        bar_marker: '#a855f7cc',
    },
    system: null,  // placeholder — uses SYSTEM_THEMES dynamically
    minimal: {
        bg: '#111111', fg: '#aaaaaa', fg_dim: '#555555',
        fg_heading: '#dddddd', fg_link: '#888888',
        bar_bg: '#222222', bar_fg: '#888888',
        bar_fg_warn: '#cc4444', bar_divider: '#0008',
        bar_marker: '#ffffffaa',
    },
};

let currentTheme = 'default';

function _applyTheme(name) {
    if (name === 'system') {
        currentTheme = 'system';  // set BEFORE applySystemTheme checks it
        applySystemTheme(systemTheme);
        document.querySelectorAll('.mode-btn[data-theme]').forEach(b =>
            b.classList.toggle('active', b.dataset.theme === 'system'));
        _savePrefToServer('theme', 'system');
        window.pywebview?.api?.set_theme('system');
        return;
    }
    const theme = THEMES[name] || THEMES.default;
    const s = document.documentElement.style;
    for (const [key, value] of Object.entries(theme)) {
        s.setProperty(`--${key.replaceAll('_', '-')}`, value);
    }
    currentTheme = name;
    document.querySelectorAll('.mode-btn[data-theme]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === name);
    });
    // Persist
    _savePrefToServer('theme', name);
    // Also update via Python so it's applied next open
    window.pywebview?.api?.set_theme(name);
}

function _initThemeButtons() {
    document.querySelectorAll('.mode-btn[data-theme]').forEach(btn => {
        btn.addEventListener('click', () => _applyTheme(btn.dataset.theme));
    });
}

// ─── Yesterday summary ───────────────────────────────────────────────────────

function loadYesterdaySummary() {
    const container = document.getElementById('yesterdaySummary');
    if (!container || !window.pywebview?.api) return;

    pywebview.api.get_yesterday_summary().then(data => {
        if (!data || !Object.keys(data).length) return;

        container.classList.remove('hidden');
        container.replaceChildren();

        // Title row
        const title = document.createElement('div');
        title.className = 'yesterday-title';
        const resets = parseInt(data.resets || 0);
        title.textContent = `Yesterday${resets > 0 ? ` · ${resets} reset${resets > 1 ? 's' : ''}` : ''}`;
        container.appendChild(title);

        // Build chips from peak/avg pairs
        // Keys look like "Session (5hr) Peak%", "Session (5hr) Avg%"
        const metrics = {};
        for (const [key, val] of Object.entries(data)) {
            if (key === 'date' || key === 'resets') continue;
            const isPeak = key.endsWith('Peak%');
            const isAvg  = key.endsWith('Avg%');
            if (!isPeak && !isAvg) continue;
            const label = key.replace(' Peak%', '').replace(' Avg%', '');
            if (!metrics[label]) metrics[label] = {};
            if (isPeak) metrics[label].peak = val;
            if (isAvg)  metrics[label].avg  = val;
        }

        for (const [label, vals] of Object.entries(metrics)) {
            const chip = document.createElement('div');
            chip.className = 'yesterday-chip';

            const lbl = document.createElement('div');
            lbl.className = 'yesterday-chip-label';
            // Shorten label for display
            lbl.textContent = label.replace('Weekly (7 day)', 'Weekly').replace('Session (5hr)', 'Session');

            const values = document.createElement('div');
            values.className = 'yesterday-chip-values';

            const peak = document.createElement('span');
            peak.className = 'yesterday-chip-peak';
            const peakPct = parseFloat(vals.peak || 0);
            peak.textContent = vals.peak || '0%';
            if (peakPct >= 80) peak.style.color = 'var(--bar-fg-warn)';
            else if (peakPct >= 60) peak.style.color = '#f59e0b';

            const avg = document.createElement('span');
            avg.className = 'yesterday-chip-avg';
            avg.textContent = `avg ${vals.avg || '0%'}`;

            values.append(peak, avg);
            chip.append(lbl, values);
            container.appendChild(chip);
        }
    }).catch(() => {});
}

// ─── Compact mode ────────────────────────────────────────────────────────────

const COMPACT_KEYS = ['five_hour', 'seven_day'];  // session + weekly 7day

function _applyCompactMode() {
    const btn = document.getElementById('minimiseBtn');
    if (btn) btn.title = compactMode ? 'Full view' : 'Compact view';
    if (btn) btn.innerHTML = compactMode ? '&#9723;' : '&#8212;';

    // Sections to hide in compact mode
    const hideable = [
        els.modeSelector, els.accountSection, els.extraSection,
        els.usageSection, els.dialsSection, els.ledSection, els.historySection,
    ];

    hideable.forEach(el => { if (el) el.style.display = compactMode ? 'none' : ''; });
    // Also hide the settings gear in compact
    const gear = document.getElementById('viewToggle');
    if (gear) gear.style.display = compactMode ? 'none' : '';

    if (els.compactSection) {
        els.compactSection.classList.toggle('visible', compactMode);
        if (compactMode && lastUsageData) renderCompact(lastUsageData);
    }

    // Install section: always show in compact (CLI version)
    if (els.installSection) {
        const isHistory = currentView === 'history';
        els.installSection.classList.toggle('visible', !isHistory && !!els._installsVisible);
    }
}

function renderCompact(entries) {
    if (!els.compactBars) return;
    // Show only session (5hr) and weekly (7day) entries
    const shown = entries.filter(e =>
        e.label.toLowerCase().includes('session') ||
        e.label.toLowerCase().includes('weekly (7')
    );
    // Fall back to first two if label matching fails
    const display = shown.length >= 2 ? shown : entries.slice(0, 2);

    els.compactBars.replaceChildren(...display.map(entry => {
        const div = document.createElement('div');
        div.className = 'usage-entry';

        const header = document.createElement('div');
        header.className = 'bar-header';
        const label = document.createElement('span');
        label.textContent = entry.label;
        const pct = document.createElement('span');
        pct.className = 'bar-pct';
        pct.style.color = entry.warn ? 'var(--bar-fg-warn)' : '';
        pct.textContent = entry.pct_text;
        header.append(label, pct);

        const container = document.createElement('div');
        container.className = 'bar-container';
        const fill = document.createElement('div');
        fill.className = 'bar-fill' + (entry.warn ? ' warn' : '');
        fill.style.width = `${entry.fill_pct * 100}%`;
        container.appendChild(fill);

        if (entry.marker_rel !== null) {
            const marker = document.createElement('div');
            marker.className = 'bar-marker';
            marker.style.left = `calc(${entry.marker_rel * 100}% - 1px)`;
            container.appendChild(marker);
        }

        div.append(header, container);

        if (entry.reset_text) {
            const reset = document.createElement('div');
            reset.className = 'reset-text';
            reset.textContent = entry.reset_text;
            div.appendChild(reset);
        }

        return div;
    }));
}

// ─── History toolbar ─────────────────────────────────────────────────────────

function _initHistoryToolbar() {
    // Preset buttons
    document.querySelectorAll('.hist-preset').forEach(btn => {
        btn.addEventListener('click', () => {
            historyRange = btn.dataset.range;
            document.querySelectorAll('.hist-preset').forEach(b =>
                b.classList.toggle('active', b.dataset.range === historyRange));
            // Clear custom dates when preset selected
            if (historyRange !== 'custom') {
                const from = document.getElementById('histFrom');
                const to   = document.getElementById('histTo');
                if (from) from.value = '';
                if (to)   to.value   = '';
            }
            if (currentView === 'history') renderHistory();
        });
    });

    // Custom date inputs
    const fromEl = document.getElementById('histFrom');
    const toEl   = document.getElementById('histTo');

    // Set default "to" date to today
    if (toEl) toEl.value = _todayStr();

    [fromEl, toEl].forEach(el => {
        if (!el) return;
        el.addEventListener('change', () => {
            if (fromEl?.value || toEl?.value) {
                historyRange = 'custom';
                document.querySelectorAll('.hist-preset').forEach(b =>
                    b.classList.remove('active'));
                if (currentView === 'history') renderHistory();
            }
        });
    });

    // Export button
    const exportBtn = document.getElementById('exportCsvBtn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            const range = _getExportRange();
            exportBtn.textContent = 'Exporting…';
            exportBtn.disabled = true;
            pywebview.api.export_history_csv(range.from, range.to).then(result => {
                exportBtn.textContent = result.ok ? '✓ Saved' : '✗ Error';
                setTimeout(() => {
                    exportBtn.textContent = '⬇ CSV';
                    exportBtn.disabled = false;
                }, 2500);
                if (result.path) {
                    // Open Explorer with file selected
                    pywebview.api.open_export_file(result.path);
                }
            }).catch(() => {
                exportBtn.textContent = '✗ Error';
                setTimeout(() => {
                    exportBtn.textContent = '⬇ CSV';
                    exportBtn.disabled = false;
                }, 2500);
            });
        });
    }
}

function _todayStr() {
    const d = new Date();
    return d.toISOString().split('T')[0];
}

function _getExportRange() {
    const now   = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

    if (historyRange === 'custom') {
        const fromEl = document.getElementById('histFrom');
        const toEl   = document.getElementById('histTo');
        return {
            from: fromEl?.value || null,
            to:   toEl?.value   || null,
        };
    }

    if (historyRange === 'all') return { from: null, to: null };

    const days = historyRange === '7d' ? 7 : historyRange === '30d' ? 30 : 1;
    const fromDate = new Date(today);
    fromDate.setDate(fromDate.getDate() - (days - 1));
    return {
        from: fromDate.toISOString().split('T')[0],
        to:   today.toISOString().split('T')[0],
    };
}

function _getHistoryCutoff() {
    if (historyRange === 'all') return 0;
    if (historyRange === 'custom') {
        const fromEl = document.getElementById('histFrom');
        if (fromEl?.value) return new Date(fromEl.value).getTime();
        return 0;
    }
    const days = historyRange === '7d' ? 7 : historyRange === '30d' ? 30 : 1;
    return Date.now() - days * 86400 * 1000;
}

function _getHistoryCeiling() {
    if (historyRange === 'custom') {
        const toEl = document.getElementById('histTo');
        if (toEl?.value) {
            const d = new Date(toEl.value);
            d.setHours(23, 59, 59, 999);
            return d.getTime();
        }
    }
    return Date.now() + 86400000; // far future
}

// ─── RGB Picker ──────────────────────────────────────────────────────────────

function _initRgbPicker() {
    const toggleBtn = document.getElementById('rgbToggleBtn');
    const picker    = document.getElementById('rgbPicker');
    const applyBtn  = document.getElementById('rgbApplyBtn');
    const resetBtn  = document.getElementById('rgbResetBtn');
    if (!toggleBtn || !picker) return;

    toggleBtn.addEventListener('click', () => {
        picker.classList.toggle('hidden');
    });

    applyBtn.addEventListener('click', () => {
        const custom = {
            bg:          document.getElementById('rgb_bg').value,
            bar_fg:      document.getElementById('rgb_bar_fg').value,
            bar_fg_warn: document.getElementById('rgb_bar_fg_warn').value,
            fg:          document.getElementById('rgb_fg').value,
            fg_dim:      document.getElementById('rgb_fg_dim').value,
            // Derive related colours from main choices
            fg_heading:  '#ffffff',
            fg_link:     document.getElementById('rgb_bar_fg').value,
            bar_bg:      _darken(document.getElementById('rgb_bg').value, 0.5),
            bar_divider: '#000c',
            bar_marker:  '#fffc',
        };
        const s = document.documentElement.style;
        for (const [k, v] of Object.entries(custom)) {
            s.setProperty(`--${k.replaceAll('_','-')}`, v);
        }
        // Persist as 'custom' theme
        currentTheme = 'custom';
        document.querySelectorAll('.mode-btn[data-theme]').forEach(b =>
            b.classList.toggle('active', b.dataset.theme === 'custom'));
        window.pywebview?.api?.set_custom_theme(custom);
    });

    resetBtn.addEventListener('click', () => {
        _applyTheme('default');
        picker.classList.add('hidden');
    });
}

function _darken(hex, factor) {
    const r = parseInt(hex.slice(1,3),16);
    const g = parseInt(hex.slice(3,5),16);
    const b = parseInt(hex.slice(5,7),16);
    const d = v => Math.round(v * factor).toString(16).padStart(2,'0');
    return `#${d(r)}${d(g)}${d(b)}`;
}

// ─── Drag ────────────────────────────────────────────────────────────────────

function _initDrag() {
    // Drag the header to reposition the window.
    // Works in all anchor modes — uses set_force_open(true) during drag
    // to suppress the tray-mode dismiss-on-focus-loss watcher.
    const header = document.querySelector('header');
    if (!header) return;

    let dragging = false;
    let startX = 0, startY = 0;

    header.style.cursor = 'grab';

    header.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        if (e.target.tagName === 'BUTTON') return;

        dragging = true;
        startX = e.screenX;
        startY = e.screenY;
        header.style.cursor = 'grabbing';
        e.preventDefault();

        // Suppress dismiss-watcher so tray mode doesn't close on mousedown
        window.pywebview?.api?.set_force_open(true);
    });

    document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const dx = e.screenX - startX;
        const dy = e.screenY - startY;
        startX = e.screenX;
        startY = e.screenY;
        window.pywebview?.api?.move_window(dx, dy);
    });

    document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        header.style.cursor = 'grab';
        window.pywebview?.api?.save_window_position();
        // Release force-open — restore normal dismiss behaviour
        // Small delay so the window doesn't immediately close after drop
        setTimeout(() => {
            window.pywebview?.api?.set_force_open(false);
        }, 300);
    });
}

// ─── Height reporting ─────────────────────────────────────────────────────────

new ResizeObserver(() => {
    const height = document.body.scrollHeight;
    if (window.pywebview?.api?.report_height) {
        pywebview.api.report_height(height);
    }
}).observe(document.body);
