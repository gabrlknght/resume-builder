/* -----------------------------------------------------------
   Resume Customizer — app.js
   Tab switching, dynamic arrays, form serialization,
   pdf.js preview, API calls for generate & save.
   ----------------------------------------------------------- */
/* eslint-disable no-unused-vars */ // functions called from HTML onclick attributes

// ---------------------------------------------------------------------------
// State — hydrated from server-rendered window.__DATA__
// ---------------------------------------------------------------------------
const state = JSON.parse(JSON.stringify(window.__DATA__));

// Staged review state for AI tailoring
let originalSnapshot = null;   // pre-tailoring state for Reset
let pendingTailored = null;    // AI results awaiting user approval
let currentPreviewTab = "pdf"; // "pdf" | "ai" | "letter"
let lastAiResultsHTML = "";    // persisted AI results HTML
let coverLetterData = null;    // last generated cover letter data
let lastCoverLetterHTML = "";  // persisted cover letter HTML

// PDF preview state
let pdfBlob = null;
let pdfDoc = null;
let currentPage = 1;
let totalPages = 0;

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
    populateScalarFields();
    renderEducation();
    renderExperience();
    renderProjects();
    renderSkills();
    initTabs();
    initProviderSelect({
        providerId: "ai-provider",
        modelId: "ai-model",
        baseUrlId: "ai-base-url",
        datalistId: "llama-cpp-models-list",
    });
    initProviderSelect({
        providerId: "cl-provider",
        modelId: "cl-model",
        baseUrlId: "cl-base-url",
        datalistId: "cl-llama-cpp-models-list",
    });
});

// ---------------------------------------------------------------------------
// Tabs & AI Config
// ---------------------------------------------------------------------------
function initTabs() {
    const btns = document.querySelectorAll("#sidebar button");
    btns.forEach((btn) => {
        btn.addEventListener("click", () => {
            btns.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
            document.getElementById("section-" + btn.dataset.tab).classList.add("active");
            document.querySelector(".layout").classList.toggle("no-preview", btn.dataset.tab === "stats");
            if (btn.dataset.tab === "history") {
                loadHistoryDashboard(1);
            }
            if (btn.dataset.tab === "clhistory") {
                loadClHistoryDashboard(1);
            }
            if (btn.dataset.tab === "stats") {
                loadStatsDashboard();
            }
        });
    });
}

function switchPreviewTab(tab) {
    currentPreviewTab = tab;
    const tabPdf = document.getElementById("tab-pdf");
    const tabAi = document.getElementById("tab-ai");
    const tabLetter = document.getElementById("tab-letter");
    const pageNav = document.getElementById("page-nav");

    [tabPdf, tabAi, tabLetter].forEach((t) => t && t.classList.remove("active"));

    if (tab === "pdf") {
        tabPdf.classList.add("active");
        if (pdfBlob) {
            renderPDFPreview(pdfBlob);
        } else {
            const body = document.getElementById("preview-body");
            body.innerHTML = `<div class="preview-empty" id="preview-empty">CLICK GENERATE TO PREVIEW</div>`;
            if (pageNav) pageNav.style.display = "none";
        }
    } else if (tab === "ai") {
        if (tabAi) tabAi.classList.add("active");
        if (pageNav) pageNav.style.display = "none";
        const body = document.getElementById("preview-body");
        body.innerHTML = lastAiResultsHTML;
    } else if (tab === "letter") {
        if (tabLetter) tabLetter.classList.add("active");
        if (pageNav) pageNav.style.display = "none";
        const body = document.getElementById("preview-body");
        body.innerHTML = lastCoverLetterHTML;
    }
}

function showPreviewTabs() {
    const tabsBar = document.getElementById("preview-tabs");
    if (tabsBar) tabsBar.style.display = "flex";
}

function showLetterTab() {
    showPreviewTabs();
    const tabLetter = document.getElementById("tab-letter");
    if (tabLetter) tabLetter.style.display = "";
}

// ---------------------------------------------------------------------------
// Provider select initialisation (shared between Tailor and Cover Letter tabs)
// ---------------------------------------------------------------------------
function initProviderSelect({ providerId, modelId, baseUrlId, datalistId }) {
    const providerSelect = document.getElementById(providerId);
    if (!providerSelect) return;

    const PROVIDER_CONFIGS = {
        "openai": { base_url: "", model: "gpt-4o-mini" },
        "cerebras": { base_url: "https://api.cerebras.ai/v1", model: "llama3.1-8b" },
        "nvidia": { base_url: "https://integrate.api.nvidia.com/v1", model: "moonshotai/kimi-k2.5" },
        "gemini": { base_url: "https://generativelanguage.googleapis.com/v1beta/openai/", model: "gemini-2.5-flash" },
        "llamacpp": { base_url: "http://localhost:8080", model: "" },
        "ollama": { base_url: "http://localhost:11434", model: "" },
        "openrouter": { base_url: "https://openrouter.ai/api/v1", model: "openrouter/free" },
        "openrouter_meta": { base_url: "https://openrouter.ai/api/v1", model: "meta-llama/llama-3.3-70b-instruct:free" },
        "custom": { base_url: "", model: "" }
    };

    // Ollama model aliases (same as backend)
    const OLLAMA_MODEL_ALIASES = {
        "lfm2.5": "lfm2.5:latest",
        "gemma4": "gemma4-opencode:latest",
        "qwen3.5": "qwen3.5-opencode:latest",
        "gpt-oss": "gpt-oss:20b",
    };

    providerSelect.addEventListener("change", (e) => {
        const provider = e.target.value;
        const config = PROVIDER_CONFIGS[provider];
        const modelInput = document.getElementById(modelId);
        const baseUrlInput = document.getElementById(baseUrlId);
        const datalist = document.getElementById(datalistId);

        if (config) {
            modelInput.value = config.model;
            baseUrlInput.value = config.base_url;
        }

        // Clear datalist for non-Ollama providers
        if (datalist) datalist.innerHTML = "";

        if (provider === "llamacpp") {
            const cppBase = (baseUrlInput.value || "http://localhost:8080").replace(/\/+$/, "");
            const modelsUrl = cppBase.endsWith("/v1") ? `${cppBase}/models` : `${cppBase}/v1/models`;
            modelInput.placeholder = "Fetching models…";
            fetch(modelsUrl)
                .then((r) => r.ok ? r.json() : Promise.reject(r.status))
                .then((data) => {
                    const models = (data.data || []).map((m) => m.id).filter(Boolean);
                    if (datalist) {
                        datalist.innerHTML = models
                            .map((m) => `<option value="${esc(m)}">`)
                            .join("");
                    }
                    if (models.length > 0 && !modelInput.value) {
                        modelInput.value = models[0];
                    }
                    modelInput.placeholder = models.length ? "Select or type a model" : "No models found — is llama.cpp running?";
                })
                .catch(() => {
                    modelInput.placeholder = "Could not reach llama.cpp at " + cppBase;
                });
        } else if (provider === "ollama") {
            const ollamaBase = (baseUrlInput.value || "http://localhost:11434").replace(/\/+$/, "");
            const tagsBase = ollamaBase.replace(/\/v1$/, "");
            modelInput.placeholder = "Fetching models…";
            fetch(`${tagsBase}/api/tags`)
                .then((r) => r.ok ? r.json() : Promise.reject(r.status))
                .then((data) => {
                    const models = (data.models || []).map((m) => m.name).filter(Boolean);
                    if (datalist) {
                        datalist.innerHTML = models
                            .map((m) => `<option value="${esc(m)}">`)
                            .join("");
                    }
                    if (models.length > 0 && !modelInput.value) {
                        modelInput.value = models[0];
                    }
                    modelInput.placeholder = models.length ? "Select or type a model" : "No models found — is Ollama running?";
                })
                .catch(() => {
                    modelInput.placeholder = "Could not reach Ollama at " + ollamaBase;
                });
        } else {
            modelInput.placeholder = "e.g. gpt-4o-mini";
        }
    });
}

