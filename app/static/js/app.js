/**
 * FreeRADIUS Web Manager - Enhanced JavaScript
 * Features: Theme toggle, toast notifications, sidebar, SSE, global search
 */

// ============================================
// Theme Management
// ============================================
const ThemeManager = {
    STORAGE_KEY: 'radius-theme',

    init() {
        const saved = localStorage.getItem(this.STORAGE_KEY);
        if (saved) {
            document.documentElement.setAttribute('data-theme', saved);
        } else if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.documentElement.setAttribute('data-theme', 'dark');
        }

        const toggle = document.getElementById('themeToggle');
        if (toggle) {
            toggle.addEventListener('click', () => this.toggle());
        }

        // Listen for system theme changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (!localStorage.getItem(this.STORAGE_KEY)) {
                document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light');
            }
        });
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem(this.STORAGE_KEY, next);
    },

    get() {
        return document.documentElement.getAttribute('data-theme') || 'light';
    }
};

// ============================================
// Sidebar Management
// ============================================
const SidebarManager = {
    STORAGE_KEY: 'radius-sidebar-collapsed',

    init() {
        const sidebar = document.getElementById('sidebar');
        const toggle = document.getElementById('sidebarToggle');
        const menuBtn = document.getElementById('menuBtn');
        const overlay = document.getElementById('sidebarOverlay');

        if (!sidebar) return;

        // Restore collapsed state (desktop only)
        const isCollapsed = localStorage.getItem(this.STORAGE_KEY) === 'true';
        if (isCollapsed && window.innerWidth > 1024) {
            sidebar.classList.add('sidebar--collapsed');
        }

        // Toggle button (desktop)
        if (toggle) {
            toggle.addEventListener('click', () => this.toggleCollapse());
        }

        // Menu button (mobile)
        if (menuBtn) {
            menuBtn.addEventListener('click', () => this.openMobile());
        }

        // Overlay click (mobile)
        if (overlay) {
            overlay.addEventListener('click', () => this.closeMobile());
        }

        // Close on escape
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeMobile();
            }
        });

        // Handle resize
        window.addEventListener('resize', () => {
            if (window.innerWidth > 1024) {
                this.closeMobile();
            }
        });
    },

    toggleCollapse() {
        const sidebar = document.getElementById('sidebar');
        if (!sidebar) return;

        sidebar.classList.toggle('sidebar--collapsed');
        const isCollapsed = sidebar.classList.contains('sidebar--collapsed');
        localStorage.setItem(this.STORAGE_KEY, isCollapsed);
    },

    openMobile() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');

        if (sidebar) sidebar.classList.add('sidebar--open');
        if (overlay) overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    },

    closeMobile() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');

        if (sidebar) sidebar.classList.remove('sidebar--open');
        if (overlay) overlay.classList.remove('active');
        document.body.style.overflow = '';
    }
};

// ============================================
// Toast Notifications
// ============================================
const Toast = {
    container: null,

    init() {
        this.container = document.getElementById('toastContainer');
    },

    show(message, type = 'info', duration = 5000) {
        if (!this.container) this.init();
        if (!this.container) return;

        const toast = document.createElement('div');
        toast.className = `toast toast--${type}`;

        const icons = {
            success: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
            error: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            warning: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
        };

        toast.innerHTML = `
            <span class="toast__icon" style="color: var(--${type === 'error' ? 'danger' : type})">${icons[type] || icons.info}</span>
            <div class="toast__content">
                <span class="toast__message">${message}</span>
            </div>
            <button class="toast__close" aria-label="Close">&times;</button>
        `;

        const closeBtn = toast.querySelector('.toast__close');
        closeBtn.addEventListener('click', () => this.remove(toast));

        this.container.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => this.remove(toast), duration);
        }

        return toast;
    },

    remove(toast) {
        toast.style.animation = 'slideIn 0.3s ease reverse';
        setTimeout(() => toast.remove(), 300);
    },

    success(message, duration) {
        return this.show(message, 'success', duration);
    },

    error(message, duration) {
        return this.show(message, 'error', duration);
    },

    warning(message, duration) {
        return this.show(message, 'warning', duration);
    },

    info(message, duration) {
        return this.show(message, 'info', duration);
    }
};

