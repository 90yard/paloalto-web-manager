// Global connection state (kept in memory, or could use sessionStorage)
let currentConfig = null;

// DOM Elements
const navBtns = document.querySelectorAll('.nav-btn');
const tabContents = document.querySelectorAll('.tab-content');
const loader = document.getElementById('loader');
const authStatus = document.getElementById('authStatus');

// -----------------------------------------
// Navigation Logic
// -----------------------------------------
navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        // Enforce connection before accessing other tabs 
        const targetId = btn.getAttribute('data-target');
        if (targetId !== 'tab-connect' && !currentConfig) {
            showAlert('connectAlert', '방화벽에 먼저 연결해야 합니다.', 'error');
            switchTab('tab-connect');
            return;
        }

        switchTab(targetId);
    });
});

function switchTab(targetId) {
    navBtns.forEach(b => b.classList.remove('active'));
    tabContents.forEach(t => {
        t.classList.remove('active');
        t.classList.add('hidden');
    });

    // Update active UI
    const activeBtn = document.querySelector(`[data-target="${targetId}"]`);
    if (activeBtn) activeBtn.classList.add('active');

    const targetEl = document.getElementById(targetId);
    if (targetEl) {
        targetEl.classList.remove('hidden');
        targetEl.classList.add('active');
    }

    // Auto-fetch data if switching to specific tabs
    if (targetId === 'tab-address' && currentConfig) loadAddresses();
    if (targetId === 'tab-group' && currentConfig) loadGroups();
}

// -----------------------------------------
// Utility: API Calling & Loaders
// -----------------------------------------
async function apiPost(url, body) {
    showLoader();
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await response.json();
        hideLoader();

        if (!response.ok) {
            throw new Error(data.detail || 'Unknown server error');
        }
        return data;
    } catch (err) {
        hideLoader();
        throw err;
    }
}

function showLoader() { loader.classList.remove('hidden'); }
function hideLoader() { loader.classList.add('hidden'); }

function showAlert(elementId, msg, type = 'info') {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = msg;
    el.className = `alert alert-${type}`;
    el.classList.remove('hidden');
    setTimeout(() => { el.classList.add('hidden'); }, 5000);
}

function updateAuthStatus(isConnected) {
    if (isConnected) {
        authStatus.textContent = "연결됨";
        authStatus.className = "status-badge connected";
    } else {
        authStatus.textContent = "연결 끊김";
        authStatus.className = "status-badge disconnected";
    }
}

// -----------------------------------------
// Tab 1: Connect
// -----------------------------------------
document.getElementById('connectForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const host = document.getElementById('host').value.trim();
    const user = document.getElementById('username').value.trim();
    const pass = document.getElementById('password').value.trim();
    const key = document.getElementById('api_key').value.trim();

    const config = { host, username: user || null, password: pass || null, api_key: key || null };

    try {
        await apiPost('/api/connect', config);
        showAlert('connectAlert', '성공적으로 인증 및 연결되었습니다!', 'success');
        currentConfig = config; // Save config for subsequent calls
        updateAuthStatus(true);
        setTimeout(() => switchTab('tab-address'), 1000);
    } catch (err) {
        showAlert('connectAlert', err.message, 'error');
        updateAuthStatus(false);
        currentConfig = null;
    }
});

// Address Pagination & Search State
let allAddresses = [];
let filteredAddresses = [];
let pendingAddrs = new Set(JSON.parse(sessionStorage.getItem('pendingAddrs') || '[]'));

function savePendingAddrs() {
    sessionStorage.setItem('pendingAddrs', JSON.stringify([...pendingAddrs]));
}
let currentAddrPage = 1;
const ADDR_PER_PAGE = 20;

document.getElementById('btnRefreshAddr').addEventListener('click', loadAddresses);