// ---------------------------------------------------------------------------
// Scalar fields — Profile & Contact (data-path driven)
// ---------------------------------------------------------------------------
function populateScalarFields() {
    document.querySelectorAll("[data-path]").forEach((el) => {
        const val = getNestedValue(state, el.dataset.path);
        if (val !== undefined && val !== null) {
            el.value = val;
        }
        el.addEventListener("input", () => {
            setNestedValue(state, el.dataset.path, el.value);
        });
    });
}

function getNestedValue(obj, path) {
    return path.split(".").reduce((o, k) => (o && o[k] !== undefined ? o[k] : undefined), obj);
}

function setNestedValue(obj, path, value) {
    const keys = path.split(".");
    let cur = obj;
    for (let i = 0; i < keys.length - 1; i++) {
        if (cur[keys[i]] === undefined) cur[keys[i]] = {};
        cur = cur[keys[i]];
    }
    cur[keys[keys.length - 1]] = value;
}

// ---------------------------------------------------------------------------
// Education
// ---------------------------------------------------------------------------
function renderEducation() {
    const list = document.getElementById("education-list");
    list.innerHTML = "";
    const edu = state.education || (state.education = { education: [] });
    const items = edu.education || (edu.education = []);

    items.forEach((entry, i) => {
        list.appendChild(createEducationEntry(entry, i));
    });
}

function createEducationEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";
    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeEducation(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>INSTITUTION</label>
                <input type="text" value="${esc(entry.institution || "")}" data-edu="${index}" data-key="institution">
            </div>
            <div class="field">
                <label>LOCATION</label>
                <input type="text" value="${esc(entry.location || "")}" data-edu="${index}" data-key="location">
            </div>
        </div>
        <div class="field">
            <label>DEGREE</label>
            <input type="text" value="${esc(entry.degree || "")}" data-edu="${index}" data-key="degree">
        </div>
        <div class="field">
            <label>DURATION</label>
            <input type="text" value="${esc(entry.duration || "")}" data-edu="${index}" data-key="duration">
        </div>
    `;
    div.querySelectorAll("input").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.edu);
            state.education.education[idx][inp.dataset.key] = inp.value;
        });
    });
    return div;
}

function addEducation() {
    if (!state.education) state.education = { education: [] };
    if (!state.education.education) state.education.education = [];
    state.education.education.push({ institution: "", location: "", degree: "", duration: "" });
    renderEducation();
}

function removeEducation(index) {
    state.education.education.splice(index, 1);
    renderEducation();
}

// ---------------------------------------------------------------------------
// Experience
// ---------------------------------------------------------------------------
function renderExperience() {
    const list = document.getElementById("experience-list");
    list.innerHTML = "";
    const exp = state.experience || (state.experience = { experience: [] });
    const items = exp.experience || (exp.experience = []);

    items.forEach((entry, i) => {
        list.appendChild(createExperienceEntry(entry, i));
    });
}

function createExperienceEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const details = entry.details || [];
    const detailsHtml = details
        .map(
            (d, di) => `
        <div class="detail-item">
            <textarea data-exp="${index}" data-detail="${di}">${esc(d)}</textarea>
            <button type="button" class="btn-danger btn-small" onclick="removeDetail(${index}, ${di})">×</button>
        </div>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeExperience(${index})">REMOVE</button>
        </div>
        <div class="field-row">
            <div class="field">
                <label>COMPANY</label>
                <input type="text" value="${esc(entry.company || "")}" data-exp-field="${index}" data-key="company">
            </div>
            <div class="field">
                <label>ROLE</label>
                <input type="text" value="${esc(entry.role || "")}" data-exp-field="${index}" data-key="role">
            </div>
        </div>
        <div class="field-row">
            <div class="field">
                <label>START DATE</label>
                <input type="text" value="${esc(entry.startDate || "")}" data-exp-field="${index}" data-key="startDate" placeholder="YYYY-MM">
            </div>
            <div class="field">
                <label>END DATE</label>
                <input type="text" value="${esc(entry.endDate || "")}" data-exp-field="${index}" data-key="endDate" placeholder="YYYY-MM OR EMPTY">
            </div>
        </div>
        <div class="field">
            <label>LOCATION</label>
            <input type="text" value="${esc(entry.location || "")}" data-exp-field="${index}" data-key="location">
        </div>
        <div class="field-group">
            <div class="field-group-title">DETAIL BULLETS</div>
            <div id="details-${index}">${detailsHtml}</div>
            <button type="button" class="btn-secondary btn-small" onclick="addDetail(${index})">+ ADD BULLET</button>
        </div>
    `;

    div.querySelectorAll("[data-exp-field]").forEach((inp) => {
        inp.addEventListener("input", () => {
            const idx = parseInt(inp.dataset.expField);
            const key = inp.dataset.key;
            const val = inp.value;
            state.experience.experience[idx][key] = val === "" && key === "endDate" ? null : val;
        });
    });

    div.querySelectorAll("[data-detail]").forEach((ta) => {
        ta.addEventListener("input", () => {
            const ei = parseInt(ta.dataset.exp);
            const di = parseInt(ta.dataset.detail);
            state.experience.experience[ei].details[di] = ta.value;
        });
    });

    return div;
}

function addExperience() {
    if (!state.experience) state.experience = { experience: [] };
    if (!state.experience.experience) state.experience.experience = [];
    state.experience.experience.push({
        company: "",
        role: "",
        startDate: "",
        endDate: null,
        location: "",
        details: [],
    });
    renderExperience();
}

function removeExperience(index) {
    state.experience.experience.splice(index, 1);
    renderExperience();
}

function addDetail(expIndex) {
    state.experience.experience[expIndex].details.push("");
    renderExperience();
}

function removeDetail(expIndex, detailIndex) {
    state.experience.experience[expIndex].details.splice(detailIndex, 1);
    renderExperience();
}

// ---------------------------------------------------------------------------
// Drag-and-drop reordering (shared by Projects and Skills)
// ---------------------------------------------------------------------------
function setupDragReorder(div, index, getArray, rerenderFn) {
    div.setAttribute('draggable', 'true');

    div.addEventListener('dragstart', (e) => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(index));
        setTimeout(() => div.classList.add('drag-source'), 0);
    });

    div.addEventListener('dragend', () => {
        div.classList.remove('drag-source');
        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
    });

    div.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        div.classList.add('drag-over');
    });

    div.addEventListener('dragleave', (e) => {
        if (!div.contains(e.relatedTarget)) div.classList.remove('drag-over');
    });

    div.addEventListener('drop', (e) => {
        e.preventDefault();
        div.classList.remove('drag-over');
        const src = parseInt(e.dataTransfer.getData('text/plain'));
        const dest = index;
        if (src === dest) return;
        const items = getArray();
        const [moved] = items.splice(src, 1);
        items.splice(dest, 0, moved);
        rerenderFn();
    });
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
function renderProjects() {
    const list = document.getElementById("projects-list");
    list.innerHTML = "";
    const proj = state.projects || (state.projects = { projects: [] });
    const items = proj.projects || (proj.projects = []);

    items.forEach((entry, i) => {
        list.appendChild(createProjectEntry(entry, i));
    });
}

function createProjectEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const techs = entry.technologies || [];
    const techTagsHtml = techs
        .map(
            (t, ti) =>
                `<span class="tech-tag">${esc(t)}<button type="button" onclick="removeTech(${index}, ${ti})">×</button></span>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="drag-handle" title="Drag to reorder">⠿</span>
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeProject(${index})">REMOVE</button>
        </div>
        <div class="field">
            <label>TITLE</label>
            <input type="text" value="${esc(entry.title || "")}" data-proj-field="${index}" data-key="title">
        </div>
        <div class="field">
            <label>DESCRIPTION</label>
            <textarea data-proj-field="${index}" data-key="description">${esc(entry.description || "")}</textarea>
        </div>
        <div class="field">
            <label>STATUS</label>
            <input type="text" value="${esc(entry.status || "")}" data-proj-field="${index}" data-key="status">
        </div>
        <div class="field-group">
            <div class="field-group-title">TECHNOLOGIES</div>
            <div class="tech-tags" id="techs-${index}">${techTagsHtml}</div>
            <div class="tech-add">
                <input type="text" id="tech-input-${index}" placeholder="Add technology">
                <button type="button" class="btn-secondary btn-small" onclick="addTech(${index})">ADD</button>
            </div>
        </div>
    `;

    div.querySelectorAll("[data-proj-field]").forEach((el) => {
        el.addEventListener("input", () => {
            const idx = parseInt(el.dataset.projField);
            state.projects.projects[idx][el.dataset.key] = el.value;
        });
    });

    const techInput = div.querySelector(`#tech-input-${index}`);
    if (techInput) {
        techInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addTech(index);
            }
        });
    }

    setupDragReorder(div, index, () => state.projects.projects, renderProjects);

    return div;
}

