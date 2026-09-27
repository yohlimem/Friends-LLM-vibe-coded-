/* ==========================================================================
   WhatsApp Persona AI Fine-Tuner - App Logic & Presets Manager
   ========================================================================== */

document.addEventListener("DOMContentLoaded", () => {
    // --- State Variables ---
    let parsedChatData = null;
    let datasetMeta = null;
    let eventSource = null;
    let lossChart = null;
    let loadedPresets = [];
    let activePresetId = null;
    let chatHistoriesByPreset = {}; // Per-preset chat history memory

    // --- Tab Navigation ---
    const navTabs = document.querySelectorAll(".nav-tab");
    const tabContents = document.querySelectorAll(".tab-content");

    navTabs.forEach(tab => {
        tab.addEventListener("click", () => {
            navTabs.forEach(t => t.classList.remove("active"));
            tabContents.forEach(c => c.classList.remove("active"));

            tab.classList.add("active");
            const targetId = tab.getAttribute("data-tab");
            document.getElementById(targetId).classList.add("active");
        });
    });

    // --- Chart.js Setup for Training Loss ---
    const ctx = document.getElementById("lossChart").getContext("2d");
    lossChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Training Loss',
                data: [],
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af', font: { size: 10 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#9ca3af', font: { size: 10 } }
                }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });

    // --- System Hardware Monitor (Poll every 3s) ---
    async function updateSystemStatus() {
        try {
            const res = await fetch("/api/system-status");
            const data = await res.json();

            const nameEl = document.getElementById("gpuNameDisplay");
            const fillEl = document.getElementById("gpuMemFill");
            const textEl = document.getElementById("gpuMemText");

            if (data.gpu_available) {
                nameEl.textContent = data.gpu_name || "NVIDIA RTX 4080 Super";
                const pct = Math.min(100, (data.vram_used_gb / data.vram_total_gb) * 100);
                fillEl.style.width = `${pct}%`;
                textEl.textContent = `${data.vram_used_gb} / ${data.vram_total_gb} GB VRAM`;
            } else {
                nameEl.textContent = "CPU Mode (No GPU)";
                fillEl.style.width = "0%";
                textEl.textContent = "0 / 0 GB VRAM";
            }
        } catch (err) {
            console.error("Failed to fetch system status:", err);
        }
    }
    updateSystemStatus();
    setInterval(updateSystemStatus, 3000);

    // --- MODEL PRESETS & IMPORT/EXPORT MANAGER ---
    let pendingRenamePresetId = null;

    async function loadPresets() {
        try {
            const res = await fetch("/api/presets");
            const data = await res.json();
            loadedPresets = data.presets || [];
            renderPresetsGrid(loadedPresets);
            populateActivePresetDropdown(loadedPresets);
        } catch (err) {
            console.error("Failed to load presets:", err);
        }
    }
    loadPresets();

    function populateActivePresetDropdown(presets) {
        const select = document.getElementById("activePresetSelect");
        const resumeSelect = document.getElementById("resumePresetSelect");
        if (select) select.innerHTML = "";
        if (resumeSelect) resumeSelect.innerHTML = "";

        if (presets.length === 0) {
            const opt = document.createElement("option");
            opt.value = "";
            opt.textContent = "אין מודלים מאומנים עדיין (אימן מודל בטאב 3)";
            if (select) select.appendChild(opt);

            if (resumeSelect) {
                const optR = document.createElement("option");
                optR.value = "";
                optR.textContent = "אין מודלים מאומנים עדיין";
                resumeSelect.appendChild(optR);
            }
            return;
        }

        presets.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = `${p.name} (${p.base_model.split('/')[1] || p.base_model})`;
            if (select) select.appendChild(opt);

            if (resumeSelect) {
                const optR = document.createElement("option");
                optR.value = p.id;
                optR.textContent = `${p.name} (${p.base_model.split('/')[1] || p.base_model})`;
                resumeSelect.appendChild(optR);
            }
        });

        if (activePresetId && presets.some(p => p.id === activePresetId)) {
            if (select) select.value = activePresetId;
        } else if (presets.length > 0 && select && !select.value) {
            select.value = presets[0].id;
        }

        updateSystemPromptForSelectedPreset();
    }

    function updateSystemPromptForSelectedPreset() {
        const select = document.getElementById("activePresetSelect");
        const selectedId = select ? select.value : null;
        if (!selectedId) return;

        const preset = loadedPresets.find(p => p.id === selectedId);
        if (preset) {
            const chatPromptInput = document.getElementById("chatSystemPromptInput");
            if (chatPromptInput) {
                chatPromptInput.value = preset.system_prompt || `You are now responding and speaking exactly like ${preset.name}. Use the same speaking style, vocabulary, slang, and language mixing (Hebrew/English) exactly as it appeared in the WhatsApp chats.`;
            }
        }
    }

    const activeSelectEl = document.getElementById("activePresetSelect");
    if (activeSelectEl) {
        activeSelectEl.addEventListener("change", updateSystemPromptForSelectedPreset);
    }

    function renderPresetsGrid(presets) {
        const grid = document.getElementById("presetsGrid");
        grid.innerHTML = "";

        if (presets.length === 0) {
            grid.innerHTML = `<p class="subtitle">לא נמצאו מודלים מאומנים. תוכל לאמן מודל בטאב 3 או לייבא מודל מקובץ .zip בלשונית למטה.</p>`;
            return;
        }

        presets.forEach(p => {
            const isActive = activePresetId === p.id;
            const card = document.createElement("div");
            card.className = `preset-card ${isActive ? 'active-model' : ''}`;
            card.innerHTML = `
                <div class="preset-header">
                    <div class="preset-title">
                        <i class="fa-solid fa-robot"></i> ${escapeHtml(p.name)}
                    </div>
                    <span class="preset-badge ${isActive ? 'active' : 'idle'}">${isActive ? 'טוען ב-GPU' : 'שמור בדיסק'}</span>
                </div>
                <div class="preset-meta">
                    <span><strong>מודל בסיס:</strong> ${escapeHtml(p.base_model)}</span>
                    <span><strong>תאריך יצירה:</strong> ${p.created_at || 'N/A'}</span>
                    <span><strong>נתיב:</strong> <code>${escapeHtml(p.adapter_path)}</code></span>
                </div>
                <div class="preset-actions">
                    <button class="btn primary-btn btn-load-preset"><i class="fa-solid fa-play"></i> טען</button>
                    <button class="btn accent-btn btn-continue-train"><i class="fa-solid fa-fire"></i> המשך אימון</button>
                    <button class="btn outline-btn btn-rename-preset"><i class="fa-solid fa-pen"></i></button>
                    <button class="btn outline-btn btn-export-zip"><i class="fa-solid fa-download"></i></button>
                    <button class="btn danger-btn btn-delete-preset"><i class="fa-solid fa-trash"></i></button>
                </div>
            `;
            grid.appendChild(card);

            card.querySelector(".btn-load-preset").addEventListener("click", () => switchActivePreset(p.id));
            card.querySelector(".btn-continue-train").addEventListener("click", () => {
                document.querySelector('[data-tab="trainTab"]').click();
                setTrainMode("continue");
                const resumeSelect = document.getElementById("resumePresetSelect");
                if (resumeSelect) resumeSelect.value = p.id;
                document.getElementById("personaNameInput").value = p.name;
                appendConsoleLog(`[Training] הוגדר המשך אימון עבור הפרסונה '${p.name}'.`);
            });
            card.querySelector(".btn-rename-preset").addEventListener("click", () => openRenameModal(p.id, p.name));
            card.querySelector(".btn-export-zip").addEventListener("click", (e) => exportPresetZip(p.id, e.currentTarget));
            card.querySelector(".btn-delete-preset").addEventListener("click", () => deletePreset(p.id));
        });
    }

    // --- RENAME MODAL DIALOG ---
    function openRenameModal(presetId, currentName) {
        pendingRenamePresetId = presetId;
        const input = document.getElementById("renameModalInput");
        input.value = currentName;
        document.getElementById("renameModal").classList.add("active");
        setTimeout(() => input.focus(), 100);
    }

    function closeRenameModal() {
        document.getElementById("renameModal").classList.remove("active");
        pendingRenamePresetId = null;
    }

    const btnCancelRename = document.getElementById("btnCancelRename");
    if (btnCancelRename) {
        btnCancelRename.addEventListener("click", closeRenameModal);
    }

    async function submitRename() {
        if (!pendingRenamePresetId) return;
        const input = document.getElementById("renameModalInput");
        const newName = input.value.trim();
        const btnConfirm = document.getElementById("btnConfirmRename");
        if (!newName) {
            flashUiError(input);
            triggerButtonFeedback(btnConfirm, false, `<i class="fa-solid fa-triangle-exclamation"></i> הכנס שם תקין`, 2000);
            return;
        }

        const presetId = pendingRenamePresetId;
        closeRenameModal();

        try {
            const res = await fetch("/api/rename-preset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preset_id: presetId, new_name: newName })
            });
            const data = await res.json();
            if (data.status === "success") {
                if (activePresetId === presetId) {
                    document.getElementById("friendNameDisplay").textContent = newName;
                }
                await loadPresets();
                const presetsGrid = document.getElementById("presetsGrid");
                if (presetsGrid) flashUiSuccess(presetsGrid);
                appendConsoleLog(`[Preset] השם שונה בהצלחה ל: '${newName}'.`);
            } else {
                appendConsoleLog(`[Preset Error] שגיאה בשינוי השם: ${data.detail || "Unknown error"}`);
            }
        } catch (err) {
            appendConsoleLog(`[Network Error] שגיאה בתקשורת: ${err}`);
        }
    }

    const btnConfirmRename = document.getElementById("btnConfirmRename");
    if (btnConfirmRename) {
        btnConfirmRename.addEventListener("click", submitRename);
    }

    const renameModalInput = document.getElementById("renameModalInput");
    if (renameModalInput) {
        renameModalInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                submitRename();
            } else if (e.key === "Escape") {
                closeRenameModal();
            }
        });
    }

    async function switchActivePreset(presetId) {
        const preset = loadedPresets.find(p => p.id === presetId);
        if (!preset) return;

        appendConsoleLog(`[Preset] מעביר מודל פעיל ל: ${preset.name}...`);
        const btnLoad = document.getElementById("btnSwitchPreset");
        btnLoad.disabled = true;
        btnLoad.classList.add("btn-loading-state");
        btnLoad.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> טוען ${preset.name}...`;

        try {
            const res = await fetch("/api/load-model", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ preset_id: presetId })
            });
            const data = await res.json();

            activePresetId = presetId;
            document.getElementById("friendNameDisplay").textContent = preset.name;
            document.getElementById("chatStatusText").innerHTML = `<i class="fa-solid fa-circle"></i> מחובר (${preset.name})`;
            
            // Set chat system prompt for active persona
            const chatPromptInput = document.getElementById("chatSystemPromptInput");
            if (chatPromptInput) {
                chatPromptInput.value = preset.system_prompt || `אתה עכשיו עונה ומדבר בדיוק כמו ${preset.name}.`;
            }

            renderPresetsGrid(loadedPresets);
            populateActivePresetDropdown(loadedPresets);

            if (!chatHistoriesByPreset[presetId]) {
                chatHistoriesByPreset[presetId] = [];
            }
            renderChatHistory(preset.name, chatHistoriesByPreset[presetId]);

            const gpuBadge = document.querySelector(".gpu-badge");
            if (gpuBadge) flashUiCyan(gpuBadge);

            btnLoad.classList.remove("btn-loading-state");
            triggerButtonFeedback(btnLoad, true, `<i class="fa-solid fa-check"></i> נטען בהצלחה ל-GPU!`, 3000);
            appendConsoleLog(`[Preset] המודל '${preset.name}' נטען בהצלחה ל-GPU ומוכן לשיחה.`);
        } catch (err) {
            btnLoad.classList.remove("btn-loading-state");
            triggerButtonFeedback(btnLoad, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בטעינת המודל`, 3000);
            appendConsoleLog(`[Preset Error] שגיאה בטעינת המודל: ${err}`);
        } finally {
            btnLoad.disabled = false;
        }
    }

    document.getElementById("btnSwitchPreset").addEventListener("click", () => {
        const selectedId = document.getElementById("activePresetSelect").value;
        if (selectedId) {
            switchActivePreset(selectedId);
        }
    });

    async function exportPresetZip(presetId, btnEl) {
        const originalHtml = btnEl ? btnEl.innerHTML : "";
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> מוריד...`;
        }

        appendConsoleLog(`[Export] מוריד קובץ ZIP עבור Preset '${presetId}'...`);

        try {
            const res = await fetch(`/api/export-model/${presetId}`);
            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "Failed to download zip");
            }

            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.style.display = "none";
            a.href = url;
            a.download = `${presetId}_lora_weights.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            appendConsoleLog(`[Export] הקובץ ${presetId}_lora_weights.zip יורד כעת!`);
            if (btnEl) triggerButtonFeedback(btnEl, true, `<i class="fa-solid fa-check"></i> יורד...`, 2500);
        } catch (err) {
            if (btnEl) triggerButtonFeedback(btnEl, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה`, 2500);
            appendConsoleLog(`[Export Error] שגיאה בהורדת קובץ ZIP: ${err.message}`);
        } finally {
            if (btnEl) {
                btnEl.disabled = false;
            }
        }
    }

    async function deletePreset(presetId) {
        if (!confirm(`האם אתה בטוח שברצונך למחוק את Preset המודל '${presetId}'?`)) return;

        try {
            const res = await fetch(`/api/delete-preset/${presetId}`, { method: "DELETE" });
            if (res.ok) {
                if (activePresetId === presetId) activePresetId = null;
                await loadPresets();
                const presetsGrid = document.getElementById("presetsGrid");
                if (presetsGrid) flashUiSuccess(presetsGrid);
                appendConsoleLog(`[Preset] ה-Preset '${presetId}' נמחק בהצלחה.`);
            } else {
                appendConsoleLog(`[Preset Error] שגיאה במחיקת ה-Preset.`);
            }
        } catch (err) {
            appendConsoleLog(`[Preset Error] שגיאה במחיקת ה-Preset: ${err}`);
        }
    }

    // --- IMPORT MODEL ZIP HANDLER ---
    const importZipFileInput = document.getElementById("importZipFileInput");
    const btnSubmitImport = document.getElementById("btnSubmitImport");

    btnSubmitImport.addEventListener("click", async () => {
        const nameInput = document.getElementById("importPresetNameInput");
        const name = nameInput.value.trim();
        const files = importZipFileInput.files;

        if (!name) {
            flashUiError(nameInput);
            triggerButtonFeedback(btnSubmitImport, false, `<i class="fa-solid fa-triangle-exclamation"></i> הכנס שם לפרסונה`, 2500);
            return;
        }
        if (!files || files.length === 0) {
            flashUiError(importZipFileInput);
            triggerButtonFeedback(btnSubmitImport, false, `<i class="fa-solid fa-triangle-exclamation"></i> בחר קובץ ZIP`, 2500);
            return;
        }

        const formData = new FormData();
        formData.append("preset_name", name);
        formData.append("file", files[0]);

        btnSubmitImport.disabled = true;
        btnSubmitImport.classList.add("btn-loading-state");
        btnSubmitImport.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> מייבא מודל...`;

        try {
            const res = await fetch("/api/import-model", {
                method: "POST",
                body: formData
            });
            const data = await res.json();

            if (data.status === "success") {
                const importCard = btnSubmitImport.closest(".card");
                if (importCard) flashUiSuccess(importCard);
                nameInput.value = "";
                importZipFileInput.value = "";
                await loadPresets();
                btnSubmitImport.classList.remove("btn-loading-state");
                triggerButtonFeedback(btnSubmitImport, true, `<i class="fa-solid fa-check"></i> יובא בהצלחה!`, 3500);
                appendConsoleLog(`[Import] המודל '${name}' יובא בהצלחה.`);
            } else {
                btnSubmitImport.classList.remove("btn-loading-state");
                triggerButtonFeedback(btnSubmitImport, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בייבוא`, 3000);
                appendConsoleLog(`[Import Error] שגיאה בייבוא המודל: ${data.detail || "Unknown error"}`);
            }
        } catch (err) {
            btnSubmitImport.classList.remove("btn-loading-state");
            triggerButtonFeedback(btnSubmitImport, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בתקשורת`, 3000);
            appendConsoleLog(`[Network Error] שגיאה בתקשורת: ${err}`);
        } finally {
            btnSubmitImport.disabled = false;
        }
    });

    // --- SAVE CHAT SYSTEM PROMPT FOR ACTIVE PRESET ---
    const btnSaveChatPrompt = document.getElementById("btnSaveChatPrompt");
    if (btnSaveChatPrompt) {
        btnSaveChatPrompt.addEventListener("click", async () => {
            if (!activePresetId) {
                const selectEl = document.getElementById("activePresetSelect");
                if (selectEl) flashUiError(selectEl);
                triggerButtonFeedback(btnSaveChatPrompt, false, `<i class="fa-solid fa-triangle-exclamation"></i> בחר מודל תחילה`, 2500);
                return;
            }
            const promptInput = document.getElementById("chatSystemPromptInput");
            const promptVal = promptInput.value;
            btnSaveChatPrompt.disabled = true;
            btnSaveChatPrompt.classList.add("btn-loading-state");
            btnSaveChatPrompt.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> שומר...`;

            try {
                const res = await fetch("/api/update-preset-prompt", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ preset_id: activePresetId, system_prompt: promptVal })
                });
                if (res.ok) {
                    const preset = loadedPresets.find(p => p.id === activePresetId);
                    if (preset) preset.system_prompt = promptVal;
                    flashUiSuccess(promptInput);
                    btnSaveChatPrompt.classList.remove("btn-loading-state");
                    triggerButtonFeedback(btnSaveChatPrompt, true, `<i class="fa-solid fa-check"></i> נשמר בהצלחה!`, 2500);
                    appendConsoleLog(`[Preset] ה-System Prompt של '${preset.name}' נשמר בהצלחה.`);
                } else {
                    btnSaveChatPrompt.classList.remove("btn-loading-state");
                    triggerButtonFeedback(btnSaveChatPrompt, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בשמירה`, 2500);
                }
            } catch (err) {
                btnSaveChatPrompt.classList.remove("btn-loading-state");
                triggerButtonFeedback(btnSaveChatPrompt, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בתקשורת`, 2500);
            } finally {
                btnSaveChatPrompt.disabled = false;
            }
        });
    }

    // --- FILE UPLOAD & PARSING (ACCUMULATING MULTI-FILE QUEUE) ---
    const dropZone = document.getElementById("dropZone");
    const chatFileInput = document.getElementById("chatFileInput");
    const btnClearFiles = document.getElementById("btnClearFiles");
    let accumulatedFiles = [];

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.add("dragover");
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, (e) => {
            e.preventDefault();
            dropZone.classList.remove("dragover");
        }, false);
    });

    dropZone.addEventListener("drop", (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            addIncomingFiles(files);
        }
    });

    chatFileInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files.length > 0) {
            addIncomingFiles(e.target.files);
            chatFileInput.value = ""; // Reset so same file can be re-selected if removed
        }
    });

    if (btnClearFiles) {
        btnClearFiles.addEventListener("click", (e) => {
            accumulatedFiles = [];
            uploadAccumulatedFiles();
            flashUiError(dropZone);
            triggerButtonFeedback(e.currentTarget, false, `<i class="fa-solid fa-trash"></i> נוקה`, 1500);
            appendConsoleLog("[Upload] כל הקבצים שנטענו נוקו.");
        });
    }

    function addIncomingFiles(filesInput) {
        const incoming = Array.from(filesInput);
        let addedCount = 0;

        incoming.forEach(newFile => {
            const exists = accumulatedFiles.some(
                existing => existing.name === newFile.name && existing.size === newFile.size && existing.lastModified === newFile.lastModified
            );
            if (!exists) {
                accumulatedFiles.push(newFile);
                addedCount++;
            }
        });

        if (addedCount > 0) {
            uploadAccumulatedFiles();
        } else {
            appendConsoleLog("[Upload] הקבצים שגררת כבר קיימים ברשימה המצטברת.");
        }
    }

    function removeAccumulatedFile(idx) {
        if (idx >= 0 && idx < accumulatedFiles.length) {
            const removed = accumulatedFiles.splice(idx, 1)[0];
            appendConsoleLog(`[Upload] הקובץ '${removed.name}' הוסר מהרשימה המצטברת.`);
            uploadAccumulatedFiles();
        }
    }

    function renderFileListPills() {
        const fileContainer = document.getElementById("fileListContainer");
        const filePills = document.getElementById("fileListPills");
        const countBadge = document.getElementById("fileCountBadge");

        if (!fileContainer || !filePills) return;

        if (accumulatedFiles.length === 0) {
            fileContainer.style.display = "none";
            filePills.innerHTML = "";
            return;
        }

        fileContainer.style.display = "block";
        filePills.innerHTML = "";
        if (countBadge) countBadge.textContent = accumulatedFiles.length;

        accumulatedFiles.forEach((file, index) => {
            const pill = document.createElement("div");
            pill.style.cssText = "display: inline-flex; align-items: center; gap: 6px; background: rgba(255, 255, 255, 0.07); border: 1px solid rgba(255, 255, 255, 0.12); padding: 5px 10px; border-radius: 6px; font-size: 0.82rem; color: var(--text-main);";
            
            const isDiscord = file.name.endsWith(".json") || file.name.toLowerCase().includes("discord");
            const iconClass = isDiscord ? "fa-brands fa-discord" : "fa-brands fa-whatsapp";
            const iconColor = isDiscord ? "#5865F2" : "#25D366";
            
            const sizeKb = (file.size / 1024).toFixed(0);

            pill.innerHTML = `
                <i class="${iconClass}" style="color: ${iconColor};"></i>
                <span style="font-weight: 500;">${escapeHtml(file.name)}</span>
                <span style="color: var(--text-muted); font-size: 0.75rem;">(${sizeKb} KB)</span>
                <button type="button" title="הסר קובץ זה" style="background: none; border: none; color: #ef4444; font-size: 1rem; cursor: pointer; padding: 0 0 0 4px; line-height: 1;">&times;</button>
            `;

            pill.querySelector("button").addEventListener("click", () => {
                removeAccumulatedFile(index);
            });

            filePills.appendChild(pill);
        });
    }

    async function uploadAccumulatedFiles() {
        renderFileListPills();

        if (accumulatedFiles.length === 0) {
            parsedChatData = null;
            document.getElementById("statsWrapper").style.display = "none";
            document.getElementById("previewCard").style.display = "none";
            return;
        }

        const formData = new FormData();
        accumulatedFiles.forEach(f => formData.append("files", f));

        appendConsoleLog(`[Upload] מעלה ומפענח ${accumulatedFiles.length} קבצי צ'אט מצטברים...`);

        try {
            const res = await fetch("/api/upload-chat", {
                method: "POST",
                body: formData
            });
            const data = await res.json();

            if (data.status === "success") {
                parsedChatData = data;
                renderUploadStats(data);
                flashUiSuccess(dropZone);

                const sourceStr = data.stats.chat_source || "Chat";
                appendConsoleLog(`[Upload] ${accumulatedFiles.length} קבצים פוענחו ומוזגו בהצלחה! מקור: ${sourceStr}. סה"כ הודעות: ${data.stats.total_messages.toLocaleString()}.`);
            } else {
                flashUiError(dropZone);
                appendConsoleLog(`[Upload Error] שגיאה בפענוח הקבצים: ${data.detail || "שגיאה כללית"}`);
            }
        } catch (err) {
            flashUiError(dropZone);
            appendConsoleLog(`[Network Error] שגיאה בתקשורת עם השרת: ${err}`);
        }
    }

    function renderUploadStats(data) {
        const stats = data.stats;
        document.getElementById("statsWrapper").style.display = "block";
        document.getElementById("previewCard").style.display = "block";

        const badgeEl = document.getElementById("statSourceBadge");
        if (badgeEl) {
            const sourceStr = stats.chat_source || "WhatsApp & Discord";
            const iconClass = sourceStr.toLowerCase().includes("discord") && sourceStr.toLowerCase().includes("whatsapp") 
                ? "fa-solid fa-comments" 
                : (sourceStr.toLowerCase().includes("discord") ? "fa-brands fa-discord" : "fa-brands fa-whatsapp");
            badgeEl.innerHTML = `<i class="${iconClass}" style="margin-left: 4px;"></i> ${sourceStr} (${stats.files_count || 1} קבצים)`;
        }

        document.getElementById("statTotalMsgs").textContent = stats.total_messages.toLocaleString();
        
        const hebPct = stats.total_messages > 0 ? Math.round((stats.hebrew_messages / stats.total_messages) * 100) : 0;
        const engPct = stats.total_messages > 0 ? Math.round((stats.english_messages / stats.total_messages) * 100) : 0;

        document.getElementById("statHebrewRatio").textContent = `${hebPct}%`;
        document.getElementById("statEnglishRatio").textContent = `${engPct}%`;
        document.getElementById("statMediaCount").textContent = (stats.media_omitted_count + (stats.urls_removed_count || 0)).toLocaleString();

        // Render participant role mapping list
        renderParticipantRoleList(stats);

        const previewList = document.getElementById("chatPreviewList");
        previewList.innerHTML = "";
        data.sample_messages.slice(0, 10).forEach(msg => {
            const div = document.createElement("div");
            div.className = "preview-item";
            div.innerHTML = `<div class="preview-sender">${escapeHtml(msg.sender)} (${msg.date} ${msg.time})</div><div>${escapeHtml(msg.content)}</div>`;
            previewList.appendChild(div);
        });

        // Flash stats wrapper and role assignment box to guide user eyes with color
        flashUiSuccess(document.getElementById("statsWrapper"));
        flashUiSuccess(document.getElementById("previewCard"));
        const roleBox = document.querySelector(".role-assignment-box");
        if (roleBox) flashUiPurple(roleBox);
    }

    let participantRoles = {}; // { [senderName]: 'friend' | 'user' | 'ignore' }

    function renderParticipantRoleList(stats, changedSender = null) {
        const listEl = document.getElementById("participantRoleList");
        if (!listEl) return;
        listEl.innerHTML = "";

        const senders = stats.top_senders || [];
        if (senders.length === 0) {
            listEl.innerHTML = `<p class="help-text" style="padding: 10px;">לא זוהו משתתפים בשיחות.</p>`;
            return;
        }

        senders.forEach((sender, idx) => {
            // Default role assignment if not set
            if (!participantRoles[sender]) {
                if (idx === 0) {
                    participantRoles[sender] = 'friend';
                } else if (idx === 1 || senders.length === 2) {
                    participantRoles[sender] = 'user';
                } else {
                    participantRoles[sender] = 'ignore';
                }
            }

            const count = stats.sender_counts[sender] || 0;
            const currentRole = participantRoles[sender];
            const wasJustChanged = changedSender === sender;

            const row = document.createElement("div");
            row.className = `participant-role-row role-${currentRole} ${wasJustChanged ? 'role-just-changed' : ''}`;
            
            let iconClass = "fa-robot";
            if (currentRole === 'user') iconClass = "fa-user";
            else if (currentRole === 'ignore') iconClass = "fa-eye-slash";

            row.innerHTML = `
                <div class="participant-info">
                    <i class="fa-solid ${iconClass} role-icon" style="font-size: 1.15rem;"></i>
                    <div>
                        <span class="participant-name" title="${escapeHtml(sender)}">${escapeHtml(sender)}</span>
                        <span class="participant-count">${count.toLocaleString()} הודעות</span>
                    </div>
                </div>
                <div class="role-btn-group">
                    <button type="button" class="btn-role ${currentRole === 'friend' ? 'active-friend' : ''}" data-role="friend">🤖 החבר (AI)</button>
                    <button type="button" class="btn-role ${currentRole === 'user' ? 'active-user' : ''}" data-role="user">👤 אני (User)</button>
                    <button type="button" class="btn-role ${currentRole === 'ignore' ? 'active-ignore' : ''}" data-role="ignore">⚪ התעלם</button>
                </div>
            `;

            row.querySelectorAll(".btn-role").forEach(btn => {
                btn.addEventListener("click", () => {
                    const newRole = btn.getAttribute("data-role");
                    participantRoles[sender] = newRole;
                    renderParticipantRoleList(stats, sender);
                });
            });

            listEl.appendChild(row);
        });

        updateTargetPromptFromRoles();
    }

    function updateTargetPromptFromRoles() {
        const friendNames = Object.keys(participantRoles).filter(s => participantRoles[s] === 'friend');
        const mainFriend = friendNames.length > 0 ? friendNames[0] : "החבר שלי";

        const personaInput = document.getElementById("personaNameInput");
        if (personaInput) personaInput.value = `${mainFriend} AI`;

        const promptInput = document.getElementById("systemPromptInput");
        if (promptInput) {
            promptInput.value = 
                `You are now responding and speaking exactly like ${mainFriend}. Use the same speaking style, vocabulary, slang, and language mixing (Hebrew/English) exactly as it appeared in the chat logs.`;
        }

        const selectEl = document.getElementById("targetFriendSelect");
        if (selectEl) selectEl.value = friendNames.join(", ");
        const aliasEl = document.getElementById("targetAliasesInput");
        if (aliasEl) aliasEl.value = friendNames.join(", ");
    }

    document.getElementById("btnGoToDataset").addEventListener("click", () => {
        document.querySelector('[data-tab="datasetTab"]').click();
        const datasetCard = document.querySelector("#datasetTab .card");
        if (datasetCard) flashUiPurple(datasetCard);
    });

    // --- Slider Displays ---
    const sessionGapInput = document.getElementById("sessionGapInput");
    if (sessionGapInput) {
        sessionGapInput.addEventListener("input", (e) => {
            document.getElementById("sessionGapVal").textContent = e.target.value;
        });
    }

    document.getElementById("contextTurnsInput").addEventListener("input", (e) => {
        document.getElementById("contextTurnsVal").textContent = e.target.value;
    });

    document.getElementById("valSplitInput").addEventListener("input", (e) => {
        document.getElementById("valSplitVal").textContent = e.target.value;
    });

    document.getElementById("tempInput").addEventListener("input", (e) => {
        document.getElementById("tempVal").textContent = e.target.value;
    });

    document.getElementById("topPInput").addEventListener("input", (e) => {
        document.getElementById("topPVal").textContent = e.target.value;
    });

    // --- DATASET BUILDER ---
    document.getElementById("btnBuildDataset").addEventListener("click", async () => {
        const targetFriends = Object.keys(participantRoles).filter(s => participantRoles[s] === 'friend');
        const userNames = Object.keys(participantRoles).filter(s => participantRoles[s] === 'user');
        const btnBuild = document.getElementById("btnBuildDataset");
        const roleBox = document.querySelector(".role-assignment-box");

        if (targetFriends.length === 0) {
            if (roleBox) flashUiError(roleBox);
            triggerButtonFeedback(btnBuild, false, `<i class="fa-solid fa-triangle-exclamation"></i> לא נבחר חבר (AI)`, 3000);
            return;
        }

        if (userNames.length === 0) {
            if (roleBox) flashUiError(roleBox);
            triggerButtonFeedback(btnBuild, false, `<i class="fa-solid fa-triangle-exclamation"></i> לא נבחר משתמש (אני)`, 3000);
            return;
        }

        btnBuild.disabled = true;
        btnBuild.classList.add("btn-loading-state");
        btnBuild.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> יוצר דאטהסט JSONL...`;

        const systemPrompt = document.getElementById("systemPromptInput").value;
        const contextTurns = parseInt(document.getElementById("contextTurnsInput").value);
        const valSplit = parseFloat(document.getElementById("valSplitInput").value) / 100.0;
        const sessionGap = parseInt(document.getElementById("sessionGapInput") ? document.getElementById("sessionGapInput").value : 60);
        const includeFull = document.getElementById("includeFullSessionsCheck") ? document.getElementById("includeFullSessionsCheck").checked : true;

        appendConsoleLog(`[Dataset] מייצר דאטהסט: פרסונה מאומנת = [${targetFriends.join(', ')}], שואלים (אני) = [${userNames.join(', ')}]...`);

        try {
            const res = await fetch("/api/build-dataset", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    target_friend: targetFriends,
                    user_names: userNames,
                    system_prompt: systemPrompt,
                    context_turns: contextTurns,
                    val_split: valSplit,
                    session_gap_minutes: sessionGap,
                    include_full_sessions: includeFull
                })
            });
            const data = await res.json();

            if (data.status === "success") {
                datasetMeta = data;
                const statsBadge = document.getElementById("datasetStatsBadge");
                if (statsBadge) {
                    statsBadge.style.display = "flex";
                    flashUiSuccess(statsBadge);
                }
                if (document.getElementById("dsTotalSessions")) document.getElementById("dsTotalSessions").textContent = data.total_sessions || 0;
                if (document.getElementById("dsAvgSessionLen")) document.getElementById("dsAvgSessionLen").textContent = data.avg_session_length || 0;
                document.getElementById("dsTotalSamples").textContent = data.total_samples;
                document.getElementById("dsTrainSamples").textContent = data.train_samples;
                document.getElementById("dsValSamples").textContent = data.val_samples;

                const jsonBox = document.getElementById("jsonPreviewBox");
                if (jsonBox) {
                    jsonBox.textContent = JSON.stringify(data.sample_preview, null, 2);
                    flashUiSuccess(jsonBox);
                }

                const currentCard = btnBuild.closest(".card");
                if (currentCard) flashUiSuccess(currentCard);

                appendConsoleLog(`[Dataset] דאטהסט JSONL נוצר בהצלחה! ${data.total_samples} דוגמאות אימון שחוברו בין [${userNames.join(', ')}] לבין [${targetFriends.join(', ')}].`);

                btnBuild.classList.remove("btn-loading-state");
                triggerButtonFeedback(btnBuild, true, `<i class="fa-solid fa-circle-check"></i> הדאטהסט נוצר בהצלחה! (${data.total_samples} דוגמאות)`, 4000);
            } else {
                btnBuild.classList.remove("btn-loading-state");
                const currentCard = btnBuild.closest(".card");
                if (currentCard) flashUiError(currentCard);
                triggerButtonFeedback(btnBuild, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה ביצירת הדאטהסט`, 3500);
                appendConsoleLog(`[Dataset Error] שגיאה ביצירת הדאטהסט: ${data.detail || "שגיאה כללית"}`);
            }
        } catch (err) {
            btnBuild.classList.remove("btn-loading-state");
            const currentCard = btnBuild.closest(".card");
            if (currentCard) flashUiError(currentCard);
            triggerButtonFeedback(btnBuild, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בתקשורת`, 3500);
            appendConsoleLog(`[Network Error] שגיאה בתקשורת: ${err}`);
        } finally {
            btnBuild.disabled = false;
        }
    });

    // --- TRAINING STUDIO EXECUTION ---
    const modeOptionNew = document.getElementById("modeOptionNew");
    const modeOptionContinue = document.getElementById("modeOptionContinue");
    const resumePresetGroup = document.getElementById("resumePresetGroup");

    function setTrainMode(mode) {
        if (!modeOptionNew || !modeOptionContinue) return;
        const radioNew = modeOptionNew.querySelector('input');
        const radioContinue = modeOptionContinue.querySelector('input');

        if (mode === "continue") {
            if (radioContinue) radioContinue.checked = true;
            if (radioNew) radioNew.checked = false;
            modeOptionContinue.classList.add("active");
            modeOptionNew.classList.remove("active");
            if (resumePresetGroup) resumePresetGroup.style.display = "block";

            const lrInput = document.getElementById("lrInput");
            if (lrInput && lrInput.value === "0.0002") {
                lrInput.value = "0.0001";
            }
        } else {
            if (radioNew) radioNew.checked = true;
            if (radioContinue) radioContinue.checked = false;
            modeOptionNew.classList.add("active");
            modeOptionContinue.classList.remove("active");
            if (resumePresetGroup) resumePresetGroup.style.display = "none";
        }
    }

    if (modeOptionNew && modeOptionContinue) {
        modeOptionNew.addEventListener("click", () => setTrainMode("new"));
        modeOptionContinue.addEventListener("click", () => setTrainMode("continue"));
    }

    const btnStartTraining = document.getElementById("btnStartTraining");
    const btnStopTraining = document.getElementById("btnStopTraining");

    btnStartTraining.addEventListener("click", async () => {
        const personaName = document.getElementById("personaNameInput").value.trim() || "My Friend AI";
        const baseModel = document.getElementById("baseModelSelect").value;
        const epochs = parseInt(document.getElementById("epochsInput").value);
        const lr = parseFloat(document.getElementById("lrInput").value);
        const loraR = parseInt(document.getElementById("loraRankInput").value);
        const batchSize = parseInt(document.getElementById("batchSizeInput").value);

        const checkedRadio = document.querySelector('input[name="trainMode"]:checked');
        const trainMode = checkedRadio ? checkedRadio.value : "new";
        const resumePresetId = document.getElementById("resumePresetSelect") ? document.getElementById("resumePresetSelect").value : null;

        if (trainMode === "continue" && (!resumePresetId || resumePresetId === "")) {
            const selectEl = document.getElementById("resumePresetSelect");
            if (selectEl) flashUiError(selectEl);
            triggerButtonFeedback(btnStartTraining, false, `<i class="fa-solid fa-triangle-exclamation"></i> בחר מודל להמשך`, 2500);
            return;
        }

        btnStartTraining.style.display = "none";
        btnStopTraining.style.display = "inline-flex";

        const logMsg = trainMode === "continue" 
            ? `[Training] משיק המשך אימון עבור המודל '${personaName}' מתוך Preset '${resumePresetId}'...`
            : `[Training] משיק תהליך אימון חדש עבור '${personaName}' על בסיס ${baseModel}...`;
        appendConsoleLog(logMsg);

        try {
            const res = await fetch("/api/start-training", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    persona_name: personaName,
                    base_model_name: baseModel,
                    epochs: epochs,
                    learning_rate: lr,
                    lora_r: loraR,
                    batch_size: batchSize,
                    train_mode: trainMode,
                    resume_preset_id: resumePresetId
                })
            });
            const data = await res.json();
            listenToTrainingLogs();
        } catch (err) {
            btnStartTraining.style.display = "inline-flex";
            btnStopTraining.style.display = "none";
            const trainCard = btnStartTraining.closest(".card");
            if (trainCard) flashUiError(trainCard);
            triggerButtonFeedback(btnStartTraining, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה בהפעלה`, 3000);
            appendConsoleLog(`[Training Error] שגיאה בהפעלת האימון: ${err}`);
        }
    });

    btnStopTraining.addEventListener("click", async () => {
        await fetch("/api/stop-training", { method: "POST" });
        btnStartTraining.style.display = "inline-flex";
        btnStopTraining.style.display = "none";
        appendConsoleLog("[Training] תהליך האימון נעצר ע\"י המשתמש.");
    });

    let lastConsoleMessage = "";

    function listenToTrainingLogs() {
        if (eventSource) {
            eventSource.close();
        }

        lastConsoleMessage = "";
        eventSource = new EventSource("/api/training-logs-stream");
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            const pct = data.progress_pct || 0;
            document.getElementById("trainingProgressBar").style.width = `${pct}%`;
            document.getElementById("trainingProgressText").textContent = `${pct}%`;

            document.getElementById("metricEpoch").textContent = `${data.current_epoch || 0} / ${data.total_epochs || 3}`;
            document.getElementById("metricStep").textContent = `${data.current_step || 0} / ${data.max_steps || 0}`;
            document.getElementById("metricLoss").textContent = data.latest_loss !== null ? data.latest_loss : 'N/A';
            document.getElementById("metricVram").textContent = `${data.gpu_mem_used_gb || 0} GB`;

            if (data.message && data.message !== lastConsoleMessage) {
                lastConsoleMessage = data.message;
                appendConsoleLog(`[Trainer] ${data.message}`);
            }

            if (data.logs_history && data.logs_history.length > 0) {
                lossChart.data.labels = data.logs_history.map(item => `Step ${item.step}`);
                lossChart.data.datasets[0].data = data.logs_history.map(item => item.loss);
                lossChart.update();
            }

            if (data.state === "completed") {
                appendConsoleLog("[Training] 🎉 האימון הסתיים בהצלחה! המודל נשמר ב-Presets.");
                btnStartTraining.style.display = "inline-flex";
                btnStopTraining.style.display = "none";
                triggerButtonFeedback(btnStartTraining, true, `<i class="fa-solid fa-fire"></i> האימון הסתיים בהצלחה!`, 5000);
                const metrics = document.querySelector(".metrics-dashboard");
                if (metrics) flashUiSuccess(metrics);
                eventSource.close();
                loadPresets();
            } else if (data.state === "error") {
                appendConsoleLog(`[Training] ❌ שגיאה באימון: ${data.message}`);
                btnStartTraining.style.display = "inline-flex";
                btnStopTraining.style.display = "none";
                triggerButtonFeedback(btnStartTraining, false, `<i class="fa-solid fa-triangle-exclamation"></i> שגיאה באימון`, 4000);
                const metrics = document.querySelector(".metrics-dashboard");
                if (metrics) flashUiError(metrics);
                eventSource.close();
            }
        };
    }

    // --- PERSONA CHAT MESSENGER ---
    const chatInput = document.getElementById("chatInput");
    const btnSendMessage = document.getElementById("btnSendMessage");
    const chatContainer = document.getElementById("chatMessagesContainer");

    btnSendMessage.addEventListener("click", sendChatMessage);
    chatInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendChatMessage();
        }
    });

    async function sendChatMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        chatInput.value = "";

        const presetKey = activePresetId || "default";
        if (!chatHistoriesByPreset[presetKey]) {
            chatHistoriesByPreset[presetKey] = [];
        }

        const friendName = document.getElementById("friendNameDisplay").textContent || "החבר AI";

        // Add user bubble
        appendChatBubble("user", "אתה", text);
        chatHistoriesByPreset[presetKey].push({ role: "user", content: text });

        // Add assistant placeholder bubble
        const assistantBubble = appendChatBubble("assistant", friendName, "");

        const temp = parseFloat(document.getElementById("tempInput").value);
        const topP = parseFloat(document.getElementById("topPInput").value);
        const systemPrompt = document.getElementById("chatSystemPromptInput").value || document.getElementById("systemPromptInput").value;

        try {
            const res = await fetch("/api/chat-stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    messages: chatHistoriesByPreset[presetKey],
                    system_prompt: systemPrompt,
                    temperature: temp,
                    top_p: topP
                })
            });

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let fullReply = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split("\n\n");

                for (const line of lines) {
                    if (line.startsWith("data: ")) {
                        try {
                            const json = JSON.parse(line.substring(6));
                            if (json.token) {
                                fullReply += json.token;
                                assistantBubble.querySelector(".bubble-text").textContent = fullReply;
                                chatContainer.scrollTop = chatContainer.scrollHeight;
                            }
                        } catch (e) {}
                    }
                }
            }

            chatHistoriesByPreset[presetKey].push({ role: "assistant", content: fullReply });
        } catch (err) {
            assistantBubble.querySelector(".bubble-text").textContent = "[שגיאה בתקשורת עם השרת]";
        }
    }

    function renderChatHistory(friendName, history) {
        chatContainer.innerHTML = "";
        if (!history || history.length === 0) {
            appendChatBubble("assistant", friendName, `אהלן! אני ${friendName}. שאל אותי כל דבר!`);
            return;
        }

        history.forEach(m => {
            const sender = m.role === "user" ? "אתה" : friendName;
            appendChatBubble(m.role, sender, m.content);
        });
    }

    function appendChatBubble(role, senderName, text) {
        const div = document.createElement("div");
        div.className = `chat-bubble ${role}`;
        div.innerHTML = `<div class="bubble-sender">${escapeHtml(senderName)}</div><div class="bubble-text">${escapeHtml(text)}</div>`;
        chatContainer.appendChild(div);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        return div;
    }

    document.getElementById("btnClearChat").addEventListener("click", (e) => {
        const presetKey = activePresetId || "default";
        chatHistoriesByPreset[presetKey] = [];
        const friendName = document.getElementById("friendNameDisplay").textContent || "החבר AI";
        renderChatHistory(friendName, []);
        flashUiCyan(chatContainer);
        triggerButtonFeedback(e.currentTarget, true, `<i class="fa-solid fa-trash"></i> היסטוריה נוקתה`, 1500);
    });

    // --- HELPER FUNCTIONS ---
    function appendConsoleLog(msg) {
        const body = document.getElementById("consoleBody");
        const p = document.createElement("p");
        p.className = "log-line info";
        const time = new Date().toLocaleTimeString();
        p.textContent = `[${time}] ${msg}`;
        body.appendChild(p);
        body.scrollTop = body.scrollHeight;
    }

    function escapeHtml(str) {
        return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    // --- DIRECT UI COLOR FEEDBACK SYSTEM (NO CHAT MESSAGES / NO TOASTS) ---
    function flashUiSuccess(el) {
        if (!el) return;
        el.classList.remove("ui-flash-success", "ui-flash-error", "ui-flash-purple", "ui-flash-cyan");
        void el.offsetWidth;
        el.classList.add("ui-flash-success");
        setTimeout(() => el.classList.remove("ui-flash-success"), 1600);
    }

    function flashUiError(el) {
        if (!el) return;
        el.classList.remove("ui-flash-success", "ui-flash-error", "ui-flash-purple", "ui-flash-cyan");
        void el.offsetWidth;
        el.classList.add("ui-flash-error");
        setTimeout(() => el.classList.remove("ui-flash-error"), 1600);
    }

    function flashUiPurple(el) {
        if (!el) return;
        el.classList.remove("ui-flash-success", "ui-flash-error", "ui-flash-purple", "ui-flash-cyan");
        void el.offsetWidth;
        el.classList.add("ui-flash-purple");
        setTimeout(() => el.classList.remove("ui-flash-purple"), 1600);
    }

    function flashUiCyan(el) {
        if (!el) return;
        el.classList.remove("ui-flash-success", "ui-flash-error", "ui-flash-purple", "ui-flash-cyan");
        void el.offsetWidth;
        el.classList.add("ui-flash-cyan");
        setTimeout(() => el.classList.remove("ui-flash-cyan"), 1600);
    }

    function triggerButtonFeedback(btn, isSuccess, tempHtml = null, duration = 3000) {
        if (!btn) return;
        if (!btn.dataset.origHtml) {
            btn.dataset.origHtml = btn.innerHTML;
        }
        btn.classList.remove("btn-loading-state", "btn-success-state", "btn-error-state");
        btn.classList.add(isSuccess ? "btn-success-state" : "btn-error-state");
        if (tempHtml) btn.innerHTML = tempHtml;

        setTimeout(() => {
            btn.classList.remove("btn-success-state", "btn-error-state");
            if (btn.dataset.origHtml) {
                btn.innerHTML = btn.dataset.origHtml;
                delete btn.dataset.origHtml;
            }
        }, duration);
    }
});