// ============================================
// Server Status
// ============================================
const ServerStatus = {
    element: null,
    interval: null,

    init() {
        this.element = document.getElementById('serverStatusHeader');
        if (this.element) {
            this.check();
            this.interval = setInterval(() => this.check(), 30000);
        }
    },

    async check() {
        if (!this.element) return;

        try {
            const response = await fetch('/api/status');
            const data = await response.json();

            const dot = this.element.querySelector('.status-dot');
            const text = this.element.querySelector('.status-text');

            if (data.running) {
                dot.className = 'status-dot status-dot--online';
                text.textContent = 'Online';
            } else {
                dot.className = 'status-dot status-dot--offline';
                text.textContent = data.status || 'Offline';
            }
        } catch (err) {
            const dot = this.element.querySelector('.status-dot');
            const text = this.element.querySelector('.status-text');
            dot.className = 'status-dot status-dot--offline';
            text.textContent = 'Unknown';
        }
    }
};

// ============================================
// Server-Sent Events (Live Updates)
// ============================================
const LiveUpdates = {
    eventSource: null,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    reconnectDelay: 5000,
    handlers: {},

    init() {
        // Only connect on pages that need live updates
        if (document.querySelector('[data-live-updates]')) {
            this.connect();
        }
    },

    connect() {
        if (this.eventSource) {
            this.eventSource.close();
        }

        try {
            this.eventSource = new EventSource('/api/events');

            this.eventSource.onopen = () => {
                console.log('SSE connected');
                this.reconnectAttempts = 0;
            };

            this.eventSource.onerror = (err) => {
                console.error('SSE error:', err);
                this.eventSource.close();
                this.scheduleReconnect();
            };

            // Session events
            this.eventSource.addEventListener('session_start', (e) => {
                const session = JSON.parse(e.data);
                this.trigger('session_start', session);
                Toast.success(`${session.username} connected`);
            });

            this.eventSource.addEventListener('session_stop', (e) => {
                const data = JSON.parse(e.data);
                this.trigger('session_stop', data);
                Toast.info(`Session ended`);
            });

            // Server status events
            this.eventSource.addEventListener('server_status', (e) => {
                const data = JSON.parse(e.data);
                this.trigger('server_status', data);
                ServerStatus.check();
            });

        } catch (err) {
            console.error('Failed to create EventSource:', err);
            this.scheduleReconnect();
        }
    },

    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

        setTimeout(() => this.connect(), delay);
    },

    on(event, handler) {
        if (!this.handlers[event]) {
            this.handlers[event] = [];
        }
        this.handlers[event].push(handler);
    },

    off(event, handler) {
        if (!this.handlers[event]) return;
        this.handlers[event] = this.handlers[event].filter(h => h !== handler);
    },

    trigger(event, data) {
        if (!this.handlers[event]) return;
        this.handlers[event].forEach(handler => handler(data));
    },

    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }
};

// ============================================
// Global Search
// ============================================
const GlobalSearch = {
    input: null,
    debounceTimer: null,

    init() {
        this.input = document.getElementById('globalSearch');
        if (!this.input) return;

        this.input.addEventListener('input', (e) => this.handleInput(e));
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
    },

    handleInput(e) {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = setTimeout(() => {
            const query = e.target.value.trim();
            if (query.length >= 2) {
                this.search(query);
            }
        }, 300);
    },

    handleKeydown(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const query = this.input.value.trim();
            if (query) {
                // Navigate to users page with search query
                window.location.href = `/users?search=${encodeURIComponent(query)}`;
            }
        }
    },

    async search(query) {
        // Future: implement search suggestions dropdown
        console.log('Searching:', query);
    }
};

// ============================================
// API Utilities
// ============================================
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };

    if (data) {
        options.body = JSON.stringify(data);
    }

    const response = await fetch(endpoint, options);
    const result = await response.json();

    if (!response.ok) {
        throw new Error(result.error || 'API request failed');
    }

    return result;
}