function addProject() {
    if (!state.projects) state.projects = { projects: [] };
    if (!state.projects.projects) state.projects.projects = [];
    state.projects.projects.push({
        title: "",
        description: "",
        technologies: [],
        status: "ongoing",
    });
    renderProjects();
}

function removeProject(index) {
    state.projects.projects.splice(index, 1);
    renderProjects();
}

function addTech(projIndex) {
    const input = document.getElementById("tech-input-" + projIndex);
    const val = input.value.trim();
    if (!val) return;
    state.projects.projects[projIndex].technologies.push(val);
    input.value = "";
    renderProjects();
}

function removeTech(projIndex, techIndex) {
    state.projects.projects[projIndex].technologies.splice(techIndex, 1);
    renderProjects();
}

// ---------------------------------------------------------------------------
// Skills
// ---------------------------------------------------------------------------
function renderSkills() {
    const list = document.getElementById("skills-list");
    list.innerHTML = "";
    const sk = state.skills || (state.skills = { skills: [] });
    const items = sk.skills || (sk.skills = []);
    items.forEach((entry, i) => {
        list.appendChild(createSkillCategoryEntry(entry, i));
    });
}

function createSkillCategoryEntry(entry, index) {
    const div = document.createElement("div");
    div.className = "array-entry";

    const itemTagsHtml = (entry.items || [])
        .map(
            (item, ii) =>
                `<span class="tech-tag">${esc(item)}<button type="button" onclick="removeSkillItem(${index}, ${ii})">×</button></span>`
        )
        .join("");

    div.innerHTML = `
        <div class="array-entry-header">
            <span class="drag-handle" title="Drag to reorder">⠿</span>
            <span class="array-entry-number">#${index + 1}</span>
            <button type="button" class="btn-danger btn-small" onclick="removeSkillCategory(${index})">REMOVE</button>
        </div>
        <div class="field">
            <label>CATEGORY</label>
            <input type="text" value="${esc(entry.category || "")}" data-skill-cat="${index}">
        </div>
        <div class="field-group">
            <div class="field-group-title">ITEMS</div>
            <div class="tech-tags" id="skill-items-${index}">${itemTagsHtml}</div>
            <div class="tech-add">
                <input type="text" id="skill-input-${index}" placeholder="Add skill">
                <button type="button" class="btn-secondary btn-small" onclick="addSkillItem(${index})">ADD</button>
            </div>
        </div>
    `;

    div.querySelector(`[data-skill-cat="${index}"]`).addEventListener("input", (e) => {
        state.skills.skills[index].category = e.target.value;
    });

    const skillInput = div.querySelector(`#skill-input-${index}`);
    if (skillInput) {
        skillInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                addSkillItem(index);
            }
        });
    }

    setupDragReorder(div, index, () => state.skills.skills, renderSkills);

    return div;
}

function addSkillCategory() {
    if (!state.skills) state.skills = { skills: [] };
    if (!state.skills.skills) state.skills.skills = [];
    state.skills.skills.push({ category: "", items: [] });
    renderSkills();
}

function removeSkillCategory(index) {
    state.skills.skills.splice(index, 1);
    renderSkills();
}

function addSkillItem(catIndex) {
    const input = document.getElementById("skill-input-" + catIndex);
    const val = input.value.trim();
    if (!val) return;
    state.skills.skills[catIndex].items.push(val);
    input.value = "";
    renderSkills();
}

function removeSkillItem(catIndex, itemIndex) {
    state.skills.skills[catIndex].items.splice(itemIndex, 1);
    renderSkills();
}

// ---------------------------------------------------------------------------
// Payload
// ---------------------------------------------------------------------------
function collectPayload() {
    return {
        profile: state.profile || {},
        contact: state.contact || {},
        education: state.education || { education: [] },
        experience: state.experience || { experience: [] },
        projects: state.projects || { projects: [] },
        skills: state.skills || { skills: [] },
    };
}

// ---------------------------------------------------------------------------
// API: Generate → Preview + Download
// ---------------------------------------------------------------------------
async function generatePDF() {
    const companyInput = document.getElementById("ai-company");
    const company = companyInput ? companyInput.value.trim() : "";
    if (!company) {
        toast("Please fill in the Prospective Company field before generating.", true);
        // Switch to tailoring tab so the user sees the field
        document.querySelectorAll("#sidebar button").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
        const tailorBtn = document.querySelector("#sidebar button[data-tab='tailoring']");
        if (tailorBtn) tailorBtn.classList.add("active");
        document.getElementById("section-tailoring").classList.add("active");
        if (companyInput) companyInput.focus();
        return;
    }

    const btn = document.getElementById("btn-generate");
    btn.classList.add("loading");
    btn.textContent = "GENERATING…";

    try {
        const meta = { ...(lastTailoringMeta || {}), company };
        const res = await fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...collectPayload(), _meta: meta }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Generation failed");
        }

        pdfBlob = await res.blob();

        // Extract filename from header
        const disposition = res.headers.get("content-disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        pdfBlob._filename = match ? match[1] : "resume.pdf";

        // Render in preview pane
        await renderPDFPreview(pdfBlob);
        toast("PDF GENERATED");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "GENERATE";
    }
}

// ---------------------------------------------------------------------------
// PDF.js Preview Rendering
// ---------------------------------------------------------------------------
async function renderPDFPreview(blob) {
    const pdfjsLib = await import("https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.min.mjs");
    pdfjsLib.GlobalWorkerOptions.workerSrc =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.4.168/pdf.worker.min.mjs";

    const arrayBuffer = await blob.arrayBuffer();
    pdfDoc = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    totalPages = pdfDoc.numPages;
    currentPage = 1;

    // Show page nav
    const nav = document.getElementById("page-nav");
    if (nav) nav.style.display = "flex";

    const empty = document.getElementById("preview-empty");
    if (empty) empty.style.display = "none";

    // Render all pages
    const container = document.getElementById("preview-body");
    container.innerHTML = "";

    for (let i = 1; i <= totalPages; i++) {
        const page = await pdfDoc.getPage(i);
        const scale = 1.5;
        const viewport = page.getViewport({ scale });

        const canvas = document.createElement("canvas");
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        canvas.id = "pdf-page-" + i;
        container.appendChild(canvas);

        const ctx = canvas.getContext("2d");
        await page.render({ canvasContext: ctx, viewport }).promise;
    }

    updatePageIndicator();
}