async function loadAddresses() {
    if (!currentConfig) return;
    const tbody = document.querySelector('#addressTable tbody');
    try {
        const res = await apiPost('/api/address/list', currentConfig);
        allAddresses = res.data || [];

        // Reset search and page state
        document.getElementById('addressSearch').value = '';
        renderAddresses(true);
    } catch (err) {
        console.error(err);
        tbody.innerHTML = `<tr><td colspan="4" class="text-center empty-state" style="color:red">불러오기 실패: ${err.message}</td></tr>`;
    }
}

function renderAddresses(reset = true) {
    const tbody = document.querySelector('#addressTable tbody');
    const loadMoreBtn = document.getElementById('btnLoadMoreAddr');

    if (reset) {
        currentAddrPage = 1;
        const searchTerm = document.getElementById('addressSearch').value.toLowerCase();

        if (searchTerm) {
            filteredAddresses = allAddresses.filter(item => {
                const name = (item[0] || '').toLowerCase();
                const value = (item[1] || '').toLowerCase();
                return name.includes(searchTerm) || value.includes(searchTerm);
            });
        } else {
            filteredAddresses = [...allAddresses];
        }
    }

    if (filteredAddresses.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center empty-state">검색된 객체가 없습니다.</td></tr>`;
        if (loadMoreBtn) loadMoreBtn.classList.add('hidden');
        return;
    }

    const startIndex = (currentAddrPage - 1) * ADDR_PER_PAGE;
    const endIndex = Math.min(startIndex + ADDR_PER_PAGE, filteredAddresses.length);
    const visibleItems = filteredAddresses.slice(startIndex, endIndex);

    let html = '';
    visibleItems.forEach(item => {
        const isPending = pendingAddrs.has(item[0]);
        const pendingBadge = isPending ? ` <span class="status-badge pending">커밋 대기</span>` : '';

        html += `<tr${isPending ? ' class="pending-row"' : ''}>
            <td><strong>${item[0]}</strong>${pendingBadge}</td>
            <td><span style="font-family: monospace;">${item[1]}</span></td>
            <td><span class="status-badge connected" style="background:rgba(59,130,246,0.2);color:#60a5fa">${item[2]}</span></td>
            <td style="color:#94a3b8">${item[3]}</td>
        </tr>`;
    });

    tbody.innerHTML = html;

    const paginationControls = document.getElementById('paginationControls');
    const pageNumDisplay = document.getElementById('pageNumDisplay');
    const btnPrevPage = document.getElementById('btnPrevPageAddr');
    const btnNextPage = document.getElementById('btnNextPageAddr');

    if (paginationControls) {
        paginationControls.classList.remove('hidden');
        if (pageNumDisplay) pageNumDisplay.textContent = `${currentAddrPage} / ${Math.max(1, Math.ceil(filteredAddresses.length / ADDR_PER_PAGE))}`;

        if (btnPrevPage) {
            btnPrevPage.disabled = currentAddrPage <= 1;
            btnPrevPage.style.opacity = currentAddrPage <= 1 ? "0.5" : "1";
        }
        if (btnNextPage) {
            const totalPages = Math.ceil(filteredAddresses.length / ADDR_PER_PAGE);
            btnNextPage.disabled = currentAddrPage >= totalPages;
            btnNextPage.style.opacity = currentAddrPage >= totalPages ? "0.5" : "1";
        }
    }
}

document.getElementById('addressSearch')?.addEventListener('input', () => {
    renderAddresses(true);
});

document.getElementById('btnPrevPageAddr')?.addEventListener('click', () => {
    if (currentAddrPage > 1) {
        currentAddrPage--;
        renderAddresses(false);
    }
});

document.getElementById('btnNextPageAddr')?.addEventListener('click', () => {
    const totalPages = Math.ceil(filteredAddresses.length / ADDR_PER_PAGE);
    if (currentAddrPage < totalPages) {
        currentAddrPage++;
        renderAddresses(false);
    }
});