// ============================================
// Confirm Dialog
// ============================================
function confirmAction(message) {
    return confirm(message);
}

// ============================================
// Format Utilities
// ============================================
const Format = {
    bytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    duration(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hours > 0) {
            return `${hours}h ${minutes}m`;
        }
        if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        }
        return `${secs}s`;
    },

    relativeTime(date) {
        const now = new Date();
        const diff = now - new Date(date);
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days}d ago`;
        if (hours > 0) return `${hours}h ago`;
        if (minutes > 0) return `${minutes}m ago`;
        return 'Just now';
    }
};

// ============================================
// Table Sorting
// ============================================
const TableSort = {
    init() {
        document.querySelectorAll('[data-sortable]').forEach(table => {
            table.querySelectorAll('th[data-sort]').forEach(th => {
                th.style.cursor = 'pointer';
                th.addEventListener('click', () => this.sort(table, th));
            });
        });
    },

    sort(table, th) {
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const column = th.dataset.sort;
        const type = th.dataset.sortType || 'string';
        const currentDir = th.dataset.sortDir || 'asc';
        const newDir = currentDir === 'asc' ? 'desc' : 'asc';

        // Reset all headers
        table.querySelectorAll('th[data-sort]').forEach(h => {
            h.dataset.sortDir = '';
            h.classList.remove('sort-asc', 'sort-desc');
        });

        // Set current header
        th.dataset.sortDir = newDir;
        th.classList.add(`sort-${newDir}`);

        // Sort rows
        rows.sort((a, b) => {
            const aVal = a.querySelector(`[data-column="${column}"]`)?.textContent || '';
            const bVal = b.querySelector(`[data-column="${column}"]`)?.textContent || '';

            let comparison = 0;
            if (type === 'number') {
                comparison = parseFloat(aVal) - parseFloat(bVal);
            } else {
                comparison = aVal.localeCompare(bVal);
            }

            return newDir === 'asc' ? comparison : -comparison;
        });

        // Re-append sorted rows
        rows.forEach(row => tbody.appendChild(row));
    }
};

// ============================================
// Inline Editing
// ============================================
const InlineEdit = {
    init() {
        document.querySelectorAll('[data-inline-edit]').forEach(el => {
            el.addEventListener('dblclick', () => this.startEdit(el));
        });
    },

    startEdit(el) {
        const field = el.dataset.inlineEdit;
        const value = el.textContent;
        const endpoint = el.dataset.editEndpoint;

        const input = document.createElement('input');
        input.type = field === 'password' ? 'password' : 'text';
        input.value = field === 'password' ? '' : value;
        input.className = 'form-input';
        input.style.width = '100%';
        input.placeholder = field === 'password' ? 'Enter new password' : value;

        el.innerHTML = '';
        el.appendChild(input);
        input.focus();
        input.select();

        const save = async () => {
            const newValue = input.value.trim();
            if (newValue && newValue !== value) {
                try {
                    await apiCall(endpoint, 'PATCH', { [field]: newValue });
                    el.textContent = field === 'password' ? '********' : newValue;
                    Toast.success('Updated successfully');
                } catch (err) {
                    el.textContent = value;
                    Toast.error(err.message);
                }
            } else {
                el.textContent = value;
            }
        };

        input.addEventListener('blur', save);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                input.blur();
            } else if (e.key === 'Escape') {
                el.textContent = value;
            }
        });
    }
};

// ============================================
// Initialize on DOM Ready
// ============================================
document.addEventListener('DOMContentLoaded', () => {
    ThemeManager.init();
    SidebarManager.init();
    Toast.init();
    ServerStatus.init();
    GlobalSearch.init();
    LiveUpdates.init();
    TableSort.init();
    InlineEdit.init();
});

// ============================================
// Expose Global Functions
// ============================================
window.Toast = Toast;
window.apiCall = apiCall;
window.confirmAction = confirmAction;
window.Format = Format;
window.LiveUpdates = LiveUpdates;
