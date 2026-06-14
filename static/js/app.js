// STATE MANAGEMENT
let state = {
    users: [],
    currentUser: null,
    activeTab: 'dashboard',
    csvAnalysisRows: [],
    importFilename: ''
};

// INITIALIZATION
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

async function initApp() {
    setupTabListeners();
    setupDropzone();
    setupFormListeners();
    
    // Fetch users and initialize user selectors
    await fetchUsers();
    await checkCurrentUser();
    
    // Load initial views
    loadDashboard();
    loadExpenses();
}

// NAVIGATION TABS
function setupTabListeners() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', (e) => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            
            const targetTab = tab.getAttribute('data-tab');
            state.activeTab = targetTab;
            
            document.querySelectorAll('.tab-view').forEach(view => {
                view.classList.remove('active-view');
            });
            document.getElementById(`${targetTab}View`).classList.add('active-view');
            
            if (targetTab === 'dashboard') {
                loadDashboard();
            } else if (targetTab === 'audit') {
                loadAuditTrail();
            } else if (targetTab === 'transactions') {
                loadExpenses();
            }
        });
    });
}

// AUTH & USERS HANDLERS
async function fetchUsers() {
    try {
        const res = await fetch('/api/users');
        state.users = await res.json();
        
        // Populate selectors
        populateDropdown('userSelector', state.users);
        populateDropdown('expPayer', state.users);
        populateDropdown('paySender', state.users);
        populateDropdown('payReceiver', state.users);
        
        // Event listener for user switching
        document.getElementById('userSelector').addEventListener('change', async (e) => {
            const userId = e.target.value;
            await switchUser(userId);
        });
        
        renderSplitParticipants();
    } catch (e) {
        console.error("Failed to fetch users:", e);
    }
}

async function checkCurrentUser() {
    try {
        const res = await fetch('/api/auth/me');
        const data = await res.json();
        if (data.user) {
            state.currentUser = data.user;
            document.getElementById('userSelector').value = data.user.id;
        }
    } catch (e) {
        console.warn("No session active, auto-login default.");
    }
}

async function switchUser(userId) {
    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        const data = await res.json();
        state.currentUser = data.user;
        
        // Refresh views
        loadDashboard();
        if (state.activeTab === 'audit') {
            loadAuditTrail();
        }
    } catch (e) {
        console.error("Failed to switch user:", e);
    }
}

function populateDropdown(selectId, usersList) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = '';
    usersList.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.id;
        opt.textContent = u.name;
        select.appendChild(opt);
    });
}

// VIEW 1: DASHBOARD
async function loadDashboard() {
    try {
        const res = await fetch('/api/groups/1/balances');
        const data = await res.json();
        
        renderBalancesGrid(data.balances);
        renderSimplifiedDebts(data.simplified_debts);
    } catch (e) {
        console.error("Failed to load dashboard:", e);
    }
}