function updatePageIndicator() {
    document.getElementById("page-indicator").textContent = `${currentPage} / ${totalPages}`;
}

function prevPage() {
    if (currentPage <= 1) return;
    currentPage--;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function nextPage() {
    if (currentPage >= totalPages) return;
    currentPage++;
    scrollToPage(currentPage);
    updatePageIndicator();
}

function scrollToPage(num) {
    const canvas = document.getElementById("pdf-page-" + num);
    if (canvas) canvas.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---------------------------------------------------------------------------
// Download PDF
// ---------------------------------------------------------------------------
function downloadPDF() {
    if (!pdfBlob) return;
    const url = URL.createObjectURL(pdfBlob);
    const a = document.createElement("a");
    a.href = url;
    a.download = pdfBlob._filename || "resume.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// API: Save to Backend
// ---------------------------------------------------------------------------
async function saveToBackend() {
    const btn = document.getElementById("btn-save");
    btn.classList.add("loading");
    btn.textContent = "SAVING…";

    try {
        const res = await fetch("/api/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(collectPayload()),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.error || "Save failed");
        }

        toast("SAVED TO BACKEND");
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "SAVE TO BACKEND";
    }
}

// ---------------------------------------------------------------------------
// API: AI Tailoring
// ---------------------------------------------------------------------------
function updateProgress(pct, message) {
    const container = document.getElementById("tailor-progress");
    const fill = document.getElementById("progress-bar-fill");
    const text = document.getElementById("progress-text");
    if (container) container.style.display = "block";
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = message;
}

function handlePipelineEvent(event) {
    const stageMap = {
        1: { pct: 10, label: "Stage 1/4: Analyzing job description..." },
        2: { pct: 35, label: "Stage 2/4: Matching resume to requirements..." },
        3: { pct: 65, label: "Stage 3/4: Tailoring resume sections..." },
        4: { pct: 90, label: "Stage 4/4: Validating output..." },
    };

    if (event.status === "error") {
        updateProgress(0, "Error: " + (event.message || "Unknown error"));
        return;
    }

    if (event.status === "in_progress") {
        const info = stageMap[event.stage];
        if (info) updateProgress(info.pct, event.message || info.label);
        return;
    }

    if (event.status === "complete") {
        const info = stageMap[event.stage];
        if (info) updateProgress(info.pct, (info.label.replace("...", "") + " done"));
    }
}

function applyTailoredData(data, isSkip) {
    if (isSkip) {
        const relScore = data.relevance || 'N/A';
        lastAiResultsHTML = `
            <div style="width:100%; text-align:left;">
                <div style="font-size:11px; text-transform:uppercase; margin-bottom:0.5rem; border-bottom:1px solid var(--border); padding-bottom:0.5rem;">
                    <span style="color:var(--fg); font-weight:bold;">AI TAILORING — SKIPPED (LOW MATCH)</span>
                    <span style="color:#e74c3c; font-weight:bold; float:right;">JD: ${relScore}/10</span>
                </div>
                ${data.relevance_analysis ? `<div style="font-size:11px; color:var(--muted); line-height:1.6;">${esc(data.relevance_analysis)}</div>` : ''}
            </div>`;
        showPreviewTabs();
        switchPreviewTab("ai");
        return;
    }

    // Stage results — don't apply to state yet
    pendingTailored = {
        profile: data.profile || null,
        experience: data.experience || null,
        projects: data.projects || null
    };

    // Compute diff: original snapshot vs pending tailored
    const beforeStr = JSON.stringify(originalSnapshot, null, 2);
    const afterStr = JSON.stringify(pendingTailored, null, 2);

    let diffHtml = "";
    if (window.Diff) {
        const diff = Diff.diffWords(beforeStr, afterStr);
        diffHtml = diff.map(part => {
            let style = part.added ? "color: #2ecc71; font-weight: bold; background: rgba(46, 204, 113, 0.1);" : part.removed ? "color: #e74c3c; text-decoration: line-through; background: rgba(231, 76, 60, 0.1);" : "color: #888;";
            return `<span style="${style}">${esc(part.value)}</span>`;
        }).join("");
    } else {
        diffHtml = `<span style="color: #f1c40f">Diff library failed to load.</span>`;
    }

    const relScore = data.relevance || 'N/A';
    const relColor = typeof relScore === 'number' && relScore >= 7 ? '#2ecc71' : typeof relScore === 'number' && relScore >= 4 ? '#f1c40f' : '#e74c3c';

    let evalHtml = "";
    if (data.eval_scores && typeof data.eval_scores === 'object') {
        const es = data.eval_scores;
        const formatVal = (v) => {
            if (Array.isArray(v)) return v.length === 0 ? "none" : v.join(", ");
            if (v && typeof v === "object") return JSON.stringify(v);
            if (typeof v === "number") return (v <= 1 && v >= 0) ? (v * 100).toFixed(0) + "%" : String(v);
            return String(v);
        };
        const rows = [
            ["Alignment", es.job_alignment_score],
            ["Preservation", es.content_preservation],
        ];
        if (es.hallucinated_numbers && es.hallucinated_numbers.length > 0) {
            rows.push(["Hallucinated", es.hallucinated_numbers]);
        }
        if (es.immutable_violations && es.immutable_violations.length > 0) {
            rows.push(["Field violations", es.immutable_violations]);
        }
        if (es.overall_pass !== undefined) {
            rows.push(["Overall", es.overall_pass ? "passed" : "needs review"]);
        }
        evalHtml = `<div style="font-size: 11px; margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px dashed var(--border);">
            <div style="text-transform: uppercase; color: var(--fg); margin-bottom: 0.35rem;">EVAL SCORES:</div>
            ${rows.map(([k, v]) => `<div style="color: var(--muted); display: flex; justify-content: space-between;"><span>${esc(k)}</span><span style="color: var(--fg);">${esc(formatVal(v))}</span></div>`).join("")}
        </div>`;
    }

    const hasPending = pendingTailored !== null;
    lastAiResultsHTML = `
        <div style="width: 100%; height: 100%; display: flex; flex-direction: column; text-align: left;">
            <div style="font-size: 11px; text-transform: uppercase; margin-bottom: 0.5rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: var(--fg); font-weight: bold;">AI TAILORING RESULTS — REVIEW BEFORE APPLYING</span>
                <span style="color: ${relColor}; font-weight: bold; padding: 2px 6px; border: 1px solid ${relColor};">JD: ${relScore}/10</span>
            </div>
            ${data.relevance_analysis ? `<div style="font-size: 11px; color: var(--muted); margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 1px dashed var(--border); line-height: 1.6;">${esc(data.relevance_analysis)}</div>` : ''}
            ${evalHtml}
            <div style="font-size: 11px; text-transform: uppercase; color: var(--fg); margin-bottom: 0.5rem;">DIFF CHANGES:</div>
            <div style="position: relative; flex: 1; overflow-y: auto; min-height: 0;">
                <pre style="font-family: 'JetBrains Mono', monospace; font-size: 11px; background: #0a0a0a; padding: 0.5rem; white-space: pre-wrap; word-wrap: break-word; border: 1px solid var(--border); margin: 0;">${diffHtml}</pre>
                <div style="position: sticky; bottom: 0; display: flex; gap: 8px; padding: 8px; background: linear-gradient(transparent, var(--bg) 30%); margin-top: -2rem;">
                    <button onclick="applyPendingChanges()" style="flex: 1; padding: 8px; background: #2ecc71; color: #000; border: none; cursor: pointer; font-family: inherit; font-size: 11px; font-weight: bold; text-transform: uppercase;">Apply Changes</button>
                    <button onclick="discardPendingChanges()" style="flex: 1; padding: 8px; background: var(--bg); color: var(--fg); border: 1px solid var(--border); cursor: pointer; font-family: inherit; font-size: 11px; text-transform: uppercase;">Discard</button>
                    <button onclick="resetToOriginal()" style="padding: 8px 12px; background: var(--bg); color: var(--muted); border: 1px solid var(--border); cursor: pointer; font-family: inherit; font-size: 11px; text-transform: uppercase;" ${!originalSnapshot ? 'disabled' : ''}>Reset</button>
                </div>
            </div>
        </div>`;

    showPreviewTabs();
    switchPreviewTab("ai");
}

function applyPendingChanges() {
    if (!pendingTailored) return;
    if (pendingTailored.profile) Object.assign(state.profile, pendingTailored.profile);
    if (pendingTailored.experience) state.experience = pendingTailored.experience;
    if (pendingTailored.projects) state.projects = pendingTailored.projects;
    pendingTailored = null;

    populateScalarFields();
    renderExperience();
    renderProjects();
    generatePDF().then(() => switchPreviewTab("pdf"));
    toast("Changes applied to form fields.");
}

function discardPendingChanges() {
    pendingTailored = null;
    switchPreviewTab("pdf");
    toast("AI changes discarded.");
}

function resetToOriginal() {
    if (!originalSnapshot) return;
    state.profile = JSON.parse(JSON.stringify(originalSnapshot.profile));
    state.experience = JSON.parse(JSON.stringify(originalSnapshot.experience));
    state.projects = JSON.parse(JSON.stringify(originalSnapshot.projects));
    originalSnapshot = null;
    pendingTailored = null;

    populateScalarFields();
    renderExperience();
    renderProjects();
    generatePDF().then(() => switchPreviewTab("pdf"));
    toast("Reset to pre-tailoring state.");
}

async function tailorResume() {
    const jd = document.getElementById("ai-jd").value.trim();
    if (!jd) {
        toast("Please provide a Job Description", true);
        return;
    }

    const provider = document.getElementById("ai-provider").value;
    const model = document.getElementById("ai-model").value;
    const baseUrl = document.getElementById("ai-base-url").value;
    const apiKey = document.getElementById("ai-api-key").value;

    const btn = document.getElementById("btn-tailor");
    btn.classList.add("loading");
    btn.textContent = "TAILORING… (MAY TAKE A MINUTE)";

    try {
        const currentData = collectPayload();
        // Save snapshot for Reset functionality
        originalSnapshot = JSON.parse(JSON.stringify({
            profile: currentData.profile,
            experience: currentData.experience,
            projects: currentData.projects
        }));
        pendingTailored = null;

        const payload = {
            jd: jd,
            config: {
                provider: provider,
                model: model,
                base_url: baseUrl,
                api_key: apiKey
            },
            data: currentData
        };

        const res = await fetch("/api/tailor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!res.ok) {
            let errorMsg = "Tailoring failed";
            try {
                const err = await res.json();
                errorMsg = err.error || errorMsg;
            } catch { /* ignore JSON parse error — errorMsg stays as fallback */ }
            throw new Error(errorMsg);
        }

        // SSE streaming: read chunks from response body
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse complete SSE lines from the buffer
            const lines = buffer.split("\n");
            // Keep the last potentially incomplete line in the buffer
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith("data: ")) continue;
                const jsonStr = trimmed.slice("data: ".length);
                let event;
                try {
                    event = JSON.parse(jsonStr);
                } catch (e) {
                    continue;
                }

                // Error from pipeline
                if (event.status === "error") {
                    handlePipelineEvent(event);
                    throw new Error(event.message || "Pipeline error");
                }

                // Pipeline stage events
                if (event.stage !== "final") {
                    handlePipelineEvent(event);
                    continue;
                }

                // Final event
                if (event.stage === "final" && event.status === "complete") {
                    updateProgress(100, "Complete");
                    // Capture tailoring metadata for next generate call
                    if (event.data && event.data.jd_analysis) {
                        lastTailoringMeta = {
                            company: event.data.jd_analysis.company_name || "",
                            job_title: event.data.jd_analysis.job_title || "",
                            match_score: event.data.relevance || null,
                        };
                    }
                    applyTailoredData(event.data, false);
                    toast("RESUME TAILORED SUCCESSFULLY");
                } else if (event.stage === "final" && event.status === "skip") {
                    updateProgress(100, "Skipped — relevance already high");
                    applyTailoredData(event.data, true);
                    toast("RESUME ALREADY A GOOD MATCH");
                }
            }
        }
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "TAILOR RESUME (AI)";
        // Hide progress bar after a delay
        setTimeout(() => {
            const container = document.getElementById("tailor-progress");
            if (container) container.style.display = "none";
            const fill = document.getElementById("progress-bar-fill");
            if (fill) fill.style.width = "0";
        }, 3000);
    }
}