// -----------------------------------------
// Tab 3: Address Groups
// -----------------------------------------
// Group Pagination & Search State
let allGroups = [];
let filteredGroups = [];
let currentGroupPage = 1;
const GROUP_PER_PAGE = 20;

document.getElementById('btnRefreshGroups').addEventListener('click', loadGroups);

async function loadGroups() {
    if (!currentConfig) return;
    const tbody = document.querySelector('#groupTable tbody');
    try {
        const res = await apiPost('/api/group/list', currentConfig);
        allGroups = res.data || [];

        // Reset search and page state
        document.getElementById('groupSearch').value = '';
        renderGroups(true);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-center empty-state" style="color:red">불러오기 실패: ${err.message}</td></tr>`;
    }
}

function renderGroups(resetPage = false) {
    const tbody = document.querySelector('#groupTable tbody');
    const paginationControls = document.getElementById('paginationControlsGroup');
    const pageNumDisplay = document.getElementById('pageNumDisplayGroup');
    const btnPrevPage = document.getElementById('btnPrevPageGroup');
    const btnNextPage = document.getElementById('btnNextPageGroup');

    if (resetPage) {
        currentGroupPage = 1;
        const searchTerm = document.getElementById('groupSearch').value.toLowerCase();

        if (searchTerm) {
            filteredGroups = allGroups.filter(item => {
                const name = (item[0] || '').toLowerCase();
                const members = (item[2] || '').toLowerCase();
                return name.includes(searchTerm) || members.includes(searchTerm);
            });
        } else {
            filteredGroups = [...allGroups];
        }
    }

    if (filteredGroups.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="text-center empty-state">검색된 그룹이 없습니다.</td></tr>`;
        if (paginationControls) paginationControls.classList.add('hidden');
        return;
    }

    const totalPages = Math.ceil(filteredGroups.length / GROUP_PER_PAGE);
    if (currentGroupPage > totalPages) {
        currentGroupPage = totalPages;
    }

    const startIndex = (currentGroupPage - 1) * GROUP_PER_PAGE;
    const endIndex = Math.min(startIndex + GROUP_PER_PAGE, filteredGroups.length);
    const visibleItems = filteredGroups.slice(startIndex, endIndex);

    let html = '';
    visibleItems.forEach(item => {
        html += `<tr>
            <td><strong>${item[0]}</strong></td>
            <td><span class="status-badge connected" style="background:rgba(139,92,246,0.2);color:#a78bfa">${item[1]}</span></td>
            <td><span style="color:#cbd5e1">${item[2]}</span></td>
        </tr>`;
    });

    tbody.innerHTML = html;

    // Update Pagination UI
    if (paginationControls) {
        paginationControls.classList.remove('hidden');
        if (pageNumDisplay) pageNumDisplay.textContent = `${currentGroupPage} / ${Math.max(1, Math.ceil(filteredGroups.length / GROUP_PER_PAGE))}`;

        if (btnPrevPage) {
            btnPrevPage.disabled = currentGroupPage <= 1;
            btnPrevPage.style.opacity = currentGroupPage <= 1 ? "0.5" : "1";
        }
        if (btnNextPage) {
            btnNextPage.disabled = currentGroupPage >= totalPages;
            btnNextPage.style.opacity = currentGroupPage >= totalPages ? "0.5" : "1";
        }
    }
}

document.getElementById('groupSearch')?.addEventListener('input', () => {
    renderGroups(true);
});

document.getElementById('btnPrevPageGroup')?.addEventListener('click', () => {
    if (currentGroupPage > 1) {
        currentGroupPage--;
        renderGroups(false);
    }
});

document.getElementById('btnNextPageGroup')?.addEventListener('click', () => {
    const totalPages = Math.ceil(filteredGroups.length / GROUP_PER_PAGE);
    if (currentGroupPage < totalPages) {
        currentGroupPage++;
        renderGroups(false);
    }
});


// -----------------------------------------
// Single Address Add
// -----------------------------------------

document.getElementById('addAddrForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!currentConfig) return;

    const name = document.getElementById('addrName').value.trim();
    const value = document.getElementById('addrValue').value.trim();
    const type = document.getElementById('addrType').value;
    const description = document.getElementById('addrDesc').value.trim();
    const resultEl = document.getElementById('addAddrResult');

    try {
        const res = await apiPost('/api/address/add', { ...currentConfig, name, value, type, description });
        resultEl.textContent = res.message || `'${name}' 추가 완료`;
        resultEl.className = 'alert alert-success';
        resultEl.classList.remove('hidden');

        // Mark as pending and refresh
        pendingAddrs.add(name);
        savePendingAddrs();
        document.getElementById('addAddrForm').reset();
        await loadAddresses();
    } catch (err) {
        resultEl.textContent = `오류: ${err.message}`;
        resultEl.className = 'alert alert-error';
        resultEl.classList.remove('hidden');
    }
});

// -----------------------------------------
// Bulk Address Upload (CSV)
// -----------------------------------------

document.getElementById('bulkFile')?.addEventListener('change', (e) => {
    const file = e.target.files[0];
    const nameEl = document.getElementById('bulkFileName');
    if (file) {
        nameEl.textContent = file.name;
        nameEl.style.color = 'var(--text-primary)';
        nameEl.style.fontStyle = 'normal';
    } else {
        nameEl.textContent = '선택된 파일 없음';
        nameEl.style.color = 'var(--text-secondary)';
        nameEl.style.fontStyle = 'italic';
    }
});

document.getElementById('btnBulkUpload')?.addEventListener('click', async () => {
    if (!currentConfig) return;
    const fileInput = document.getElementById('bulkFile');
    const file = fileInput.files[0];
    if (!file) {
        alert('CSV 파일을 선택해 주세요.');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('host', currentConfig.host);
    if (currentConfig.username) formData.append('username', currentConfig.username);
    if (currentConfig.password) formData.append('password', currentConfig.password);
    if (currentConfig.api_key) formData.append('api_key', currentConfig.api_key);

    showLoader();
    const resultEl = document.getElementById('bulkResult');
    try {
        const response = await fetch('/api/address/bulk', { method: 'POST', body: formData });
        const data = await response.json();
        hideLoader();
        if (!response.ok) throw new Error(data.detail || 'Unknown error');

        resultEl.textContent = data.message;
        resultEl.className = 'alert alert-success mt-4';
        resultEl.classList.remove('hidden');

        if (data.created > 0) {
            // Mark newly created as pending and refresh table
            if (data.skipped_names) {
                // skipped_names are skipped; non-skipped = created — we don't have their names here, so just refresh
            }
            await loadAddresses();
        }
    } catch (err) {
        hideLoader();
        resultEl.textContent = `오류: ${err.message}`;
        resultEl.className = 'alert alert-error mt-4';
        resultEl.classList.remove('hidden');
    }
});

// -----------------------------------------
// Tab 5: Commit (Actually part of sidebar/header)
// -----------------------------------------
document.getElementById('btnCommit').addEventListener('click', async () => {
    if (!currentConfig) return;

    // Add user confirmation to prevent accidental commit
    if (!confirm("정말로 방화벽에 설정을 Commit 하시겠습니까?")) return;

    const partial = document.getElementById('partialCommit').checked;

    try {
        const res = await apiPost('/api/commit', { ...currentConfig, partial });
        showAlert('commitOutput', res.message || '설정 적용(Commit)이 완료되었습니다.', 'success');
        // Clear pending items on successful commit
        pendingAddrs.clear();
        savePendingAddrs();
        loadAddresses(); // Refresh UI to remove badges
    } catch (err) {
        showAlert('commitOutput', `Commit 실패: ${err.message}`, 'error');
    }
});