function renderBalancesGrid(balancesMap) {
    const grid = document.getElementById('balancesGrid');
    if (!grid) return;
    grid.innerHTML = '';
    
    // Sort users alphabetically
    const uids = Object.keys(balancesMap).sort((a, b) => {
        return balancesMap[a].name.localeCompare(balancesMap[b].name);
    });
    
    uids.forEach(uid => {
        const bal = balancesMap[uid];
        const isCurrentUser = state.currentUser && parseInt(uid) === state.currentUser.id;
        
        const card = document.createElement('div');
        card.className = `balance-card ${isCurrentUser ? 'active-user-card' : ''}`;
        
        const valClass = bal.net > 0.01 ? 'text-green' : (bal.net < -0.01 ? 'text-red' : '');
        const sign = bal.net > 0.01 ? '+' : '';
        
        // Find membership window details from state
        const userMeta = state.users.find(u => u.id === parseInt(uid));
        const statusText = userMeta && userMeta.left_date ? `Left ${formatDisplayDate(userMeta.left_date)}` : 'Active';
        const badgeClass = userMeta && userMeta.left_date ? 'badge-inactive' : 'badge-active';
        
        card.innerHTML = `
            <div class="card-user-name">
                <span>${bal.name} ${isCurrentUser ? ' <small>(You)</small>' : ''}</span>
                <span class="user-status-badge ${badgeClass}">${statusText}</span>
            </div>
            <div class="card-amount-block">
                <span class="amount-title">Net Balance</span>
                <span class="amount-value ${valClass}">${sign}₹${bal.net.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>
            <div class="card-details-row">
                <span>Paid: ₹${bal.paid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                <span>Owed: ₹${bal.owed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

// VIEW 2: AUDIT LOG (Rohan's View)
async function loadAuditTrail() {
    if (!state.currentUser) return;
    const userId = state.currentUser.id;
    
    try {
        const res = await fetch(`/api/users/${userId}/audit`);
        const audit = await res.json();
        
        // Update stats
        let totalPaid = 0.0;
        let totalOwed = 0.0;
        
        const tbody = document.getElementById('auditTableBody');
        tbody.innerHTML = '';
        
        audit.forEach(item => {
            totalPaid += item.user_paid;
            totalOwed += item.user_owed;
            
            const tr = document.createElement('tr');
            
            const impactClass = item.net_impact > 0.01 ? 'text-green' : (item.net_impact < -0.01 ? 'text-red' : '');
            const sign = item.net_impact > 0.01 ? '+' : '';
            
            const dateStr = formatDisplayDate(item.date);
            const totalCostStr = item.currency !== 'INR' ? 
                `$${item.original_amount} (${item.currency})` : 
                `₹${item.amount_inr.toFixed(2)}`;
                
            tr.innerHTML = `
                <td>${dateStr}</td>
                <td>
                    <strong>${item.description}</strong><br>
                    <small class="text-secondary">${item.split_desc || (item.notes || '')}</small>
                </td>
                <td>${item.payer_name}</td>
                <td>${totalCostStr}</td>
                <td>₹${item.user_owed.toFixed(2)}</td>
                <td>₹${item.user_paid.toFixed(2)}</td>
                <td class="${impactClass}"><strong>${sign}₹${item.net_impact.toFixed(2)}</strong></td>
            `;
            tbody.appendChild(tr);
        });
        
        const net = totalPaid - totalOwed;
        const netClass = net > 0.01 ? 'text-green' : (net < -0.01 ? 'text-red' : '');
        const signNet = net > 0.01 ? '+' : '';
        
        document.getElementById('auditPaid').textContent = `₹${totalPaid.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        document.getElementById('auditOwed').textContent = `₹${totalOwed.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        document.getElementById('auditNet').textContent = `${signNet}₹${net.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`;
        document.getElementById('auditNet').className = `stat-value ${netClass}`;
        
    } catch (e) {
        console.error("Failed to load audit trail:", e);
    }
}

// VIEW 3: AISHA'S SIMPLIFIED DEBTS
function renderSimplifiedDebts(debts) {
    const list = document.getElementById('debtsList');
    if (!list) return;
    list.innerHTML = '';
    
    if (debts.length === 0) {
        list.innerHTML = `
            <div class="no-debts-msg">
                <i class="fa-solid fa-circle-check" style="font-size: 3rem;"></i>
                <span>Everyone is fully settled up! No outstanding debts.</span>
            </div>
        `;
        return;
    }
    
    debts.forEach(debt => {
        const item = document.createElement('div');
        item.className = 'debt-item';
        
        item.innerHTML = `
            <span class="debt-sender"><i class="fa-solid fa-user-minus text-red"></i> ${debt.from_user_name}</span>
            <div class="debt-arrow">
                <span class="debt-amt-badge">₹${debt.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                <i class="fa-solid fa-long-arrow-right"></i>
            </div>
            <span class="debt-recipient"><i class="fa-solid fa-user-plus text-green"></i> ${debt.to_user_name}</span>
        `;
        list.appendChild(item);
    });
}

// VIEW 4: TRANSACTIONS & MANUAL FORM
function switchFormType(type) {
    document.querySelectorAll('.toggle-btn').forEach(btn => btn.classList.remove('active'));
    if (type === 'expense') {
        document.getElementById('btnToggleExpense').classList.add('active');
        document.getElementById('expenseForm').style.display = 'block';
        document.getElementById('paymentForm').style.display = 'none';
    } else {
        document.getElementById('btnTogglePayment').classList.add('active');
        document.getElementById('expenseForm').style.display = 'none';
        document.getElementById('paymentForm').style.display = 'block';
    }
}

function toggleExRateField() {
    const currency = document.getElementById('expCurrency').value;
    const rateGroup = document.getElementById('exRateGroup');
    if (currency === 'USD') {
        rateGroup.style.display = 'block';
    } else {
        rateGroup.style.display = 'none';
    }
}

function renderSplitParticipants() {
    const container = document.getElementById('participantsSplitList');
    if (!container) return;
    container.innerHTML = '';
    
    const splitType = document.getElementById('expSplitType').value;
    
    state.users.forEach(u => {
        // Only include active users on current form select date if date is filled, otherwise list all
        const label = document.createElement('label');
        label.className = 'participant-checkbox-item';
        
        // Hide details input unless percentage/share/unequal is selected
        let detailInputHTML = '';
        if (splitType === 'percentage') {
            detailInputHTML = `<input type="number" step="0.1" class="participant-details-input" placeholder="%" data-uid="${u.id}">`;
        } else if (splitType === 'share') {
            detailInputHTML = `<input type="number" step="1" value="1" class="participant-details-input" placeholder="shares" data-uid="${u.id}">`;
        } else if (splitType === 'unequal') {
            detailInputHTML = `<input type="number" step="0.01" class="participant-details-input" placeholder="₹" data-uid="${u.id}">`;
        }
        
        label.innerHTML = `
            <input type="checkbox" checked value="${u.id}">
            <span>${u.name}</span>
            ${detailInputHTML}
        `;
        container.appendChild(label);
    });
}

function setupFormListeners() {
    // Expense split type changed
    const splitTypeSelect = document.getElementById('expSplitType');
    if (splitTypeSelect) {
        splitTypeSelect.addEventListener('change', renderSplitParticipants);
    }
    
    // Expense submit
    document.getElementById('expenseForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const description = document.getElementById('expDesc').value;
        const amount = parseFloat(document.getElementById('expAmount').value);
        const currency = document.getElementById('expCurrency').value;
        const exchange_rate = currency === 'USD' ? parseFloat(document.getElementById('expExchangeRate').value) : 1.0;
        const paid_by_user_id = parseInt(document.getElementById('expPayer').value);
        const date = document.getElementById('expDate').value;
        const split_type = document.getElementById('expSplitType').value;
        const notes = document.getElementById('expNotes').value;
        
        // Collect checked participants
        const participantsCheckboxes = document.querySelectorAll('#participantsSplitList input[type="checkbox"]:checked');
        const split_with = Array.from(participantsCheckboxes).map(cb => parseInt(cb.value));
        
        if (split_with.length === 0) {
            alert("Please select at least one member to split the expense with.");
            return;
        }
        
        // Collect split details
        const split_details = {};
        if (split_type !== 'equal') {
            const detailInputs = document.querySelectorAll('#participantsSplitList .participant-details-input');
            detailInputs.forEach(input => {
                const uid = input.getAttribute('data-uid');
                if (split_with.includes(parseInt(uid))) {
                    split_details[uid] = parseFloat(input.value || 0.0);
                }
            });
        }
        
        const payload = {
            description, amount, currency, exchange_rate, paid_by_user_id, date, split_type, split_with, split_details, notes
        };
        
        try {
            const res = await fetch('/api/expenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                // Clear form
                document.getElementById('expenseForm').reset();
                renderSplitParticipants();
                switchFormType('expense');
                
                // Refresh data
                loadDashboard();
                loadExpenses();
            }
        } catch (err) {
            console.error("Failed to add manual expense:", err);
        }
    });
    
    // Settlement submit
    document.getElementById('paymentForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const sender_id = parseInt(document.getElementById('paySender').value);
        const receiver_id = parseInt(document.getElementById('payReceiver').value);
        const amount = parseFloat(document.getElementById('payAmount').value);
        const date = document.getElementById('payDate').value;
        const notes = document.getElementById('payNotes').value;
        
        if (sender_id === receiver_id) {
            alert("Sender and receiver must be different people.");
            return;
        }
        
        const payload = { sender_id, receiver_id, amount, date, notes };
        
        try {
            const res = await fetch('/api/payments', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (data.error) {
                alert(data.error);
            } else {
                document.getElementById('paymentForm').reset();
                loadDashboard();
                loadExpenses();
            }
        } catch (err) {
            console.error("Failed to add payment:", err);
        }
    });
}

async function loadExpenses() {
    const list = document.getElementById('ledgerList');
    if (!list) return;
    list.innerHTML = '';
    
    try {
        // Fetch expenses
        const expRes = await fetch('/api/expenses');
        const expenses = await expRes.json();
        
        // Fetch payments
        const payRes = await fetch('/api/payments');
        const payments = await payRes.json();
        
        // Merge & Sort chronologically descending
        const allTransactions = [];
        expenses.forEach(e => allTransactions.push({ ...e, type: 'expense' }));
        payments.forEach(p => allTransactions.push({ ...p, type: 'payment' }));
        
        allTransactions.sort((a, b) => new Date(b.date) - new Date(a.date));
        
        if (allTransactions.length === 0) {
            list.innerHTML = `<p class="text-secondary" style="padding: 1rem;">No transactions recorded yet. Upload a CSV or log manually.</p>`;
            return;
        }
        
        allTransactions.forEach(t => {
            const card = document.createElement('div');
            card.className = 'ledger-card';
            
            const isExpense = t.type === 'expense';
            const iconClass = isExpense ? 'fa-solid fa-receipt' : 'fa-solid fa-hand-holding-dollar';
            const bgClass = isExpense ? 'icon-expense' : 'icon-payment';
            
            const dateStr = formatDisplayDate(t.date);
            
            let description = t.description;
            let payerLabel = isExpense ? `Paid by ${t.payer_name}` : `${t.sender_name} → ${t.receiver_name}`;
            
            let amountInrStr = `₹${t.amount_inr.toFixed(2)}`;
            let foreignStr = '';
            if (t.currency !== 'INR') {
                foreignStr = `${t.currency} ${t.amount.toFixed(2)} (@ ₹${t.exchange_rate})`;
            }
            
            card.innerHTML = `
                <div class="ledger-icon ${bgClass}">
                    <i class="${iconClass}"></i>
                </div>
                <div class="ledger-info">
                    <span class="ledger-desc">${description}</span>
                    <span class="ledger-meta">${dateStr} • ${payerLabel}</span>
                </div>
                <div class="ledger-amount-block">
                    <span class="ledger-inr-val ${isExpense ? 'text-red' : 'text-green'}">${isExpense ? '-' : '+'}${amountInrStr}</span>
                    <span class="ledger-foreign-val">${foreignStr}</span>
                </div>
            `;
            list.appendChild(card);
        });
    } catch (e) {
        console.error("Failed to load expenses:", e);
    }
}

// VIEW 5: CSV UPLOADER & WIZARD
function setupDropzone() {
    const dropzone = document.getElementById('dropzone');
    const input = document.getElementById('csvFileInput');
    
    if (!dropzone || !input) return;
    
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    
    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });
    
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleUploadedCSV(files[0]);
        }
    });
    
    input.addEventListener('change', (e) => {
        const files = e.target.files;
        if (files.length > 0) {
            handleUploadedCSV(files[0]);
        }
    });
}

async function handleUploadedCSV(file) {
    if (!file.name.endsWith('.csv')) {
        alert("Please select a valid CSV file.");
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch('/api/import/analyze', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if (data.error) {
            alert(data.error);
            return;
        }
        
        state.csvAnalysisRows = data.rows;
        state.importFilename = data.filename;
        
        // Switch view to review wizard list
        document.getElementById('dropzone').style.display = 'none';
        document.getElementById('importReviewContainer').style.display = 'block';
        document.getElementById('importReportContainer').style.display = 'none';
        
        renderWizardRows();
    } catch (e) {
        console.error("Failed to analyze CSV:", e);
    }
}

function renderWizardRows() {
    const container = document.getElementById('reviewRowsList');
    container.innerHTML = '';
    
    let anomaliesCount = 0;
    
    state.csvAnalysisRows.forEach((row, index) => {
        const card = document.createElement('div');
        const hasAnoms = row.anomalies.length > 0;
        const anomSeverity = hasAnoms ? (row.anomalies.some(a => a.severity === 'error') ? 'has-errors' : 'has-warnings') : '';
        card.className = `review-row-card ${anomSeverity}`;
        card.id = `row-card-${index}`;
        
        if (hasAnoms) anomaliesCount++;
        
        // Badges
        let badgesHTML = '';
        row.anomalies.forEach(a => {
            const label = a.type.replace(/_/g, ' ');
            const badgeClass = a.severity === 'error' ? 'badge-err' : 'badge-warn';
            badgesHTML += `<span class="anomaly-badge ${badgeClass}">${label}</span>`;
        });
        
        // Create expanding details view
        let detailsHTML = '';
        if (hasAnoms || row.is_settlement || row.parsed.currency === 'USD') {
            detailsHTML = `
                <div class="card-details-panel" id="row-panel-${index}">
                    ${row.anomalies.map(a => `
                        <div class="anomaly-alert-box ${a.severity === 'error' ? 'alert-err' : ''}">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                            <span>${a.message}</span>
                        </div>
                    `).join('')}
                    
                    <div class="resolution-inputs">
                        <div class="form-group">
                            <label>Description</label>
                            <input type="text" value="${row.parsed.description}" data-field="description" data-row-idx="${index}" oninput="updateRowField(${index}, 'description', this.value)">
                        </div>
                        <div class="form-group">
                            <label>Amount</label>
                            <input type="number" step="0.001" value="${row.parsed.amount}" data-field="amount" data-row-idx="${index}" oninput="updateRowField(${index}, 'amount', parseFloat(this.value))">
                        </div>
                        <div class="form-group">
                            <label>Currency</label>
                            <select data-field="currency" data-row-idx="${index}" onchange="updateRowField(${index}, 'currency', this.value); updateExRateFieldVisibility(${index})">
                                <option value="INR" ${row.parsed.currency === 'INR' ? 'selected' : ''}>INR</option>
                                <option value="USD" ${row.parsed.currency === 'USD' ? 'selected' : ''}>USD</option>
                            </select>
                        </div>
                        <div class="form-group" id="row-exrate-group-${index}" style="display: ${row.parsed.currency === 'USD' ? 'block' : 'none'};">
                            <label>Exchange Rate</label>
                            <input type="number" step="0.01" value="${row.parsed.exchange_rate || 83.50}" data-field="exchange_rate" data-row-idx="${index}" oninput="updateRowField(${index}, 'exchange_rate', parseFloat(this.value))">
                        </div>
                        <div class="form-group">
                            <label>Payer (Paid By)</label>
                            <select data-field="paid_by" data-row-idx="${index}" onchange="updateRowField(${index}, 'paid_by', this.value)">
                                <option value="">Select Payer</option>
                                ${state.users.map(u => `<option value="${u.name}" ${row.parsed.paid_by === u.name ? 'selected' : ''}>${u.name}</option>`).join('')}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Date (YYYY-MM-DD)</label>
                            <input type="text" value="${row.parsed.date}" data-field="date" data-row-idx="${index}" oninput="updateRowField(${index}, 'date', this.value)">
                        </div>
                        <div class="form-group">
                            <label>Action</label>
                            <select data-field="action" data-row-idx="${index}" onchange="updateRowAction(${index}, this.value)">
                                <option value="import" ${row.action !== 'skip' ? 'selected' : ''}>Import Row</option>
                                <option value="skip" ${row.action === 'skip' ? 'selected' : ''}>Delete/Skip Row</option>
                            </select>
                        </div>
                    </div>
                </div>
            `;
        }
        
        card.innerHTML = `
            <div class="card-summary-line" onclick="toggleDetailsPanel(${index})">
                <div class="row-main-info">
                    <span class="row-id-badge">Row ${row.row_index}</span>
                    <span class="row-desc-text">${row.parsed.description}</span>
                    <span class="row-amount-badge">${row.parsed.currency === 'USD' ? '$' : '₹'}${row.parsed.amount.toFixed(2)}</span>
                    <span class="text-secondary">paid by ${row.parsed.paid_by || 'Unknown'}</span>
                </div>
                <div class="row-badges">
                    ${badgesHTML}
                    <i class="fa-solid fa-chevron-down text-secondary" id="row-chevron-${index}"></i>
                </div>
            </div>
            ${detailsHTML}
        `;
        container.appendChild(card);
    });
    
    document.getElementById('statTotalRows').textContent = state.csvAnalysisRows.length;
    document.getElementById('statAnomalousRows').textContent = anomaliesCount;
}

function toggleDetailsPanel(index) {
    const panel = document.getElementById(`row-panel-${index}`);
    const chevron = document.getElementById(`row-chevron-${index}`);
    if (panel) {
        const isHidden = panel.style.display === 'none';
        panel.style.display = isHidden ? 'flex' : 'none';
        chevron.className = isHidden ? 'fa-solid fa-chevron-up text-secondary' : 'fa-solid fa-chevron-down text-secondary';
    }
}

function updateRowField(rowIndex, field, value) {
    state.csvAnalysisRows[rowIndex].parsed[field] = value;
    
    // Resolve error states locally
    const card = document.getElementById(`row-card-${rowIndex}`);
    card.classList.add('resolved-card');
}

function updateRowAction(rowIndex, action) {
    state.csvAnalysisRows[rowIndex].action = action;
    const card = document.getElementById(`row-card-${rowIndex}`);
    if (action === 'skip') {
        card.style.opacity = '0.5';
    } else {
        card.style.opacity = '1.0';
    }
}

function updateExRateFieldVisibility(rowIndex) {
    const currency = document.querySelector(`#row-panel-${rowIndex} select[data-field="currency"]`).value;
    const exRateGroup = document.getElementById(`row-exrate-group-${rowIndex}`);
    if (exRateGroup) {
        exRateGroup.style.display = currency === 'USD' ? 'block' : 'none';
    }
}

async function confirmImport() {
    const payload = {
        filename: state.importFilename,
        rows: state.csvAnalysisRows
    };
    
    try {
        const res = await fetch('/api/import/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        
        if (data.error) {
            alert("Import failed: " + data.error);
            return;
        }
        
        // Fetch import report details
        const reportRes = await fetch(`/api/imports/${data.import_id}/report`);
        const report = await reportRes.json();
        
        renderImportReport(data.stats, report);
    } catch (e) {
        console.error("Failed to confirm CSV import:", e);
    }
}

function renderImportReport(stats, report) {
    // Hide review panel, show report panel
    document.getElementById('importReviewContainer').style.display = 'none';
    document.getElementById('importReportContainer').style.display = 'block';
    
    document.getElementById('reportTimestamp').textContent = new Date(report.imported_at).toLocaleString();
    
    const statsGrid = document.getElementById('reportStatsGrid');
    statsGrid.innerHTML = `
        <div class="report-stat-box">
            <span class="report-stat-num text-green">${stats.imported_expenses}</span>
            <span class="stat-label">Expenses Imported</span>
        </div>
        <div class="report-stat-box">
            <span class="report-stat-num text-green">${stats.imported_payments}</span>
            <span class="stat-label">Settlements Logged</span>
        </div>
        <div class="report-stat-box">
            <span class="report-stat-num text-warning">${stats.skipped_duplicates}</span>
            <span class="stat-label">Duplicates Skipped</span>
        </div>
        <div class="report-stat-box">
            <span class="report-stat-num text-green">${stats.anomalies_logged}</span>
            <span class="stat-label">Corrections Executed</span>
        </div>
    `;
    
    const tbody = document.getElementById('reportTableBody');
    tbody.innerHTML = '';
    
    if (report.anomalies.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center;">No anomalies or corrections needed. Clean import!</td></tr>`;
        return;
    }
    
    report.anomalies.forEach(anom => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>Row ${anom.row_index}</td>
            <td><span class="anomaly-badge badge-warn">${anom.anomaly_type.replace(/_/g, ' ')}</span></td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${anom.original_data}</td>
            <td>${anom.detected_issue}</td>
            <td class="text-green"><strong>${anom.action_taken}</strong></td>
        `;
        tbody.appendChild(tr);
    });
}

function resetImportWizard() {
    document.getElementById('csvFileInput').value = '';
    document.getElementById('dropzone').style.display = 'flex';
    document.getElementById('importReviewContainer').style.display = 'none';
    document.getElementById('importReportContainer').style.display = 'none';
}

function closeImportReport() {
    resetImportWizard();
    // Refresh dashboard balances
    loadDashboard();
    // Switch tab to Dashboard
    const dashboardTab = document.querySelector('.nav-tab[data-tab="dashboard"]');
    if (dashboardTab) dashboardTab.click();
}

// --- GENERAL UTILITY HELPERS ---
function formatDisplayDate(dateStr) {
    if (!dateStr) return '';
    try {
        const dt = new Date(dateStr);
        return dt.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    } catch (e) {
        return dateStr;
    }
}