// ---------------------------------------------------------------------------
// Cover Letter Generator
// ---------------------------------------------------------------------------
function updateClProgress(pct, message) {
    const container = document.getElementById("cl-progress");
    const fill = document.getElementById("cl-progress-bar");
    const text = document.getElementById("cl-progress-text");
    if (container) container.style.display = "block";
    if (fill) fill.style.width = pct + "%";
    if (text) text.textContent = message;
}

function renderCoverLetterPreview(data) {
    coverLetterData = data;

    const paragraphs = [
        data.opening_paragraph,
        ...(data.body_paragraphs || []),
        data.closing_paragraph,
    ]
        .filter(Boolean)
        .map((p) => `<p class="cl-paragraph">${esc(p)}</p>`)
        .join("");

    const improvementsHtml =
        data.improvements_from_prior && data.improvements_from_prior.length > 0
            ? `<div class="cl-improvements">
                <div class="cl-improvements-title">IMPROVEMENTS FROM PRIOR LETTER</div>
                <ul>${data.improvements_from_prior.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>
               </div>`
            : "";

    const relScore = data.relevance;
    const relColor =
        typeof relScore === "number" && relScore >= 7
            ? "#2ecc71"
            : typeof relScore === "number" && relScore >= 4
            ? "#f1c40f"
            : "#e74c3c";

    lastCoverLetterHTML = `
        <div class="cl-preview">
            <div class="cl-meta">
                <span class="cl-job-badge">${esc(data.job_title || "")}${data.company ? " &middot; " + esc(data.company) : ""}</span>
                ${relScore !== undefined ? `<span class="cl-score-badge" style="color:${relColor}; border-color:${relColor};">JD MATCH: ${relScore}/10</span>` : ""}
            </div>
            <div class="cl-subject">${esc(data.subject_line || "")}</div>
            <div class="cl-letter">
                <div class="cl-salutation">${esc(data.salutation || "Dear Hiring Manager,")}</div>
                ${paragraphs}
                <div class="cl-signoff">
                    <div>${esc(data.sign_off || "Sincerely,")}</div>
                    <div class="cl-candidate-name">${esc(data.candidate_name || "")}</div>
                </div>
            </div>
            ${improvementsHtml}
            <div class="cl-actions">
                <button type="button" class="btn-secondary btn-small" onclick="copyCoverLetter()">COPY TEXT</button>
                <button type="button" class="btn-secondary btn-small" onclick="downloadCoverLetter()">DOWNLOAD .TXT</button>
                <button type="button" class="btn-secondary btn-small" onclick="printCoverLetter()">PRINT / PDF</button>
            </div>
        </div>`;

    showLetterTab();
    switchPreviewTab("letter");
}

function buildCoverLetterPlainText() {
    if (!coverLetterData) return "";
    const d = coverLetterData;
    const parts = [
        d.subject_line || "",
        "",
        d.salutation || "Dear Hiring Manager,",
        "",
        d.opening_paragraph || "",
        ...(d.body_paragraphs || []).map((p) => "\n" + p),
        "",
        d.closing_paragraph || "",
        "",
        d.sign_off || "Sincerely,",
        d.candidate_name || "",
    ];
    return parts.join("\n");
}

function copyCoverLetter() {
    const text = buildCoverLetterPlainText();
    if (!text) return;
    navigator.clipboard.writeText(text).then(
        () => toast("COVER LETTER COPIED"),
        () => toast("Copy failed — check browser permissions", true)
    );
}

function downloadCoverLetter() {
    const text = buildCoverLetterPlainText();
    if (!text) return;
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const company = (coverLetterData && coverLetterData.company) || "company";
    const role = (coverLetterData && coverLetterData.job_title) || "role";
    a.download = `cover_letter_${company}_${role}.txt`
        .replace(/[^a-z0-9_.-]/gi, "_")
        .toLowerCase();
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function printCoverLetter(d) {
    if (!d) d = coverLetterData;
    if (!d) return;
    const paragraphs = [
        d.opening_paragraph,
        ...(d.body_paragraphs || []),
        d.closing_paragraph,
    ]
        .filter(Boolean)
        .map((p) => `<p>${esc(p)}</p>`)
        .join("");

    const win = window.open("", "_blank");
    if (!win) {
        toast("Popup blocked — allow popups to print the cover letter", true);
        return;
    }
    win.document.write(`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cover Letter${d.company ? " — " + esc(d.company) : ""}</title>
<style>
  @page { margin: 2.5cm; }
  body { font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; line-height: 1.7; color: #000; max-width: 700px; margin: 0 auto; }
  .subject { font-size: 10pt; font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1.8em; color: #444; }
  .salutation { margin-bottom: 1em; }
  p { margin: 0 0 1em 0; text-align: justify; }
  .signoff { margin-top: 2em; }
  .name { font-weight: bold; margin-top: 0.3em; }
  @media print { button { display: none; } }
</style>
</head>
<body>
<div class="subject">${esc(d.subject_line || "")}</div>
<div class="salutation">${esc(d.salutation || "Dear Hiring Manager,")}</div>
${paragraphs}
<div class="signoff">
  <div>${esc(d.sign_off || "Sincerely,")}</div>
  <div class="name">${esc(d.candidate_name || "")}</div>
</div>
</body>
</html>`);
    win.document.close();
    win.focus();
    win.print();
}

async function printClHistoryEntry(entryId) {
    try {
        const res = await fetch(`/api/cl-history/restore/${entryId}`, { method: "POST" });
        if (!res.ok) throw new Error("Failed to load cover letter");
        printCoverLetter(await res.json());
    } catch (e) {
        toast(e.message, true);
    }
}

async function generateCoverLetter() {
    const jd = (document.getElementById("cl-jd").value || "").trim();
    if (!jd) {
        toast("Please provide a Job Description", true);
        return;
    }

    const priorLetter = (document.getElementById("cl-prior").value || "").trim();
    const provider = document.getElementById("cl-provider").value;
    const model = document.getElementById("cl-model").value;
    const baseUrl = document.getElementById("cl-base-url").value;
    const apiKey = document.getElementById("cl-api-key").value;

    const btn = document.getElementById("btn-cover-letter");
    btn.classList.add("loading");
    btn.textContent = "GENERATING… (MAY TAKE A MINUTE)";
    updateClProgress(0, "Starting…");

    const stageMap = {
        1: { pct: 20, label: "Stage 1/3: Analyzing job description..." },
        2: { pct: 50, label: "Stage 2/3: Matching resume credentials..." },
        3: { pct: 80, label: "Stage 3/3: Writing cover letter..." },
    };

    try {
        const payload = {
            jd,
            prior_letter: priorLetter || "",
            config: { provider, model, base_url: baseUrl, api_key: apiKey },
            data: collectPayload(),
        };

        const res = await fetch("/api/cover-letter", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (!res.ok) {
            let errorMsg = "Cover letter generation failed";
            try {
                const err = await res.json();
                errorMsg = err.error || errorMsg;
            } catch { /* ignore JSON parse error — errorMsg stays as fallback */ }
            throw new Error(errorMsg);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            const lines = buffer.split("\n");
            buffer = lines.pop();

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || !trimmed.startsWith("data: ")) continue;
                let event;
                try {
                    event = JSON.parse(trimmed.slice("data: ".length));
                } catch (_) {
                    continue;
                }

                if (event.status === "error") {
                    updateClProgress(0, "Error: " + (event.message || "Unknown error"));
                    throw new Error(event.message || "Pipeline error");
                }

                if (event.status === "in_progress") {
                    const info = stageMap[event.stage];
                    if (info) updateClProgress(info.pct, event.message || info.label);
                    continue;
                }

                if (event.status === "complete" && event.stage !== "final") {
                    const info = stageMap[event.stage];
                    if (info) updateClProgress(info.pct, info.label.replace("...", " \u2713"));
                    continue;
                }

                if (event.stage === "final" && event.status === "complete") {
                    updateClProgress(100, "Complete");
                    renderCoverLetterPreview(event.data);
                    saveCoverLetterToHistory(event.data);
                    toast("COVER LETTER GENERATED");
                }
            }
        }
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.classList.remove("loading");
        btn.textContent = "GENERATE COVER LETTER (AI)";
        setTimeout(() => {
            const container = document.getElementById("cl-progress");
            if (container) container.style.display = "none";
            const fill = document.getElementById("cl-progress-bar");
            if (fill) fill.style.width = "0";
        }, 3000);
    }
}

// ---------------------------------------------------------------------------
// History Dashboard
// ---------------------------------------------------------------------------
let historyPage = 1;
let lastTailoringMeta = null; // {company, job_title, match_score} from last AI run

// ---------------------------------------------------------------------------
// Cover Letter History
// ---------------------------------------------------------------------------
let clHistoryPage = 1;

async function saveCoverLetterToHistory(data) {
    try {
        await fetch("/api/cl-history/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cover_letter: data }),
        });
    } catch (_) {
        // silent — history save is non-critical
    }
}

async function loadClHistoryDashboard(page) {
    clHistoryPage = page;
    const container = document.getElementById("cl-history-dashboard");
    container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">LOADING…</div>`;
    try {
        const res = await fetch(`/api/cl-history/dashboard?page=${page}&limit=25`);
        if (!res.ok) throw new Error("Failed to load cover letter history");
        const data = await res.json();
        renderClHistoryTable(data);
    } catch (e) {
        container.innerHTML = `<div class="preview-empty" style="padding:2rem 0; color:#e74c3c;">${esc(e.message)}</div>`;
    }
}

function renderClHistoryTable(data) {
    const container = document.getElementById("cl-history-dashboard");
    if (!data.entries || data.entries.length === 0) {
        container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">NO COVER LETTERS YET — GENERATE ONE TO START TRACKING</div>`;
        return;
    }

    const rows = data.entries.map((entry) => {
        const ts = entry.timestamp || "";
        const datePart = ts ? ts.replace("T", " ").slice(0, 10) : "—";
        const timePart = ts ? ts.replace("T", " ").slice(11, 16) : "";
        const score = entry.relevance_score;
        let scoreHtml = "—";
        if (score !== null && score !== undefined) {
            const cls = score >= 7 ? "score-high" : score >= 4 ? "score-mid" : "score-low";
            scoreHtml = `<span class="history-score ${cls}">${score}/10</span>`;
        }
        const pdfLink = `<button type="button" class="btn-secondary btn-small" onclick="printClHistoryEntry('${esc(entry.id)}')" title="Open print/PDF dialog">PDF</button>`;
        const txtLink = `<a href="/api/cl-history/file/${entry.id}/cover_letter.txt" download style="color:var(--muted); text-decoration:underline;">TXT</a>`;

        return `<tr>
            <td style="white-space:nowrap;">
                <div style="line-height:1.05;">
                    ${esc(datePart)}<br>
                    ${timePart ? '<span style="color:var(--muted); font-size:11px;">' + esc(timePart) + '</span>' : ''}
                </div>
            </td>
            <td>${esc(entry.company || "—")}</td>
            <td>${esc(entry.job_title || "—")}</td>
            <td>${scoreHtml}</td>
            <td style="white-space:nowrap;">${pdfLink}</td>
            <td style="white-space:nowrap;">${txtLink}</td>
            <td style="white-space:nowrap;">
                <button type="button" class="btn-secondary btn-small" title="Restore to editor" onclick="restoreClHistoryEntry('${esc(entry.id)}')">✅</button>
                <button type="button" class="btn-danger btn-small" title="Delete" style="margin-left:4px;" onclick="deleteClHistoryEntry('${esc(entry.id)}')">❌</button>
            </td>
        </tr>`;
    }).join("");

    const totalPages = Math.ceil(data.total / data.limit);
    const paginationHtml = totalPages > 1 ? `
        <div class="history-pagination">
            <span>${data.total} total entries</span>
            <button type="button" class="btn-secondary btn-small" onclick="loadClHistoryDashboard(${clHistoryPage - 1})" ${clHistoryPage <= 1 ? "disabled" : ""}>← PREV</button>
            <span style="color:var(--fg);">${clHistoryPage} / ${totalPages}</span>
            <button type="button" class="btn-secondary btn-small" onclick="loadClHistoryDashboard(${clHistoryPage + 1})" ${clHistoryPage >= totalPages ? "disabled" : ""}>NEXT →</button>
        </div>` : `<div class="history-pagination"><span>${data.total} entr${data.total === 1 ? "y" : "ies"}</span></div>`;

    container.innerHTML = `
        <div style="overflow-x:auto;">
            <table class="history-table">
                <thead>
                    <tr>
                        <th>DATE</th>
                        <th>COMPANY</th>
                        <th>JOB TITLE</th>
                        <th>SCORE</th>
                        <th>PDF</th>
                        <th>FILE</th>
                        <th>ACTIONS</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        ${paginationHtml}`;
}

async function restoreClHistoryEntry(entryId) {
    try {
        const res = await fetch(`/api/cl-history/restore/${entryId}`, { method: "POST" });
        if (!res.ok) throw new Error("Restore failed");
        const data = await res.json();

        // Navigate to cover letter tab and show the letter in the preview
        const btns = document.querySelectorAll("#sidebar button");
        btns.forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
        const clBtn = document.querySelector("#sidebar button[data-tab='coverletter']");
        if (clBtn) clBtn.classList.add("active");
        document.getElementById("section-coverletter").classList.add("active");

        // Pre-fill JD field if available
        const jdEl = document.getElementById("cl-jd");
        if (jdEl && data.jd_text) jdEl.value = data.jd_text;

        // Re-render the letter in the preview pane
        renderCoverLetterPreview(data);
        toast("COVER LETTER RESTORED — REVIEW IN PREVIEW");
    } catch (e) {
        toast(e.message, true);
    }
}

async function deleteClHistoryEntry(entryId) {
    if (!confirm(`Delete cover letter entry "${entryId}"? This cannot be undone.`)) return;
    try {
        const res = await fetch("/api/cl-history/entry", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: entryId }),
        });
        if (!res.ok) throw new Error("Delete failed");
        toast("ENTRY DELETED");
        loadClHistoryDashboard(clHistoryPage);
    } catch (e) {
        toast(e.message, true);
    }
}

async function loadHistoryDashboard(page) {
    historyPage = page;
    const container = document.getElementById("history-dashboard");
    container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">LOADING…</div>`;
    try {
        const res = await fetch(`/api/history/dashboard?page=${page}&limit=25`);
        if (!res.ok) throw new Error("Failed to load history");
        const data = await res.json();
        renderHistoryTable(data);
    } catch (e) {
        container.innerHTML = `<div class="preview-empty" style="padding:2rem 0; color:#e74c3c;">${esc(e.message)}</div>`;
    }
}

function renderHistoryTable(data) {
    const container = document.getElementById("history-dashboard");
    if (!data.entries || data.entries.length === 0) {
        container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">NO HISTORY YET — GENERATE A RESUME TO START TRACKING</div>`;
        return;
    }

    const rows = data.entries.map((entry) => {
        const ts = entry.timestamp || "";
        const datePart = ts ? ts.replace("T", " ").slice(0, 10) : "—";
        const timePart = ts ? ts.replace("T", " ").slice(11, 16) : "";
        const score = entry.match_score;
        let scoreHtml = "—";
        if (score !== null && score !== undefined) {
            const cls = score >= 7 ? "score-high" : score >= 4 ? "score-mid" : "score-low";
            scoreHtml = `<span class="history-score ${cls}">${score}/10</span>`;
        }
        const hiredClass = entry.hired ? "hired-yes" : "hired-no";
        const hiredLabel = entry.hired ? "✓ YES" : "✗ NO";
        const pdfLink = entry.pdf_filename
            ? `<a href="/api/history/file/${entry.id}/${entry.pdf_filename}" target="_blank" style="color:var(--muted); text-decoration:underline;">PDF</a>`
            : "—";

        return `<tr>
            <td style="white-space:nowrap;">
                <div style="line-height:1.05;">
                    ${esc(datePart)}<br>
                    ${timePart ? '<span style="color:var(--muted); font-size:11px;">' + esc(timePart) + '</span>' : ''}
                </div>
            </td>
            <td>${esc(entry.company || "—")}</td>
            <td>${esc(entry.job_title || "—")}</td>
            <td>${scoreHtml}</td>
            <td><span class="${hiredClass}" onclick="toggleHired('${esc(entry.id)}', ${entry.hired}, this)" title="Click to toggle">${hiredLabel}</span></td>
            <td style="white-space:nowrap;">${pdfLink}</td>
            <td style="white-space:nowrap;">
                    <button type="button" class="btn-secondary btn-small" title="Restore" onclick="restoreHistoryEntry('${esc(entry.id)}')">✅</button>
                    <button type="button" class="btn-danger btn-small" title="Delete" style="margin-left:4px;" onclick="deleteHistoryEntry('${esc(entry.id)}')">❌</button>
            </td>
        </tr>`;
    }).join("");

    const totalPages = Math.ceil(data.total / data.limit);
    const paginationHtml = totalPages > 1 ? `
        <div class="history-pagination">
            <span>${data.total} total entries</span>
            <button type="button" class="btn-secondary btn-small" onclick="loadHistoryDashboard(${historyPage - 1})" ${historyPage <= 1 ? "disabled" : ""}>← PREV</button>
            <span style="color:var(--fg);">${historyPage} / ${totalPages}</span>
            <button type="button" class="btn-secondary btn-small" onclick="loadHistoryDashboard(${historyPage + 1})" ${historyPage >= totalPages ? "disabled" : ""}>NEXT →</button>
        </div>` : `<div class="history-pagination"><span>${data.total} entr${data.total === 1 ? "y" : "ies"}</span></div>`;

    container.innerHTML = `
        <div style="overflow-x:auto;">
            <table class="history-table">
                <thead>
                    <tr>
                        <th>DATE</th>
                        <th>COMPANY</th>
                        <th>JOB TITLE</th>
                        <th>SCORE</th>
                        <th>HIRED</th>
                        <th>PDF</th>
                        <th>ACTIONS</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>
        ${paginationHtml}`;
}

async function restoreHistoryEntry(entryId) {
    try {
        const res = await fetch(`/api/history/restore/${entryId}`, { method: "POST" });
        if (!res.ok) throw new Error("Restore failed");
        const data = await res.json();

        // Merge into state
        if (data.profile) Object.assign(state.profile, data.profile);
        if (data.contact) Object.assign(state.contact, data.contact);
        if (data.education) state.education = data.education;
        if (data.experience) state.experience = data.experience;
        if (data.projects) state.projects = data.projects;
        if (data.skills) state.skills = data.skills;

        // Re-render all form sections
        populateScalarFields();
        renderEducation();
        renderExperience();
        renderProjects();
        renderSkills();

        // Switch to profile tab
        const btns = document.querySelectorAll("#sidebar button");
        btns.forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".section").forEach((s) => s.classList.remove("active"));
        const profileBtn = document.querySelector("#sidebar button[data-tab='profile']");
        if (profileBtn) profileBtn.classList.add("active");
        document.getElementById("section-profile").classList.add("active");

        toast("RESTORED — REVIEW FIELDS & REGENERATE");
    } catch (e) {
        toast(e.message, true);
    }
}

async function deleteHistoryEntry(entryId) {
    if (!confirm(`Delete history entry "${entryId}"? This cannot be undone.`)) return;
    try {
        const res = await fetch("/api/history/entry", {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: entryId }),
        });
        if (!res.ok) throw new Error("Delete failed");
        toast("ENTRY DELETED");
        loadHistoryDashboard(historyPage);
    } catch (e) {
        toast(e.message, true);
    }
}

async function toggleHired(entryId, currentVal, cellEl) {
    const newVal = !currentVal;
    try {
        const res = await fetch("/api/history/hired", {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ folder: entryId, hired: newVal }),
        });
        if (!res.ok) throw new Error("Update failed");
        // Update cell in-place without a full reload
        cellEl.className = newVal ? "hired-yes" : "hired-no";
        cellEl.textContent = newVal ? "✓ YES" : "✗ NO";
        cellEl.setAttribute("onclick", `toggleHired('${entryId}', ${newVal}, this)`);
    } catch (e) {
        toast(e.message, true);
    }
}

// ---------------------------------------------------------------------------
// Stats Dashboard
// ---------------------------------------------------------------------------
let statsChart = null;
let statsPeriod = "weekly";
let statsType = "all";

async function loadStatsDashboard() {
    const container = document.getElementById("stats-dashboard");
    container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">LOADING...</div>`;
    try {
        const res = await fetch(`/api/history/stats?period=${statsPeriod}&type=${statsType}`);
        if (!res.ok) throw new Error("Failed to load stats");
        renderStatsDashboard(await res.json());
    } catch (e) {
        container.innerHTML = `<div class="preview-empty" style="padding:2rem 0;">${esc(e.message)}</div>`;
    }
}

function renderStatsDashboard(data) {
    const container = document.getElementById("stats-dashboard");
    const hitRate = data.submission_count > 0
        ? Math.round((data.hired_count / data.submission_count) * 100)
        : 0;

    const periodBtns = ["weekly", "monthly", "annual"].map(p =>
        `<button class="btn-secondary btn-small stats-toggle${statsPeriod === p ? " active" : ""}"
                 onclick="setStatsPeriod('${p}')">${p.toUpperCase()}</button>`
    ).join("");

    const typeBtns = [["all", "ALL"], ["resume", "RESUMES"], ["cover_letter", "COVER LETTERS"]].map(([val, label]) =>
        `<button class="btn-secondary btn-small stats-toggle${statsType === val ? " active" : ""}"
                 onclick="setStatsType('${val}')">${label}</button>`
    ).join("");

    container.innerHTML = `
        <div class="stats-controls">
            <div class="stats-toggle-group">${periodBtns}</div>
            <div class="stats-toggle-group">${typeBtns}</div>
        </div>
        <div class="stats-summary">
            <div class="stats-card"><div class="stats-card-value">${data.submission_count}</div><div class="stats-card-label">SUBMISSIONS</div></div>
            <div class="stats-card"><div class="stats-card-value">${data.hired_count}</div><div class="stats-card-label">HIRED</div></div>
            <div class="stats-card"><div class="stats-card-value">${data.pending_count}</div><div class="stats-card-label">PENDING</div></div>
            <div class="stats-card"><div class="stats-card-value">${hitRate}%</div><div class="stats-card-label">HIT RATE</div></div>
        </div>
        <div class="stats-chart-wrap"><canvas id="stats-chart"></canvas></div>`;

    if (statsChart) { statsChart.destroy(); statsChart = null; }

    if (data.series.length === 0) {
        document.querySelector(".stats-chart-wrap").innerHTML =
            `<div class="preview-empty" style="height:100%;display:flex;align-items:center;justify-content:center;">NO DATA FOR THIS PERIOD</div>`;
        return;
    }

    statsChart = new Chart(document.getElementById("stats-chart").getContext("2d"), {
        data: {
            labels: data.series.map(s => s.label),
            datasets: [
                {
                    type: "bar",
                    label: "Total",
                    data: data.series.map(s => s.total),
                    backgroundColor: "rgba(255,255,255,0.12)",
                    borderColor: "rgba(255,255,255,0.35)",
                    borderWidth: 1,
                },
                {
                    type: "line",
                    label: "Hired",
                    data: data.series.map(s => s.hired),
                    borderColor: "#fff",
                    backgroundColor: "transparent",
                    pointBackgroundColor: "#fff",
                    pointRadius: 4,
                    tension: 0.35,
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { labels: { color: "#888", font: { family: "JetBrains Mono", size: 11 } } },
                tooltip: {
                    backgroundColor: "#111",
                    titleColor: "#fff",
                    bodyColor: "#888",
                    borderColor: "#333",
                    borderWidth: 1,
                    callbacks: {
                        afterBody: (items) => {
                            const idx = items[0].dataIndex;
                            const s = data.series[idx];
                            return [`Pending: ${s.pending}`];
                        },
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: "#888", font: { family: "JetBrains Mono", size: 10 } },
                    grid: { color: "#1a1a1a" },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#888", font: { family: "JetBrains Mono", size: 10 }, precision: 0 },
                    grid: { color: "#1a1a1a" },
                },
            },
        },
    });
}

function setStatsPeriod(p) { statsPeriod = p; loadStatsDashboard(); }
function setStatsType(t) { statsType = t; loadStatsDashboard(); }

// ---------------------------------------------------------------------------
// Toast
// ---------------------------------------------------------------------------
function toast(msg, isError = false) {
    const el = document.getElementById("toast");
    el.textContent = msg;
    el.className = "toast visible" + (isError ? " error" : "");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => {
        el.className = "toast";
    }, 2500);
}

// ---------------------------------------------------------------------------
// Util
// ---------------------------------------------------------------------------
function esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}
